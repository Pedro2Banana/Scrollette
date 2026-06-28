import logging
from logging.handlers import RotatingFileHandler

from app.config import LOG_DIR


def setup_logging():
    """Configure the `app` logger: full detail to a rotating file, key info to
    the console. Call once at startup. Child loggers (app.*) inherit this."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")

    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False  # 不再往 root 冒泡，避免重复打印

    file_handler = RotatingFileHandler(
        LOG_DIR / "scrollette.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
