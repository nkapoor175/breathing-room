import datetime

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def now_iso() -> str:
    """Current time as ISO 8601 with the India offset, e.g. 2026-10-28T18:40:02+05:30."""
    return datetime.datetime.now(IST).isoformat(timespec="seconds")
