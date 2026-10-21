"""Input validation. Every function raises ValidationError with a friendly message."""
from __future__ import annotations

from datetime import date, datetime


class ValidationError(ValueError):
    """Raised when user input is invalid. The message is safe to show in the UI."""


def clean_name(value: str, field: str = "Name", max_len: int = 100) -> str:
    value = (value or "").strip()
    if not value:
        raise ValidationError(f"{field} cannot be empty.")
    if len(value) > max_len:
        raise ValidationError(f"{field} must be {max_len} characters or fewer.")
    return value


def parse_date(value, field: str = "Date") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValidationError(f"{field} must be a valid date in YYYY-MM-DD format.")


def check_exam_date(value, today: date | None = None, allow_unchanged: str | None = None) -> str:
    """Exam dates must be valid and not in the past (an unchanged old date is tolerated)."""
    today = today or date.today()
    d = parse_date(value, "Exam date")
    if d < today and (allow_unchanged is None or d.isoformat() != allow_unchanged):
        raise ValidationError("Exam date cannot be in the past.")
    return d.isoformat()


def check_int(value, field: str, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.")
    if not low <= n <= high:
        raise ValidationError(f"{field} must be between {low} and {high}.")
    return n


def check_float(value, field: str, low: float, high: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.")
    if not low <= x <= high:
        raise ValidationError(f"{field} must be between {low} and {high}.")
    return x


def check_status(value: str) -> str:
    if value not in ("pending", "in_progress", "completed"):
        raise ValidationError("Status must be pending, in_progress or completed.")
    return value


def check_not_future(value, field: str = "Date", today: date | None = None) -> str:
    d = parse_date(value, field)
    if d > (today or date.today()):
        raise ValidationError(f"{field} cannot be in the future.")
    return d.isoformat()
