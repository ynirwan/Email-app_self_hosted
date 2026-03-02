"""
email_merge.py — thin compatibility shim.

FIX C3: field_map values like "standard.first_name" were previously substituted
         literally into the HTML.  Now they are resolved against a (optional)
         subscriber document before substitution.

FIX C4: template_json stores HTML under the key "content", not "html".  Both
         keys are now tried so the function works with existing and new templates.
"""
import re
from typing import Dict, Any, Optional


def _resolve_field(mapped_field: str, subscriber: Optional[Dict[str, Any]]) -> str:
    """Resolve a field_map value (e.g. 'standard.first_name') to a string."""
    if not mapped_field or not subscriber:
        return ""

    if mapped_field == "email":
        return subscriber.get("email", "")

    if mapped_field.startswith("standard."):
        key = mapped_field[len("standard."):]
        return str(subscriber.get("standard_fields", {}).get(key, "") or "")

    if mapped_field.startswith("custom."):
        key = mapped_field[len("custom."):]
        value = subscriber.get("custom_fields", {}).get(key)
        if isinstance(value, (dict, list)):
            return ""
        return str(value or "")

    # Fallback: return the mapped string unchanged (may be a literal default)
    return str(mapped_field)


def merge_template(
    template_json: Dict[str, Any],
    field_map: Dict[str, str],
    subscriber: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Merge a template's HTML with a field_map, optionally resolving subscriber data.

    Parameters
    ----------
    template_json : dict
        The template's content_json document.
    field_map : dict
        Mapping of template placeholder -> subscriber field path or literal value.
    subscriber : dict, optional
        Full subscriber document used to resolve field paths.

    Returns
    -------
    str
        The merged HTML string.
    """
    # FIX C4: try "content" first (current schema), fall back to "html" (legacy)
    html = template_json.get("content") or template_json.get("html", "")

    for placeholder, mapped_field in field_map.items():
        # FIX C3: resolve field paths against the subscriber document
        value = _resolve_field(mapped_field, subscriber) if subscriber else mapped_field
        html = re.sub(r'\{\{\s*' + re.escape(placeholder) + r'\s*\}\}', value, html)

    return html
