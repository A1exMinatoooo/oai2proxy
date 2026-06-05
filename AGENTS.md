# AGENTS.md — Anthropic→OpenAI Proxy

## Overview

A lightweight Python proxy that accepts Anthropic Messages API requests,
converts them to OpenAI Chat Completions format, and forwards to a
configurable upstream endpoint. Supports both synchronous and streaming modes.

## Quick Start

```bash
uv sync                                    # install dependencies
cp .env.example .env                        # edit with your upstream URL and key
uv run python main.py                       # start the proxy
```

## Build / Run

```bash
# Install dependencies
uv sync

# Run the server
uv run python main.py

# Or with uvicorn directly
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `UPSTREAM_BASE_URL` | Yes | `https://api.openai.com/v1` | OpenAI-compatible endpoint base URL |
| `UPSTREAM_API_KEY` | Yes | — | API key for the upstream endpoint |
| `PROXY_HOST` | No | `0.0.0.0` | Proxy listen address |
| `PROXY_PORT` | No | `8080` | Proxy listen port |

## Architecture

- `main.py` — FastAPI app, routes `/v1/messages` and `/health`
- `converter.py` — Request/response/stream format conversion
- `config.py` — Pydantic settings from env vars / `.env`

## Deployment (内网离线部署)

### 方式一：Docker 镜像

```bash
# 本机构建镜像
docker build -t oai2proxy .

# 导出镜像为文件
docker save oai2proxy | gzip > oai2proxy.tar.gz

# 内网机器加载并运行
docker load < oai2proxy.tar.gz
docker run -d --name oai2proxy -p 8080:8080 \
  -e UPSTREAM_BASE_URL=https://your-upstream/v1 \
  -e UPSTREAM_API_KEY=sk-xxx \
  oai2proxy
```

### 方式二：单文件二进制

```bash
# 本机构建（需 uv 环境）
uv run python build.py

# 输出：dist/oai2proxy（~16MB，含完整 Python 运行时）
# 拷贝到内网机器后直接运行：
UPSTREAM_BASE_URL=https://your-upstream/v1 \
UPSTREAM_API_KEY=sk-xxx \
./oai2proxy
```

> ⚠️ 二进制文件与构建时的操作系统和架构绑定（如 macOS arm64）。
> 如需 Linux x86_64 版本，在对应架构上执行 `uv run python build.py`。

## Testing

```bash
# Non-streaming
curl http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{"model":"gpt-4","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}'

# Streaming
curl -N http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{"model":"gpt-4","max_tokens":100,"stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```
