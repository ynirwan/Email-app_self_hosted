# backend/tasks/campaign/template_renderer.py
"""
Pure Jinja2 / {{ var }} renderer.

When context contains __field_types__ (set at upload time via registry):
  - Values are already native Python types — no inference needed.
  - Just build recipient sub-dict and dot-notation nesting.

When __field_types__ is absent (old campaigns, no registry):
  - Fall back to value-shape inference (JSON, pipe, numeric detection).

autoescape=False: email HTML we control. True wraps values in Markup,
breaking numeric comparisons like {{ price > 10 }}.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from jinja2 import Environment

logger = logging.getLogger(__name__)

SYSTEM_KEYS = {
    "__field_types__",
    "recipient",
    "unsubscribe_url",
    "subscriber_id",
    "current_date",
    "current_year",
    "sent_at",
    "subscription_date",
}


# ── Inference helpers (fallback only for old campaigns) ───────────────────────


def _try_number(v: str) -> Any:
    try:
        return int(v)
    except (ValueError, TypeError):
        pass
    try:
        return float(v)
    except (ValueError, TypeError):
        pass
    return v


def _try_json(v: str) -> Any:
    s = v.strip()
    if s and s[0] in ("[", "{"):
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass
    return v


def _infer_list(v: str) -> List[Dict]:
    items = []
    for row in v.strip().split(";"):
        row = row.strip()
        if not row or "|" not in row:
            continue
        p = [x.strip() for x in row.split("|")]
        cols = [
            "name",
            "price",
            "on_sale",
            "description",
            "original_price",
            "new",
            "note",
        ]
        obj = {}
        for i, col in enumerate(cols):
            raw = p[i] if i < len(p) else ""
            if col in ("on_sale", "new"):
                obj[col] = raw.lower() in ("true", "1", "yes")
            elif col in ("price", "original_price"):
                obj[col] = _try_number(raw) if raw else 0
            else:
                obj[col] = raw
        for j, extra in enumerate(p[len(cols) :], len(cols)):
            obj[f"col_{j}"] = extra
        items.append(obj)
    return items


def _infer_object(v: str, key_hints: Optional[List[str]] = None) -> Dict:
    keys = key_hints or ["code", "description", "expires_at", "discount", "terms"]
    parts = [x.strip() for x in v.split("|")]
    result = {}
    for i, k in enumerate(keys):
        result[k] = parts[i] if i < len(parts) else ""
    for j, extra in enumerate(parts[len(keys) :], len(keys)):
        result[f"key_{j}"] = extra
    return result


def _infer_value(key: str, value: Any) -> Any:
    """Guess type from value shape. Used only when no registry present."""
    if not isinstance(value, str):
        return value
    s = value.strip()

    # JSON array or object
    parsed = _try_json(s)
    if parsed is not value:
        return parsed

    # Pipe + semicolon → list
    if ";" in s and "|" in s:
        items = _infer_list(s)
        if items:
            return items

    # Pipe only → object (but skip if key looks like a phone or address)
    if "|" in s:
        return _infer_object(s)

    # Pure numeric string (not zip codes — those have leading zeros we must keep)
    if re.match(r"^-?\d+\.?\d*$", s):
        return _try_number(s)

    return s


class TemplateRenderer:
    def __init__(self):
        self.variable_pattern = re.compile(r"\{\{\s*([^}]+)\s*\}\}")
        self.jinja_env = Environment(autoescape=False)

    # ── Public API ─────────────────────────────────────────────────────────────

    def personalize_template(
        self,
        template: Dict[str, Any],
        subscriber_data: Dict[str, Any],
        extra_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        if not template:
            return {"error": "template_missing"}
        try:
            ctx = (
                extra_context
                if extra_context is not None
                else self._build_base_context(subscriber_data, {})
            )
            result = {}
            for field in ("html_content", "text_content", "subject"):
                raw = template.get(field, "")
                result[field] = self._render(raw, ctx) if raw else raw
            return result
        except Exception as e:
            logger.error(f"Template personalization failed: {e}")
            return {
                "html_content": template.get("html_content", ""),
                "text_content": template.get("text_content", ""),
                "subject": template.get("subject", ""),
                "error": str(e),
            }

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _render(self, content: str, context: Dict[str, Any]) -> str:
        if not content:
            return content
        if "{%" in content or "{#" in content:
            try:
                nested = self._build_jinja_context(context)
                return self.jinja_env.from_string(content).render(nested)
            except Exception as e:
                logger.warning(f"Jinja2 render failed ({e}), simple replacement")
        return self._simple_replace(content, context)

    def _simple_replace(self, content: str, context: Dict[str, Any]) -> str:
        def sub(m):
            val = context.get(m.group(1).strip())
            return str(val) if val is not None else m.group(0)

        return self.variable_pattern.sub(sub, content)

    # ── Context building ───────────────────────────────────────────────────────

    def _build_base_context(self, subscriber_data, fallback_values):
        ctx = dict(fallback_values)
        ctx.setdefault("email", subscriber_data.get("email", ""))
        ctx.setdefault(
            "first_name",
            subscriber_data.get("standard_fields", {}).get("first_name", ""),
        )
        ctx.setdefault(
            "last_name", subscriber_data.get("standard_fields", {}).get("last_name", "")
        )
        for k, v in subscriber_data.get("custom_fields", {}).items():
            ctx.setdefault(k, v)
        ctx.update(
            {
                "subscriber_id": str(subscriber_data.get("_id", "")),
                "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "current_year": str(datetime.utcnow().year),
            }
        )
        return ctx

    def _build_jinja_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        field_types = context.get("__field_types__", {})
        has_registry = bool(field_types)

        nested = {}

        if has_registry:
            # ── TYPED PATH: values already converted at upload ─────────────
            # Just copy as-is; no inference.
            for k, v in context.items():
                if k not in SYSTEM_KEYS:
                    nested[k] = v
        else:
            # ── INFERENCE PATH: old campaigns without registry ─────────────
            for k, v in context.items():
                if k not in SYSTEM_KEYS:
                    nested[k] = _infer_value(k, v)

        # Build recipient sub-dict from all flat scalars
        recipient = {}
        for k, v in nested.items():
            if not isinstance(v, (dict, list)):
                recipient[k] = v
        nested["recipient"] = recipient

        # Expand dot-notation keys
        for k, v in list(context.items()):
            if "." in k and k not in SYSTEM_KEYS:
                parts = k.split(".")
                cur = nested
                for part in parts[:-1]:
                    cur = cur.setdefault(part, {})
                cur[parts[-1]] = v

        return nested


template_renderer = TemplateRenderer()
