# backend/tasks/campaign/snapshot_utils.py
"""
Snapshot utility — builds a frozen content_snapshot from a template at send time.
Used by:
  - POST /campaigns/{id}/send
  - POST /ab-tests/{id}/start
The snapshot is stored in the campaign / ab-test document so workers never
need to fetch the live template again; edits or deletes have zero impact.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional
from bson import ObjectId

logger = logging.getLogger(__name__)

# Max snapshot size in bytes (500 KB). Enforced before writing to DB.
MAX_SNAPSHOT_BYTES = 500 * 1024


def _extract_html_from_content_json(content_json: Dict[str, Any]) -> str:
    """
    Convert the stored content_json into a plain HTML string,
    mirroring exactly what template_cache.TemplateProcessor._normalize_template_format does.
    """
    mode = content_json.get("mode", "")

    if mode == "drag-drop" and "blocks" in content_json:
        blocks = sorted(content_json["blocks"], key=lambda x: x.get("position", 0))
        body_parts = [b.get("content", "") for b in blocks if b.get("content")]
        body = "\n".join(body_parts)
        return (
            "<!DOCTYPE html>\n<html>\n<head>\n"
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "  <style>body{font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px}</style>\n"
            "</head>\n<body>\n"
            f"{body}\n"
            "</body>\n</html>"
        )

    # html or visual mode
    if mode in ("html", "visual") and "content" in content_json:
        return content_json["content"]

    return ""


def build_snapshot(
    template: Dict[str, Any], campaign: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build a content_snapshot dict from a template document + campaign.

    The snapshot contains everything the worker needs to send every email
    in this campaign — it is written once, never updated.

    Returns a dict ready to be stored in campaign["content_snapshot"].
    Raises ValueError if the template is empty or the snapshot exceeds MAX_SNAPSHOT_BYTES.
    """
    # ── Resolve html_content ──────────────────────────────────────────────────
    html_content = template.get("html_content", "")

    # If the template stores content inside content_json (drag-drop / visual)
    # and html_content is absent, derive it — same logic as template_cache.
    if not html_content:
        content_json = template.get("content_json", {})
        if content_json:
            html_content = _extract_html_from_content_json(content_json)

    if not html_content:
        raise ValueError(
            f"Template '{template.get('name', template.get('_id'))}' "
            "has no renderable HTML content. Cannot create snapshot."
        )

    # ── Resolve text_content ──────────────────────────────────────────────────
    text_content = template.get("text_content", "")

    # ── Subject: campaign overrides template ──────────────────────────────────
    subject = campaign.get("subject") or template.get("subject", "")

    # ── Field map / fallbacks from campaign ──────────────────────────────────
    field_map = campaign.get("field_map", {})
    fallback_values = campaign.get("fallback_values", {})

    # ── Build snapshot ────────────────────────────────────────────────────────
    snapshot = {
        "html_content": html_content,
        "text_content": text_content,
        "subject": subject,
        "field_map": field_map,
        "fallback_values": fallback_values,
        "template_id": str(template.get("_id", "")),
        "template_name": template.get("name", ""),
        "taken_at": datetime.utcnow(),
    }

    # ── Size guard ────────────────────────────────────────────────────────────
    import json

    approx_bytes = len(json.dumps(snapshot, default=str).encode("utf-8"))
    if approx_bytes > MAX_SNAPSHOT_BYTES:
        raise ValueError(
            f"Snapshot size ({approx_bytes:,} bytes) exceeds the "
            f"{MAX_SNAPSHOT_BYTES // 1024} KB limit. "
            "Reduce template HTML size before sending."
        )

    logger.info(
        "Snapshot built",
        extra={
            "template_id": snapshot["template_id"],
            "html_bytes": len(html_content.encode("utf-8")),
            "total_bytes": approx_bytes,
            "field_map_keys": list(field_map.keys()),
        },
    )
    return snapshot
