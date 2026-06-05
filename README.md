# oai2proxy

Anthropic Messages API → OpenAI Chat Completions API 的轻量级代理服务器。

接收 Anthropic 格式请求，转换为 OpenAI 格式转发至上游，再将响应转换回 Anthropic 格式返回给客户端。支持同步和流式（SSE）两种模式。

## 快速开始

```bash
# 安装依赖
uv sync

# 配置上游地址和密钥
cp .env.example .env
# 编辑 .env，填入你的 UPSTREAM_BASE_URL 和 UPSTREAM_API_KEY

# 启动服务
uv run python main.py
```

服务默认监听 `0.0.0.0:8080`。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `UPSTREAM_BASE_URL` | 是 | `https://api.openai.com/v1` | 上游 OpenAI 兼容接口的 Base URL |
| `UPSTREAM_API_KEY` | 是 | — | 上游接口的 API Key |
| `PROXY_HOST` | 否 | `0.0.0.0` | 代理监听地址 |
| `PROXY_PORT` | 否 | `8080` | 代理监听端口 |

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查，返回 `{"status":"ok","upstream":"..."}` |
| `POST` | `/v1/messages` | 主代理端点，接收 Anthropic Messages API 请求 |

### 支持的功能

- **System prompt**：字符串或 content block 列表
- **消息内容**：纯文本、图片（base64 和 URL）
- **参数透传**：`max_tokens`、`temperature`、`top_p`、`stop_sequences`、`stream`
- **流式响应**：完整的 Anthropic SSE 事件生命周期
- **Token 用量统计**：同步和流式模式均支持

### 暂不支持

- Tool use / Function calling
- `metadata`、`top_k`、`prefill` 等 Anthropic 特有参数

> **注意**：代理本身不提供访问鉴权。任何能访问到代理服务的请求都会被直接转发至上游。`UPSTREAM_API_KEY` 仅用于代理→上游的身份验证，不保护代理入口。请通过网络层（防火墙、VPN 等）限制访问，或等待后续版本支持 `PROXY_API_KEY`。

## 部署方式

### Docker

```bash
# 构建镜像
docker build -t oai2proxy .

# 运行
docker run -d --name oai2proxy -p 8080:8080 \
  -e UPSTREAM_BASE_URL=https://your-upstream/v1 \
  -e UPSTREAM_API_KEY=sk-xxx \
  oai2proxy
```

### 独立二进制

```bash
# 构建（需要 uv 环境）
uv run python build.py

# 产物：dist/oai2proxy（约 16MB，含完整 Python 运行时）
# 拷贝到目标机器后直接运行
UPSTREAM_BASE_URL=https://your-upstream/v1 \
UPSTREAM_API_KEY=sk-xxx \
./oai2proxy
```

> 二进制与构建时的操作系统和架构绑定。跨平台构建参见 [GitHub Actions release workflow](.github/workflows/release.yml)。

### 内网离线部署

```bash
# Docker 方式：本机构建 → 导出 → 内网加载
docker save oai2proxy | gzip > oai2proxy.tar.gz
# 拷贝到内网机器
docker load < oai2proxy.tar.gz
docker run -d --name oai2proxy -p 8080:8080 \
  -e UPSTREAM_BASE_URL=https://your-upstream/v1 \
  -e UPSTREAM_API_KEY=sk-xxx \
  oai2proxy
```

## 测试

```bash
# 非流式
curl http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{"model":"gpt-4","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}'

# 流式
curl -N http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: test" \
  -d '{"model":"gpt-4","max_tokens":100,"stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```

## 项目结构

```
main.py          # FastAPI 应用，路由定义
converter.py     # Anthropic ↔ OpenAI 格式转换逻辑
config.py        # 配置管理（环境变量 / .env / INI 文件）
build.py         # PyInstaller 构建脚本
Dockerfile       # 生产环境 Docker 镜像
Dockerfile.build # 跨平台交叉编译镜像
```

## 技术栈

- Python 3.12
- FastAPI + Uvicorn（Web 框架）
- httpx（异步 HTTP 客户端）
- pydantic-settings（配置管理）
- PyInstaller（独立二进制打包）
