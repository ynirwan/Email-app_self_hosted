# backend/tasks/campaign/template_renderer.py
"""
Pure Jinja2 / {{ var }} renderer.

Values are already native Python types (converted at upload time via the
field registry). Build a flat context dict, run Jinja2, done.

autoescape=False: email HTML we control. True wraps values in Markup,
breaking numeric comparisons like {{ price > 10 }}.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict

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
            "last_name",
            subscriber_data.get("standard_fields", {}).get("last_name", ""),
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
        # Values are already native Python types — copy as-is, no inference.
        nested = {k: v for k, v in context.items() if k not in SYSTEM_KEYS}

        # Build recipient sub-dict from all flat scalars
        nested["recipient"] = {
            k: v for k, v in nested.items() if not isinstance(v, (dict, list))
        }

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
