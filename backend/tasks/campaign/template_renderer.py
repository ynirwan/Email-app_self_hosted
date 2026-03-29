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

KEY FIX (2026-03-28):
  MongoDB may store LIST / OBJECT custom fields in "raw pipe-header" format —
  a list-of-dicts where the first key IS the pipe-joined column names and the
  rest are col_1, col_2, …

  Example stored in DB:
    [{"name|price|on_sale": "Widget", "col_1": "9.99", "col_2": "true"}, …]

  This happens when data was uploaded before the field-type selector existed
  (type defaulted to "string", so _to_list() was never called at ingest).

  _normalize_value() detects and re-maps to proper named dicts so Jinja2
  can access item.name, item.price, item.on_sale etc.
  Single-item pipe-header lists are also unwrapped to plain dicts (OBJECT).
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from jinja2 import Environment, TemplateSyntaxError

logger = logging.getLogger(__name__)

# Keys that are internal markers only — never passed into the Jinja context.
# unsubscribe_url, subscriber_id, current_date, current_year, sent_at, and
# subscription_date are all valid {{ }} template variables and must NOT be here.
SYSTEM_KEYS = {
    "__field_types__",  # internal type registry, not a template variable
    "recipient",  # built fresh from nested scalars in _build_jinja_context
}

# Columns that should be cast to bool / number when normalizing raw pipe-header rows
_BOOL_COLS = {"on_sale", "onsale", "new", "is_new", "verified", "active", "enabled"}
_NUM_COLS = {
    "price",
    "original_price",
    "qty",
    "quantity",
    "amount",
    "discount",
    "index",
}


# ── Pipe-header normalization ─────────────────────────────────────────────────


def _is_pipe_header_dict(d: dict) -> bool:
    """
    True when a dict was stored in raw pipe-header format:
      - Exactly one key contains '|' (the composite column-header key)
      - All other keys match col_N pattern
    """
    if not isinstance(d, dict) or not d:
        return False
    pipe_keys = [k for k in d if "|" in k]
    return len(pipe_keys) == 1


def _safe_number(v: Any) -> Any:
    if v is None or v == "":
        return 0
    s = str(v).strip()
    try:
        return int(s)
    except (ValueError, TypeError):
        pass
    try:
        return float(s)
    except (ValueError, TypeError):
        return v


def _normalize_pipe_header_row(d: dict) -> dict:
    """
    Convert one raw pipe-header dict to a properly named dict.

    Input:
      {"name|price|on_sale|description": "Widget",
       "col_1": "9.99", "col_2": "true", "col_3": "Best seller"}

    Output:
      {"name": "Widget", "price": 9.99, "on_sale": True, "description": "Best seller"}
    """
    pipe_key = next(k for k in d if "|" in k)
    col_names = [c.strip().lower().replace(" ", "_") for c in pipe_key.split("|")]

    # Values: first is the value stored under the composite key, rest are col_1 …
    values = [d[pipe_key]]
    i = 1
    while f"col_{i}" in d:
        values.append(d[f"col_{i}"])
        i += 1

    result = {}
    for idx, col in enumerate(col_names):
        raw = values[idx] if idx < len(values) else ""
        if col in _BOOL_COLS:
            result[col] = str(raw).strip().lower() in ("true", "1", "yes", "on", "y")
        elif col in _NUM_COLS:
            result[col] = _safe_number(raw)
        else:
            result[col] = raw

    # Any extra col_N values beyond declared columns
    for j in range(len(col_names), i):
        result[f"col_{j}"] = d.get(f"col_{j}", "")

    return result


def _normalize_value(value: Any) -> Any:
    """
    Recursively normalize a context value.

    - list of pipe-header dicts  →  list of properly-named dicts  (LIST field)
    - 1-item list of pipe-header →  plain dict                     (OBJECT field)
    - already-clean list / dict  →  returned as-is
    """
    if not isinstance(value, list) or not value:
        return value

    if all(isinstance(item, dict) and _is_pipe_header_dict(item) for item in value):
        normalized = [_normalize_pipe_header_row(item) for item in value]
        # Single-element list → unwrap to dict so {{ promo.code }} works directly
        if len(normalized) == 1:
            return normalized[0]
        return normalized

    # Partially-pipe-header list: normalize what we can, leave the rest
    return [
        _normalize_pipe_header_row(item)
        if isinstance(item, dict) and _is_pipe_header_dict(item)
        else item
        for item in value
    ]


# ── Inference helpers (fallback only for old campaigns without registry) ───────


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
        # Already a native type — normalize pipe-header lists that slipped through
        return _normalize_value(value)

    s = value.strip()

    # JSON array or object
    parsed = _try_json(s)
    if parsed is not value:
        return _normalize_value(parsed)

    # Pipe + semicolon → list of rows
    if ";" in s and "|" in s:
        items = _infer_list(s)
        if items:
            return items

    # Pipe only → object (skip phone / address strings)
    if "|" in s:
        return _infer_object(s)

    # Pure numeric string (keep leading-zero strings like zip codes as strings)
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
        """
        Render template content with partial-block fault isolation.

        Strategy:
        1. Try rendering the whole content in one Jinja2 pass (fast path).
        2. If that fails, split the HTML at Jinja block boundaries
           ({% if %}...{% endif %}, {% for %}...{% endfor %} etc.) and render
           each top-level block independently.  A broken block only kills
           itself — the rest of the email still renders correctly.
        3. Any block that still fails falls back to simple {{ var }} replace.
        """
        if not content:
            return content

        has_jinja = "{%" in content or "{#" in content
        if not has_jinja:
            return self._simple_replace(content, context)

        nested = self._build_jinja_context(context)

        # ── Fast path: try the whole template at once ──────────────────────
        try:
            return self.jinja_env.from_string(content).render(nested)
        except Exception as e:
            logger.warning(
                f"Jinja2 full-render failed ({e}), switching to block-level isolation"
            )

        # ── Fault-isolated path: split at top-level Jinja blocks ──────────
        # Each "segment" is either:
        #   - a plain HTML/text chunk between blocks
        #   - one complete {% tag %}...{% endtag %} block
        # We render each independently so a broken block only fails itself.
        segments = self._split_jinja_blocks(content)
        parts = []
        for seg in segments:
            if "{%" not in seg and "{{" not in seg:
                parts.append(seg)
                continue
            try:
                parts.append(self.jinja_env.from_string(seg).render(nested))
            except Exception as seg_err:
                logger.warning(
                    f"Jinja2 block failed ({seg_err}), using simple {{ }} replace for this block"
                )
                parts.append(self._simple_replace(seg, context))
        return "".join(parts)

    # ── Jinja block splitter ───────────────────────────────────────────────────

    def _split_jinja_blocks(self, content: str) -> list:
        """
        Split content into segments at top-level Jinja block boundaries.

        Top-level block tags: if, for, with, block, macro, call, filter, set
        (and their end tags).  We walk the content looking for {% tag %} that
        opens a new top-level block, collect everything up to its matching
        {% endtag %}, and yield that as one segment.  Plain text between
        blocks is yielded as-is.  Nested blocks are kept together with their
        parent so they still work correctly.

        Example split for:
          <p>Hello {{ name }}</p>
          {% if vip %}
          <p>VIP!</p>
          {% endif %}
          <p>Footer</p>
          {% if broken > %}
          <p>bad</p>
          {% endif %}

        Segments:
          1. '<p>Hello {{ name }}</p>\n'
          2. '{% if vip %}\n<p>VIP!</p>\n{% endif %}'
          3. '\n<p>Footer</p>\n'
          4. '{% if broken > %}\n<p>bad</p>\n{% endif %}'
        """
        import re

        BLOCK_OPEN = re.compile(r"\{%-?\s*(if|for|with|block|macro|call|filter)\b")
        BLOCK_CLOSE = re.compile(
            r"\{%-?\s*(endif|endfor|endwith|endblock|endmacro|endcall|endfilter)\b"
        )
        TAG = re.compile(r"\{%.*?%\}", re.DOTALL)

        segments = []
        pos = 0
        depth = 0
        block_start = None
        text_start = 0

        for m in TAG.finditer(content):
            tag_text = m.group(0)
            if BLOCK_OPEN.match(tag_text):
                if depth == 0:
                    # Flush any plain text before this block
                    if m.start() > text_start:
                        segments.append(content[text_start : m.start()])
                    block_start = m.start()
                depth += 1
            elif BLOCK_CLOSE.match(tag_text):
                if depth > 0:
                    depth -= 1
                    if depth == 0 and block_start is not None:
                        # Flush the complete block (open → close tag inclusive)
                        segments.append(content[block_start : m.end()])
                        block_start = None
                        text_start = m.end()

        # Flush any trailing content after the last block
        if text_start < len(content):
            segments.append(content[text_start:])

        # If nothing was split (no top-level blocks found), return as single segment
        return segments if segments else [content]

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
        field_types = context.get("__field_types__", {})
        has_registry = bool(field_types)

        nested = {}

        if has_registry:
            # ── TYPED PATH: values converted at upload ─────────────────────
            # Still normalize to catch any pipe-header lists that slipped
            # through (e.g. uploaded before the type selector existed).
            for k, v in context.items():
                if k not in SYSTEM_KEYS:
                    nested[k] = _normalize_value(v)
        else:
            # ── INFERENCE PATH: old campaigns without registry ─────────────
            for k, v in context.items():
                if k not in SYSTEM_KEYS:
                    nested[k] = _infer_value(k, v)

        # Build recipient sub-dict from flat scalars (non-list, non-dict values)
        recipient = {}
        for k, v in nested.items():
            if not isinstance(v, (dict, list)):
                recipient[k] = v
            else:
                # Also expose dicts inside recipient so {{ recipient.promo.code }} works
                recipient[k] = v
        nested["recipient"] = recipient

        # Expand dot-notation keys (e.g. "address.city" → nested["address"]["city"])
        for k, v in list(context.items()):
            if "." in k and k not in SYSTEM_KEYS:
                parts = k.split(".")
                cur = nested
                for part in parts[:-1]:
                    cur = cur.setdefault(part, {})
                cur[parts[-1]] = v

        return nested


template_renderer = TemplateRenderer()
