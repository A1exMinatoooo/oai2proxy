#!/usr/bin/env python3
"""Build a standalone binary using PyInstaller.

Usage:
    uv run python build.py

Output:
    dist/oai2proxy   — single executable, no Python runtime needed
"""

import subprocess
import sys


def main():
    # Install pyinstaller via uv
    subprocess.check_call(
        ["uv", "pip", "install", "--quiet", "pyinstaller"],
    )

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--name", "oai2proxy",
            "--add-data", "converter.py:.",
            "--add-data", "config.py:.",
            "--hidden-import", "uvicorn.logging",
            "--hidden-import", "uvicorn.loops",
            "--hidden-import", "uvicorn.loops.auto",
            "--hidden-import", "uvicorn.protocols",
            "--hidden-import", "uvicorn.protocols.http",
            "--hidden-import", "uvicorn.protocols.http.auto",
            "--hidden-import", "uvicorn.protocols.websockets",
            "--hidden-import", "uvicorn.protocols.websockets.auto",
            "--hidden-import", "uvicorn.lifespan",
            "--hidden-import", "uvicorn.lifespan.on",
            "main.py",
        ]
    )
    print("\n✅ Build complete: dist/oai2proxy")
    print("   Copy this single file to the target machine and run:")
    print("   UPSTREAM_BASE_URL=https://... UPSTREAM_API_KEY=sk-... ./oai2proxy")


if __name__ == "__main__":
    main()
