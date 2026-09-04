from __future__ import annotations

import logging
import os
from pathlib import Path


def log_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return root / "BrowserCacheTool" / "browser_cache_tool.log"


def create_logger() -> logging.Logger:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("BrowserCacheTool")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger