# backend/schemas/field_converter.py
"""
Type conversion applied at upload time.
Values arrive as CSV strings; this module converts them to native Python
types based on the declared FieldType in the list's field registry.

After conversion, values are stored as native types in MongoDB.
The renderer receives them as-is — no type guessing needed.
"""

import logging
from typing import Any, Dict
from datetime import datetime

from schemas.subscriber_schema import (
    CustomFieldDef,
    FieldType,
    ListFieldRegistry,
    STANDARD_FIELD_NAMES,
)

logger = logging.getLogger(__name__)


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


def convert_value(value: Any, field_def: CustomFieldDef) -> Any:
    """Convert a raw CSV value to its declared native Python type."""
    if value is None or value == "":
        if field_def.type == FieldType.NUMBER:
            return 0
        if field_def.type == FieldType.BOOLEAN:
            return False
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

    return s  # fallback for any unrecognized type


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
