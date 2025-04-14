from datetime import datetime, UTC

def utc_now() -> datetime:
    """Get current UTC datetime in a timezone-aware format"""
    return datetime.now(UTC) 