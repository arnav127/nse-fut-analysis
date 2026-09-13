"""Run logging: one rotating file per stage plus the console.

The pipeline's stages are long and mostly unattended, so the console is where a person
watches and the file is what gets read afterwards when something looks wrong. Handlers are
attached once per logger name; re-importing a stage module in the same process would
otherwise duplicate every line.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-14s | %(message)s"


def setup_logger(name: str, filename: str = "pipeline.log", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger
