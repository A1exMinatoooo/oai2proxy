"""Anthropic → OpenAI API proxy.

Accepts requests in Anthropic Messages API format, converts them to
OpenAI Chat Completions format, forwards to a configurable upstream
endpoint, and converts the response back (including streaming).

Usage:
    export UPSTREAM_BASE_URL=https://api.openai.com/v1
    export UPSTREAM_API_KEY=sk-xxx
    python main.py
"""

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config import settings
from converter import (
    anthropic_to_openai_request,
    openai_to_anthropic_response,
    stream_openai_to_anthropic,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Anthropic→OpenAI Proxy")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require x-api-key header when PROXY_API_KEY is configured."""
    if settings.proxy_api_key and request.url.path != "/health":
        api_key = request.headers.get("x-api-key", "")
        if api_key != settings.proxy_api_key:
            return JSONResponse(
                status_code=401,
                content=_anthropic_error("authentication_error", "Invalid or missing x-api-key"),
            )
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok", "upstream": settings.upstream_base_url}


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    model = body.get("model", "")
    is_stream = body.get("stream", False)

    # Convert request
    openai_body = anthropic_to_openai_request(body)
    logger.info("→ %s model=%s stream=%s", request.url.path, model, is_stream)

    # Build upstream URL
    upstream_url = f"{settings.upstream_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.upstream_api_key}",
    }

    if is_stream:
        return await _proxy_stream(upstream_url, headers, openai_body, model)
    else:
        return await _proxy_sync(upstream_url, headers, openai_body, model)


async def _proxy_sync(upstream_url: str, headers: dict, openai_body: dict, model: str) -> JSONResponse:
    """Forward as a regular request and return the converted response."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        try:
            resp = await client.post(upstream_url, json=openai_body, headers=headers)
        except httpx.RequestError as exc:
            logger.error("Upstream request failed: %s", exc)
            return JSONResponse(
                status_code=502,
                content=_anthropic_error("upstream_error", str(exc)),
            )

        if resp.status_code != 200:
            logger.error("Upstream returned %d: %s", resp.status_code, resp.text[:500])
            return JSONResponse(
                status_code=resp.status_code,
                content=_anthropic_error("upstream_error", resp.text[:1000]),
            )

        openai_resp = resp.json()
        anthropic_resp = openai_to_anthropic_response(openai_resp, model)
        return JSONResponse(content=anthropic_resp)


async def _proxy_stream(upstream_url: str, headers: dict, openai_body: dict, model: str) -> StreamingResponse:
    """Forward as a streaming request and convert SSE chunks on the fly."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))

    async def generate():
        try:
            async with client.stream("POST", upstream_url, json=openai_body, headers=headers) as resp:
                if resp.status_code != 200:
                    body_bytes = await resp.aread()
                    error_event = (
                        f"event: error\n"
                        f"data: {__import__('json').dumps(_anthropic_error('upstream_error', body_bytes.decode()[:1000]))}\n\n"
                    )
                    yield error_event.encode()
                    return

                async for chunk in stream_openai_to_anthropic(resp.aiter_lines(), model):
                    yield chunk.encode()
        except httpx.RequestError as exc:
            logger.error("Upstream stream failed: %s", exc)
            error_event = (
                f"event: error\n"
                f"data: {__import__('json').dumps(_anthropic_error('upstream_error', str(exc)))}\n\n"
            )
            yield error_event.encode()
        finally:
            await client.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _anthropic_error(error_type: str, message: str) -> dict:
    return {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message,
        },
    }


if __name__ == "__main__":
    import uvicorn

    from config import BINARY_MODE, _config_path

    if BINARY_MODE:
        logger.info("Config file: %s", _config_path())
    logger.info("Starting proxy on %s:%d → %s", settings.proxy_host, settings.proxy_port, settings.upstream_base_url)
    uvicorn.run(app, host=settings.proxy_host, port=settings.proxy_port)
