import logging
import datetime
from typing import Optional

# Store the root logger name configured by main
_ROOT_LOGGER_NAME = None
_ROOT_HANDLER_CONFIGURED = False

def configure_logger(name: str, level: Optional[int] = logging.INFO) -> logging.Logger:
    """
    Gets a logger instance and ensures it has a console handler for output visibility.

    Args:
        name: The name of the logger.
        level: The desired level for this specific logger.

    Returns:
        A logger instance with console output enabled.
    """
    logger = logging.getLogger(name)
    # Set the individual logger level
    logger.setLevel(level)
    
    # Add a console handler if one doesn't exist already
    has_console_handler = False
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream.name == '<stdout>':
            has_console_handler = True
            break
    
    if not has_console_handler:
        # Create and add a console handler with formatted output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter('[%(levelname)s | %(asctime)s | %(name)s] %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Ensure propagation is enabled so messages can also reach the root handler if configured
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