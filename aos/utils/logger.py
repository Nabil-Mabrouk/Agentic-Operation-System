import logging
import sys
from typing import Optional

def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configures the root logger for the entire application.
    This should be called only ONCE when the application starts.

    Args:
        level: The log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to a log file. If provided, logs will also be written to this file.

    Example:
        setup_logging(level="DEBUG", log_file="aos.log")
    """
    root_logger = logging.getLogger()
    
    # Validate and set log level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        logging.warning(f"Invalid log level: {level}. Defaulting to INFO.")
        numeric_level = logging.INFO
    root_logger.setLevel(numeric_level)
    
    # Avoid adding duplicate handlers
    if root_logger.handlers:
        logging.info("Logging already configured. Skipping setup.")
        return

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)-25s - %(levelname)-8s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            logging.info(f"Logging to file: {log_file}")
        except Exception as e:
            logging.error(f"Failed to set up file logging to {log_file}: {e}")

    logging.info(f"Root logger configured with level {logging.getLevelName(numeric_level)}")