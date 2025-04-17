import logging
import datetime
from typing import Optional

# Store the root logger name configured by main
_ROOT_LOGGER_NAME = None
_ROOT_HANDLER_CONFIGURED = False

def configure_logger(name: str, level: Optional[int] = logging.INFO) -> logging.Logger:
    """
    Gets a logger instance. Configuration (level, handler) should be set
    by setup_main_logger.

    Args:
        name: The name of the logger.
        level: The desired level for this specific logger (will be overridden by root if stricter).

    Returns:
        A logger instance.
    """
    logger = logging.getLogger(name)
    # Set the individual logger level, but messages are still filtered by the root handler
    logger.setLevel(level)
    # Ensure propagation is enabled so messages reach the root handler
    logger.propagate = True
    return logger

# Function to be called ONLY from main.py to set the initial root level
def setup_main_logger(root_name: str, level: int) -> logging.Logger:
    """Sets up the root logger and its single handler level."""
    global _ROOT_LOGGER_NAME, _ROOT_HANDLER_CONFIGURED

    if _ROOT_HANDLER_CONFIGURED:
        # If already configured, just get the logger and ensure level is set
        logger = logging.getLogger(root_name)
        logger.setLevel(level)
        # Make sure the handler level is also updated if called again (though shouldn't happen)
        if logger.handlers:
            logger.handlers[0].setLevel(level)
        return logger

    _ROOT_LOGGER_NAME = root_name
    logger = logging.getLogger(root_name)
    logger.setLevel(level) # Set root logger level

    # Remove existing handlers to prevent duplicates if run multiple times in a session
    for h in list(logger.handlers): # Iterate over a copy
         logger.removeHandler(h)

    # Configure the single root handler
    handler = logging.StreamHandler()
    handler.setLevel(level) # Set handler level to match root logger level
    # Add logger name to the format for clarity
    formatter = logging.Formatter('[%(levelname)s | %(asctime)s | %(name)s | %(message)s]')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent messages propagating to the absolute root logger (which might have default handlers)
    logger.propagate = False

    _ROOT_HANDLER_CONFIGURED = True
    return logger 