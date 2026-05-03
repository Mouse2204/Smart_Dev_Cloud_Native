import logging
import sys
import os

def get_logger(name: str) -> logging.Logger:
    """Returns a standardized logger with colored console output."""
    logger = logging.getLogger(name)
    
    # Avoid adding multiple handlers if the logger is accessed multiple times
    if logger.handlers:
        return logger

    # Set log level from environment
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)

    # Console Handler
    handler = logging.StreamHandler(sys.stdout)
    
    # Custom Formatter
    # [Gray TIMESTAMP] [Colored LEVEL] [Bold NAME] - MESSAGE
    class ColoredFormatter(logging.Formatter):
        GREY = "\x1b[38;20m"
        BLUE = "\x1b[38;5;39m"
        YELLOW = "\x1b[33;20m"
        RED = "\x1b[31;20m"
        BOLD_RED = "\x1b[31;1m"
        RESET = "\x1b[0m"
        
        FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"

        FLAGS = {
            logging.DEBUG: GREY,
            logging.INFO: BLUE,
            logging.WARNING: YELLOW,
            logging.ERROR: RED,
            logging.CRITICAL: BOLD_RED
        }

        def format(self, record):
            log_fmt = self.FLAGS.get(record.levelno) + self.FORMAT + self.RESET
            formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
            return formatter.format(record)

    handler.setFormatter(ColoredFormatter())
    logger.addHandler(handler)
    
    return logger
