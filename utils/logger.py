import logging
import datetime
from typing import Optional

# Configure the logger with a custom format
def configure_logger(name: str, level: Optional[int] = logging.INFO) -> logging.Logger:
    """
    Configure a logger with a custom format: [log level | timestamp | debug message]
    
    Args:
        name: The name of the logger
        level: The logging level (default: INFO)
        
    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)
    
    # If the logger already has handlers, don't add more
    if logger.handlers:
        return logger
        
    logger.setLevel(level)
    
    # Create a console handler
    handler = logging.StreamHandler()
    handler.setLevel(level)
    
    # Create a formatter with the requested format
    formatter = logging.Formatter('[%(levelname)s | %(asctime)s | %(message)s]')
    handler.setFormatter(formatter)
    
    # Add the handler to the logger
    logger.addHandler(handler)
    
    return logger 