"""Configuration management.

Priority (highest → lowest):
  1. Environment variables
  2. .env file (dev mode only)
  3. User config file (binary mode: ~/.oai2proxy/config.ini)
"""

import os
import sys
from configparser import ConfigParser
from pathlib import Path

from pydantic_settings import BaseSettings

APP_NAME = "oai2proxy"
BINARY_MODE = getattr(sys, "frozen", False)


def _config_path() -> Path:
    return Path.home() / f".{APP_NAME}" / "config.ini"


def _ensure_config() -> None:
    """In binary mode, create a template config file if it doesn't exist."""
    path = _config_path()
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {APP_NAME} configuration\n"
        "# Edit the values below, then restart the program.\n"
        "# Environment variables will override these values.\n"
        "\n"
        "[server]\n"
        "host = 0.0.0.0\n"
        "port = 8080\n"
        "\n"
        "# API key required to access this proxy (optional).\n"
        "# Clients must send this key in the x-api-key header.\n"
        "# Leave empty to allow unauthenticated access.\n"
        "# proxy_api_key =\n"
        "\n"
        "[upstream]\n"
        "# OpenAI-compatible endpoint base URL (required)\n"
        "base_url = https://api.openai.com/v1\n"
        "\n"
        "# API key for the upstream endpoint (required)\n"
        "api_key = YOUR_API_KEY_HERE\n",
        encoding="utf-8",
    )
    print(f"{'=' * 60}")
    print(f"  Config file created at:")
    print(f"    {path}")
    print(f"")
    print(f"  Please edit it and fill in your upstream API key,")
    print(f"  then restart the program.")
    print(f"{'=' * 60}")
    sys.exit(0)


def _load_config_file() -> dict:
    """Load settings from the user config file and return as env-style dict."""
    path = _config_path()
    if not path.exists():
        return {}

    parser = ConfigParser()
    parser.read(path, encoding="utf-8")

    mapping: dict[str, str] = {}
    if parser.has_option("upstream", "base_url"):
        mapping["UPSTREAM_BASE_URL"] = parser.get("upstream", "base_url")
    if parser.has_option("upstream", "api_key"):
        mapping["UPSTREAM_API_KEY"] = parser.get("upstream", "api_key")
    if parser.has_option("server", "proxy_api_key"):
        mapping["PROXY_API_KEY"] = parser.get("server", "proxy_api_key")
    if parser.has_option("server", "host"):
        mapping["PROXY_HOST"] = parser.get("server", "host")
    if parser.has_option("server", "port"):
        mapping["PROXY_PORT"] = parser.get("server", "port")
    return mapping


# In binary mode: ensure config file exists (exit if newly created),
# then inject values into env so pydantic-settings picks them up.
if BINARY_MODE:
    _ensure_config()
    for key, val in _load_config_file().items():
        os.environ.setdefault(key, val)


class Settings(BaseSettings):
    # Upstream OpenAI-compatible endpoint
    upstream_base_url: str = "https://api.openai.com/v1"
    upstream_api_key: str = ""

    # Proxy server
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8080

    # Proxy entry auth (empty = no auth required)
    proxy_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
