"""Logging setup: rotating file handler + stdout stream."""

import logging
import sys
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s|%(levelname)s|%(name)s|%(message)s"
LOG_FILE = "receptionist.log"

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        file_handler,
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("mca.receptionist")
