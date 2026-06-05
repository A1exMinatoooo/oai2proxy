"""Configuration loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Upstream OpenAI-compatible endpoint
    upstream_base_url: str = "https://api.openai.com/v1"
    upstream_api_key: str = ""

    # Proxy server
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8080

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
