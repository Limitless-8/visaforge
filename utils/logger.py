"""
utils/logger.py
---------------
Lightweight logger factory. All modules should use `get_logger(__name__)`
instead of printing or calling logging.basicConfig themselves.
"""

from __future__ import annotations

import logging
import sys

from config.settings import settings

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)
