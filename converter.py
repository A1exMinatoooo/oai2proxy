"""Convert between Anthropic Messages API and OpenAI Chat Completions API formats."""

import json
import time
import uuid
from collections.abc import AsyncIterator


# ---------------------------------------------------------------------------
# Request: Anthropic → OpenAI
# ---------------------------------------------------------------------------

def anthropic_to_openai_request(body: dict) -> dict:
    """Convert an Anthropic Messages request body to an OpenAI Chat Completions request body."""
    openai: dict = {
        "model": body.get("model", ""),
        "messages": [],
    }

    # System message
    system = body.get("system")
    if system:
        if isinstance(system, str):
            openai["messages"].append({"role": "system", "content": system})
        elif isinstance(system, list):
            # Anthropic allows system as content blocks
            text_parts = [b.get("text", "") for b in system if b.get("type") == "text"]
            openai["messages"].append({"role": "system", "content": "\n".join(text_parts)})

    # Messages
    for msg in body.get("messages", []):
        openai["messages"].append(_convert_message(msg))

    # Parameters
    if "max_tokens" in body:
        openai["max_tokens"] = body["max_tokens"]
    if "temperature" in body:
        openai["temperature"] = body["temperature"]
    if "top_p" in body:
        openai["top_p"] = body["top_p"]
    if "stop_sequences" in body:
        openai["stop"] = body["stop_sequences"]
    if body.get("stream"):
        openai["stream"] = True
        openai["stream_options"] = {"include_usage": True}

    return openai


def _convert_message(msg: dict) -> dict:
    """Convert a single Anthropic message to OpenAI format."""
    role = msg["role"]
    content = msg.get("content")

    if isinstance(content, str):
        return {"role": role, "content": content}

    if isinstance(content, list):
        parts = []
        for block in content:
            btype = block.get("type")
            if btype == "text":
                parts.append(block["text"])
            elif btype == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    media_type = source.get("media_type", "image/png")
                    data = source.get("data", "")
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    })
                elif source.get("type") == "url":
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": source.get("url", "")},
                    })
            # tool_use / tool_result can be added later

        # If all parts are plain text, collapse to a single string
        if all(isinstance(p, str) for p in parts):
            return {"role": role, "content": "\n".join(parts)}
        # Mixed content (text + images)
        content_parts = []
        for p in parts:
            if isinstance(p, str):
                content_parts.append({"type": "text", "text": p})
            else:
                content_parts.append(p)
        return {"role": role, "content": content_parts}

    return {"role": role, "content": ""}


# ---------------------------------------------------------------------------
# Response (non-streaming): OpenAI → Anthropic
# ---------------------------------------------------------------------------

def openai_to_anthropic_response(openai_resp: dict, model: str) -> dict:
    """Convert an OpenAI Chat Completions response to Anthropic Messages format."""
    choice = openai_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")

    content_text = message.get("content") or ""
    content = [{"type": "text", "text": content_text}] if content_text else []

    usage_in = openai_resp.get("usage", {})
    anthropic_resp = {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": _map_finish_reason(finish_reason),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage_in.get("prompt_tokens", 0),
            "output_tokens": usage_in.get("completion_tokens", 0),
        },
    }
    return anthropic_resp


def _map_finish_reason(reason: str | None) -> str:
    if reason == "length":
        return "max_tokens"
    if reason == "tool_calls":
        return "tool_use"
    return "end_turn"


# ---------------------------------------------------------------------------
# Streaming: OpenAI SSE → Anthropic SSE
# ---------------------------------------------------------------------------

async def stream_openai_to_anthropic(
    openai_stream: AsyncIterator[bytes],
    model: str,
) -> AsyncIterator[str]:
    """Convert an OpenAI SSE stream to Anthropic SSE events.

    Yields lines in the format:
        event: <event_type>\n
        data: <json>\n\n
    """
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
    block_index = 0
    started = False
    finished = False

    # Yield message_start immediately
    message_start = _make_message_start(msg_id, model)
    yield _sse("message_start", message_start)

    async for raw_line in openai_stream:
        line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else raw_line.strip()

        if not line or line.startswith(":"):
            continue

        # OpenAI signals end of stream
        if line == "data: [DONE]":
            break

        if not line.startswith("data: "):
            continue

        payload = json.loads(line[6:])
        choices = payload.get("choices", [])
        usage = payload.get("usage")

        if not choices and not usage:
            continue

        # Emit content_block_start on first chunk with content
        if choices:
            delta = choices[0].get("delta", {})
            chunk_text = delta.get("content") or ""
            finish_reason = choices[0].get("finish_reason")

            if chunk_text and not started:
                started = True
                yield _sse("content_block_start", {
                    "index": block_index,
                    "content_block": {"type": "text", "text": ""},
                })

            if chunk_text:
                yield _sse("content_block_delta", {
                    "index": block_index,
                    "delta": {"type": "text_delta", "text": chunk_text},
                })

            if finish_reason and not finished:
                finished = True
                # Close the text block
                if started:
                    yield _sse("content_block_stop", {"index": block_index})
                # message_delta with stop_reason and usage
                delta_payload: dict = {
                    "stop_reason": _map_finish_reason(finish_reason),
                }
                if usage:
                    delta_payload["usage"] = {
                        "output_tokens": usage.get("completion_tokens", 0),
                    }
                yield _sse("message_delta", delta_payload)

        # If usage comes in a separate chunk without choices
        elif usage and not finished:
            finished = True
            if started:
                yield _sse("content_block_stop", {"index": block_index})
            yield _sse("message_delta", {
                "stop_reason": "end_turn",
                "usage": {"output_tokens": usage.get("completion_tokens", 0)},
            })

    # If stream ended without a finish_reason
    if not finished:
        if started:
            yield _sse("content_block_stop", {"index": block_index})
        yield _sse("message_delta", {"stop_reason": "end_turn"})

    yield _sse("message_stop", {})


def _make_message_start(msg_id: str, model: str) -> dict:
    return {
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
