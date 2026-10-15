"""Logging setup with Rich console and file handlers."""

import logging
import logging.handlers
from pathlib import Path

from rich.logging import RichHandler

from config.settings import settings


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(settings.LOG_LEVEL)

    # Rich console handler
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
    )
    console_handler.setLevel(settings.LOG_LEVEL)
    logger.addHandler(console_handler)

    # File handler
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=5_000_000,
        backupCount=3,
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(file_handler)

    return logger
