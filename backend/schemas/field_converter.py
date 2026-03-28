# backend/schemas/field_converter.py
"""
Type conversion applied at upload time.
Values arrive as CSV strings; this module converts them to native Python
types based on the declared FieldType in the list's field registry.

After conversion, values are stored as native types in MongoDB.
The renderer receives them as-is — no type guessing needed.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from schemas.subscriber_schema import (
    CustomFieldDef,
    FieldType,
    ListFieldRegistry,
    STANDARD_FIELD_NAMES,
)

logger = logging.getLogger(__name__)

# Default column names for LIST fields when none declared in registry
DEFAULT_LIST_COLUMNS = [
    "name",
    "price",
    "on_sale",
    "description",
    "original_price",
    "new",
    "note",
]
# Default key names for OBJECT fields
DEFAULT_OBJECT_KEYS = ["code", "description", "expires_at", "discount", "terms"]


def _to_number(v: str) -> Any:
    v = v.strip()
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v  # leave as string if unparseable


def _to_boolean(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "on", "y")


def _to_date(v: str) -> str:
    v = v.strip()
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v  # return original if unparseable


def _to_list(v: str, columns: List[str]) -> List[Dict[str, Any]]:
    """Parse semicolon-separated pipe rows into a list of dicts."""
    if not isinstance(v, str):
        return v if isinstance(v, list) else []
    items = []
    for row in v.strip().split(";"):
        row = row.strip()
        if not row:
            continue
        parts = [p.strip() for p in row.split("|")]
        obj = {}
        for i, col in enumerate(columns):
            if i >= len(parts):
                # default for missing columns
                obj[col] = False if col in ("on_sale", "new") else ""
            elif col in ("on_sale", "new"):
                obj[col] = _to_boolean(parts[i])
            elif col in ("price", "original_price", "qty", "quantity"):
                obj[col] = _to_number(parts[i]) if parts[i] else 0
            else:
                obj[col] = parts[i]
        # any extra pipe columns beyond declared
        for j, extra in enumerate(parts[len(columns) :], start=len(columns)):
            obj[f"col_{j}"] = extra
        items.append(obj)
    return items


def _to_object(v: str, keys: List[str]) -> Dict[str, Any]:
    """Parse single pipe row into a dict."""
    if not isinstance(v, str):
        return v if isinstance(v, dict) else {}
    parts = [p.strip() for p in v.split("|")]
    result = {}
    for i, key in enumerate(keys):
        result[key] = parts[i] if i < len(parts) else ""
    for j, extra in enumerate(parts[len(keys) :], start=len(keys)):
        result[f"key_{j}"] = extra
    return result


def convert_value(value: Any, field_def: CustomFieldDef) -> Any:
    """Convert a raw CSV value to its declared native Python type."""
    if value is None or value == "":
        # Return typed zero/empty rather than raw empty
        if field_def.type == FieldType.NUMBER:
            return 0
        if field_def.type == FieldType.BOOLEAN:
            return False
        if field_def.type == FieldType.LIST:
            return []
        if field_def.type == FieldType.OBJECT:
            return {}
        return ""

    s = str(value)

    if field_def.type == FieldType.STRING:
        return s  # never auto-cast

    if field_def.type == FieldType.NUMBER:
        return _to_number(s)

    if field_def.type == FieldType.BOOLEAN:
        return _to_boolean(s)

    if field_def.type == FieldType.DATE:
        return _to_date(s)

    if field_def.type == FieldType.LIST:
        cols = field_def.columns or DEFAULT_LIST_COLUMNS
        return _to_list(s, cols)

    if field_def.type == FieldType.OBJECT:
        keys = field_def.keys or DEFAULT_OBJECT_KEYS
        return _to_object(s, keys)

    return s  # fallback


def apply_registry(
    raw_fields: Dict[str, Any],
    registry: ListFieldRegistry,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Split raw flat fields dict into (standard_fields, custom_fields)
    applying type conversion per registry.

    raw_fields: flat dict from UploadSubscriber.fields
    Returns: (standard_fields_dict, custom_fields_dict)
    """
    standard: Dict[str, Any] = {}
    custom: Dict[str, Any] = {}

    for key, value in raw_fields.items():
        key = key.strip()

        if key in STANDARD_FIELD_NAMES and key in (registry.standard or []):
            # Standard field — always stored as string (trimmed)
            standard[key] = str(value).strip() if value is not None else ""

        elif key in STANDARD_FIELD_NAMES:
            # Recognised standard field name but not in this registry's standard list
            # Still store it as standard (flexible)
            standard[key] = str(value).strip() if value is not None else ""

        else:
            # Custom field — apply declared type
            field_def = registry.custom.get(key)
            if field_def:
                try:
                    custom[key] = convert_value(value, field_def)
                except Exception as e:
                    logger.warning(
                        f"Type conversion failed for field '{key}': {e} — storing as string"
                    )
                    custom[key] = str(value) if value is not None else ""
            else:
                # Field not in registry — store as string (safe default)
                custom[key] = str(value).strip() if value is not None else ""

    return standard, custom


def registry_to_field_types(registry: ListFieldRegistry) -> Dict[str, str]:
    """
    Flatten registry into {field_key: type_str} for storage in snapshot.
    Used by renderer to skip type guessing.
    """
    types: Dict[str, str] = {}
    for name in registry.standard or []:
        types[name] = FieldType.STRING.value
    for name, defn in (registry.custom or {}).items():
        types[name] = defn.type.value
    return types
