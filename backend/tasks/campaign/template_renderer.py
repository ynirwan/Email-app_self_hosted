# backend/tasks/campaign/template_renderer.py
"""
Pure template personalization engine — no Redis, no DB, no caching.

Replaces template_cache.TemplateProcessor for the send path.
Snapshot architecture means the HTML is already in memory; this module
only handles {{ var }} replacement and Jinja2 rendering.

Used by:
  - tasks/campaign/email_campaign_tasks.py  (campaign sending)
  - tasks/ab_testing.py                     (A/B test sending)
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

from jinja2 import Environment, select_autoescape

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """
    Stateless Jinja2 / {{ var }} renderer.
    No __init__ dependencies — safe to instantiate at module level.
    """

    def __init__(self):
        # Regex for simple {{ var }} patterns
        self.variable_pattern = re.compile(r"\{\{\s*([^}]+)\s*\}\}")
        # Single shared Jinja2 env (thread-safe, stateless)
        self.jinja_env = Environment(autoescape=select_autoescape(["html", "xml"]))

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def personalize_template(
        self,
        template: Dict[str, Any],
        subscriber_data: Dict[str, Any],
        extra_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Render html_content, text_content, subject with subscriber data.

        template       — dict with keys: html_content, text_content, subject
        subscriber_data — subscriber document from MongoDB
        extra_context  — already-built context dict from the task (field_map
                         applied, unsubscribe_url, system fields, etc.)
                         When supplied it is used as-is; subscriber_data is
                         only used to fill gaps not already in extra_context.
        """
        if not template:
            return {"error": "template_missing"}

        try:
            if extra_context is not None:
                context = extra_context
            else:
                context = self._build_context(subscriber_data, {})

            personalized = {}
            for field in ("html_content", "text_content", "subject"):
                raw = template.get(field, "")
                personalized[field] = self._render(raw, context) if raw else raw

            return personalized

        except Exception as e:
            logger.error(f"Template personalization failed: {e}")
            return {
                "html_content": template.get("html_content", ""),
                "text_content": template.get("text_content", ""),
                "subject": template.get("subject", ""),
                "error": str(e),
            }

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNAL
    # ──────────────────────────────────────────────────────────────────────────

    def _build_context(
        self,
        subscriber_data: Dict[str, Any],
        fallback_values: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a flat personalization context from subscriber doc."""
        ctx = dict(fallback_values)

        ctx.setdefault("email", subscriber_data.get("email", ""))
        ctx.setdefault(
            "first_name",
            subscriber_data.get("standard_fields", {}).get("first_name", ""),
        )
        ctx.setdefault(
            "last_name", subscriber_data.get("standard_fields", {}).get("last_name", "")
        )

        for key, value in subscriber_data.get("custom_fields", {}).items():
            ctx.setdefault(key, value)

        ctx.update(
            {
                "subscriber_id": str(subscriber_data.get("_id", "")),
                "subscription_date": str(subscriber_data.get("created_at", "")),
                "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "current_year": str(datetime.utcnow().year),
            }
        )
        return ctx

    def _render(self, content: str, context: Dict[str, Any]) -> str:
        """
        Render a content string.
        Uses Jinja2 when {%…%} or {#…#} tags are present,
        falls back to simple {{ var }} regex replacement.
        """
        if not content:
            return content

        if "{%" in content or "{#" in content:
            try:
                nested = self._build_nested_context(context)
                return self.jinja_env.from_string(content).render(nested)
            except Exception as e:
                logger.warning(
                    f"Jinja2 render failed ({e}), falling back to simple replacement"
                )

        # Simple {{ var }} replacement
        def replace_var(match):
            var = match.group(1).strip()
            val = context.get(var)
            return str(val) if val is not None else match.group(0)

        return self.variable_pattern.sub(replace_var, content)

    def _build_nested_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert dot-notation keys to nested dicts and parse pipe-separated
        string arrays into lists — required for Jinja2 for-loops.
        """
        nested = dict(context)

        # dot notation → nested dicts  e.g. "recipient.name" → {"recipient": {"name": ...}}
        for key, value in list(context.items()):
            if "." in key:
                parts = key.split(".")
                cur = nested
                for part in parts[:-1]:
                    if part not in cur or not isinstance(cur[part], dict):
                        cur[part] = {}
                    cur = cur[part]
                cur[parts[-1]] = value

        # parse  "name|price|on_sale|desc; name2|..."  strings into lists
        for key, value in list(nested.items()):
            if isinstance(value, str) and ";" in value and "|" in value:
                try:
                    items = []
                    for item_str in value.strip().split(";"):
                        item_str = item_str.strip()
                        if item_str and "|" in item_str:
                            p = item_str.split("|")
                            items.append(
                                {
                                    "name": p[0].strip() if len(p) > 0 else "",
                                    "price": p[1].strip() if len(p) > 1 else "",
                                    "on_sale": p[2].strip().lower()
                                    in ("true", "1", "yes")
                                    if len(p) > 2
                                    else False,
                                    "description": p[3].strip() if len(p) > 3 else "",
                                }
                            )
                    if items:
                        nested[key] = items
                except Exception:
                    pass  # leave as string if parsing fails

            # promo object: "code|description|expires_at"
            elif (
                isinstance(value, str)
                and "|" in value
                and ";" not in value
                and key == "promo"
            ):
                try:
                    p = value.split("|")
                    if len(p) >= 2:
                        nested[key] = {
                            "code": p[0].strip(),
                            "description": p[1].strip(),
                            "expires_at": p[2].strip() if len(p) > 2 else "",
                        }
                except Exception:
                    pass

        return nested


# Module-level singleton — import this everywhere
template_renderer = TemplateRenderer()
