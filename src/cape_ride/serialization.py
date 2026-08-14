"""Stable conversion of typed models to JSON-compatible values."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import cast


def to_jsonable(value: object) -> object:
    """Convert application models without using untyped application dictionaries."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def dumps(value: object) -> str:
    """Render stable, readable JSON."""
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True)


def json_object(value: object) -> dict[str, object]:
    """Narrow a converted model to a JSON object for composed CLI responses."""
    converted = to_jsonable(value)
    if not isinstance(converted, dict):
        raise TypeError("Expected a JSON object")
    return cast(dict[str, object], converted)

