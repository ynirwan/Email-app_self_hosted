# backend/tasks/template_cache.py - COMPLETE TEMPLATE CACHING
"""
Production-ready template caching system
High-performance template loading, caching, and personalization
"""
import logging
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from bson import ObjectId
from celery_app import celery_app
from database import get_sync_templates_collection
from core.config import settings, get_redis_key
import redis
import re
from jinja2 import Template as Jinja2Template, Environment, select_autoescape

logger = logging.getLogger(__name__)

class TemplateProcessor:
    """Template processing and personalization engine"""

    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        self.personalization_cache = {}

        # Regex patterns for template variables
        self.variable_pattern = re.compile(r'\{\{\s*([^}]+)\s*\}\}')
        self.conditional_pattern = re.compile(
            r'\{%\s*if\s+([^%]+)\s*%\}(.*?)\{%\s*endif\s*%\}', re.DOTALL
        )
        self.loop_pattern = re.compile(
            r'\{%\s*for\s+(\w+)\s+in\s+([^%]+)\s*%\}(.*?)\{%\s*endfor\s*%\}', re.DOTALL
        )

    def get_template(self, template_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get template with caching and handle different formats"""
        try:
            if not force_refresh:
                cached = self._get_cached_template(template_id)
                if cached:
                    return cached

            templates_collection = get_sync_templates_collection()
            template = templates_collection.find_one({"_id": ObjectId(template_id)})

            if not template:
                logger.error(f"Template not found: {template_id}")
                return None

            template = self._normalize_template_format(template)
            self._cache_template(template_id, template)
            return self._process_template(template)

        except Exception as e:
            logger.error(f"Failed to get template {template_id}: {e}")
            return None

    def _normalize_template_format(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Convert different template formats to standard format"""
        try:
            if "content_json" in template and not template.get("html_content"):
                content_json = template["content_json"]
                mode = content_json.get("mode", "")

                if mode == "drag-drop" and "blocks" in content_json:
                    html_parts = []
                    blocks = sorted(content_json["blocks"], key=lambda x: x.get("position", 0))
                    for block in blocks:
                        block_type = block.get("type", "text")
                        content = block.get("content", "")
                        styles = block.get("styles", {})
                        attrs = block.get("attrs", {})

                        # Build inline style string from the block's style map
                        style_str = "; ".join(
                            f"{k}: {v}" for k, v in styles.items() if v
                        )
                        style_attr = f' style="{style_str}"' if style_str else ""

                        if block_type == "button":
                            href = attrs.get("href", "#")
                            label = content or attrs.get("label", "Click here")
                            bg = styles.get("background-color", "#007bff")
                            color = styles.get("color", "#ffffff")
                            padding = styles.get("padding", "12px 24px")
                            border_radius = styles.get("border-radius", "4px")
                            html_parts.append(
                                f'<div style="text-align: center; padding: 16px 0;">'
                                f'<a href="{href}" target="_blank" style="display: inline-block;'
                                f' background-color: {bg}; color: {color}; padding: {padding};'
                                f' border-radius: {border_radius}; text-decoration: none;'
                                f' font-weight: bold;">{label}</a></div>'
                            )
                        elif block_type == "image":
                            src = attrs.get("src", content)
                            alt = attrs.get("alt", "")
                            link = attrs.get("href", "")
                            img_tag = f'<img src="{src}" alt="{alt}" style="max-width:100%;{style_str}">'
                            if link:
                                html_parts.append(
                                    f'<div style="text-align: center;">'
                                    f'<a href="{link}">{img_tag}</a></div>'
                                )
                            else:
                                html_parts.append(f'<div style="text-align: center;">{img_tag}</div>')
                        elif block_type == "divider":
                            color = styles.get("border-color", "#e0e0e0")
                            html_parts.append(
                                f'<hr style="border: none; border-top: 1px solid {color};'
                                f' margin: 16px 0;">'
                            )
                        elif block_type == "spacer":
                            height = styles.get("height", "24px")
                            html_parts.append(f'<div style="height: {height};"></div>')
                        elif content:
                            # text / html / heading blocks – emit as-is with block styles
                            html_parts.append(f'<div{style_attr}>{content}</div>')

                    body_content = "\n".join(html_parts)
                    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
    </style>
</head>
<body>
{body_content}
</body>
</html>"""
                    template["html_content"] = html_content
                    template["text_content"] = ""
                    logger.info(f"Converted drag-drop template ({len(blocks)} blocks)")

                elif mode in ["html", "visual"] and "content" in content_json:
                    template["html_content"] = content_json["content"]
                    template["text_content"] = ""
                    logger.info(f"Using {mode} mode template")
            return template

        except Exception as e:
            logger.error(f"Template normalization failed: {e}")
            return template

    def _get_cached_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get template from cache"""
        try:
            cache_key = get_redis_key("template_cache", template_id)
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                template_data = json.loads(cached_data)
                cached_at = template_data.get("cached_at")
                if cached_at:
                    cached_time = datetime.fromisoformat(cached_at)
                    if datetime.utcnow() - cached_time < timedelta(seconds=settings.TEMPLATE_CACHE_TTL_SECONDS):
                        logger.debug(f"Template cache hit: {template_id}")
                        return template_data.get("template")
            return None

        except Exception as e:
            logger.error(f"Template cache retrieval failed for {template_id}: {e}")
            return None

    def _cache_template(self, template_id: str, template: Dict[str, Any]):
        """Cache processed template"""
        try:
            cache_key = get_redis_key("template_cache", template_id)
            cache_data = {
                "template": template,
                "cached_at": datetime.utcnow().isoformat(),
                "cache_version": 1
            }
            self.redis_client.setex(
                cache_key,
                settings.TEMPLATE_CACHE_TTL_SECONDS,
                json.dumps(cache_data, default=str)
            )
            logger.debug(f"Template cached: {template_id}")

        except Exception as e:
            logger.error(f"Template caching failed for {template_id}: {e}")

    def _process_template(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Process template for optimization"""
        try:
            processed = template.copy()
            html_content = template.get("html_content", "")
            text_content = template.get("text_content", "")
            subject = template.get("subject", "")

            variables = set()
            for content in [html_content, text_content, subject]:
                if content:
                    variables.update(self.variable_pattern.findall(content))

            processed["required_variables"] = list(variables)
            processed["processed_at"] = datetime.utcnow()
            processed["variable_count"] = len(variables)

            processed["_compiled_patterns"] = {
                "variables": [
                    (var, re.compile(r'\{\{\s*' + re.escape(var) + r'\s*\}\}')) for var in variables
                ]
            }

            content_size = len(html_content) + len(text_content) + len(subject)
            if content_size > settings.MAX_TEMPLATE_SIZE_KB * 1024:
                logger.warning(f"Template {template.get('_id')} exceeds size limit: {content_size} bytes")
                processed["size_warning"] = True

            return processed

        except Exception as e:
            logger.error(f"Template processing failed: {e}")
            return template

    def personalize_template(self, template: Dict[str, Any], subscriber_data: Dict[str, Any],
                            fallback_values: Dict[str, Any] = None) -> Dict[str, Any]:
        """Personalize template with subscriber data"""
        try:
            if not template:
                return {"error": "template_missing"}

            fallback_values = fallback_values or {}
            personalized = {}
            context = self._create_personalization_context(subscriber_data, fallback_values)
            content_fields = ["html_content", "text_content", "subject"]

            for field in content_fields:
                original_content = template.get(field, "")
                if original_content:
                    personalized_content = self._personalize_content(
                        original_content, context, template.get("_compiled_patterns", {})
                    )
                    personalized[field] = personalized_content
                else:
                    personalized[field] = original_content

            personalized.update({
                "template_id": str(template.get("_id", "")),
                "template_name": template.get("name", ""),
                "personalized_at": datetime.utcnow().isoformat(),
                "subscriber_id": subscriber_data.get("_id", ""),
                "personalization_applied": len([v for v in context.values() if v is not None])
            })

            return personalized

        except Exception as e:
            logger.error(f"Template personalization failed: {e}")
            return {
                "html_content": template.get("html_content", ""),
                "text_content": template.get("text_content", ""),
                "subject": template.get("subject", ""),
                "error": str(e)
            }

    def _create_personalization_context(self, subscriber_data: Dict[str, Any],
                                        fallback_values: Dict[str, Any]) -> Dict[str, Any]:
        """Create base personalization context"""
        context = dict(fallback_values)

        if "email" not in context:
            context["email"] = subscriber_data.get("email", "")
        if "first_name" not in context:
            context["first_name"] = subscriber_data.get("standard_fields", {}).get("first_name", "")
        if "last_name" not in context:
            context["last_name"] = subscriber_data.get("standard_fields", {}).get("last_name", "")

        for key, value in subscriber_data.get("custom_fields", {}).items():
            if key not in context:
                context[key] = value

        context.update({
            "subscriber_id": str(subscriber_data.get("_id", "")),
            "subscription_date": str(subscriber_data.get("created_at", "")),
            "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "current_year": str(datetime.utcnow().year)
        })
        return context

    def _personalize_content(self, content: str, context: Dict[str, Any],
                            compiled_patterns: Dict[str, Any] = None) -> str:
        """Personalize content with context data - supports both {{ var }} and Jinja2 syntax.

        FIX C2: The simple regex path used to call str() on list/dict values producing
                 raw Python repr in emails.  Complex types are now skipped in the simple
                 path — use {% for %} / {{ var }} inside Jinja2 blocks for those.
        FIX H3: autoescape disabled so custom fields that intentionally contain HTML
                 are not entity-encoded in the output.
        """
        try:
            if not content:
                return content

            # Use Jinja2 whenever any template syntax is present, including plain {{ }}.
            # This ensures lists/dicts are always handled by the proper engine rather than
            # by the unsafe str() fallback in the simple replacement path.
            has_template_syntax = '{%' in content or '{#' in content or '{{' in content

            if has_template_syntax:
                try:
                    nested_context = self._build_nested_context(context)

                    # autoescape=False: custom fields may contain intentional HTML.
                    # Sanitise untrusted user input at ingestion time, not render time.
                    jinja_env = Environment(autoescape=False)
                    jinja_tpl = jinja_env.from_string(content)
                    personalized = jinja_tpl.render(nested_context)
                    logger.info("✅ Rendered template using Jinja2 engine")
                    return personalized
                except Exception as e:
                    logger.error(f"Jinja2 rendering failed: {e}, falling back to simple replacement")
                    # Fall through to simple scalar replacement only

            # Safe fallback: replace only scalar {{ var }} tokens.
            # Lists and dicts are deliberately skipped to avoid Python repr() garbage.
            personalized = content

            if compiled_patterns and "variables" in compiled_patterns:
                for var_name, pattern in compiled_patterns["variables"]:
                    var_name = var_name.strip()
                    value = context.get(var_name)
                    if value is None or isinstance(value, (dict, list)):
                        continue  # leave placeholder intact
                    personalized = pattern.sub(str(value), personalized)
            else:
                for var_name, value in context.items():
                    if value is None or isinstance(value, (dict, list)):
                        continue
                    pattern = r'\{\{\s*' + re.escape(str(var_name)) + r'\s*\}\}'
                    personalized = re.sub(pattern, str(value), personalized)
            return personalized

        except Exception as e:
            logger.error(f"Content personalization failed: {e}")
            return content

    def _build_nested_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Build nested objects from dot notation keys and parse string arrays"""
        nested = dict(context)  # Start with flat context

        for key, value in context.items():
            if '.' in key:
                # Split "recipient.name" → ["recipient", "name"]
                parts = key.split('.')
                # Create/update nested structure
                current = nested
                for i, part in enumerate(parts[:-1]):
                    if part not in current or not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]
                # Set the final value
                current[parts[-1]] = value
        
        # Parse string arrays into actual lists for Jinja2 for loops
        for key, value in list(nested.items()):
            if isinstance(value, str) and ';' in value and '|' in value:
                # Format: "name|price|on_sale|description; name2|price2|..."
                try:
                    parsed_items = []
                    items_str = value.strip()
                    if items_str:
                        for item_str in items_str.split(';'):
                            item_str = item_str.strip()
                            if item_str and '|' in item_str:
                                parts = item_str.split('|')
                                if len(parts) >= 2:
                                    item_obj = {
                                        'name': parts[0].strip() if len(parts) > 0 else '',
                                        'price': parts[1].strip() if len(parts) > 1 else '',
                                        'on_sale': parts[2].strip().lower() in ('true', '1', 'yes') if len(parts) > 2 else False,
                                        'description': parts[3].strip() if len(parts) > 3 else ''
                                    }
                                    parsed_items.append(item_obj)
                    if parsed_items:
                        nested[key] = parsed_items
                        logger.info(f"✅ Parsed '{key}' from string to {len(parsed_items)} items for Jinja2 loop")
                except Exception as e:
                    logger.warning(f"Failed to parse string array for '{key}': {e}")
            
            # Also handle promo object format: "code|description|expires_at"
            elif isinstance(value, str) and '|' in value and ';' not in value and key == 'promo':
                try:
                    parts = value.split('|')
                    if len(parts) >= 2:
                        nested[key] = {
                            'code': parts[0].strip() if len(parts) > 0 else '',
                            'description': parts[1].strip() if len(parts) > 1 else '',
                            'expires_at': parts[2].strip() if len(parts) > 2 else ''
                        }
                        logger.info(f"✅ Parsed 'promo' from string to object")
                except Exception as e:
                    logger.warning(f"Failed to parse promo object: {e}")
        
        logger.info(f"🔍 Nested context keys: {list(nested.keys())[:15]}")
        if 'items' in nested:
            logger.info(f"🔍 Items type: {type(nested['items'])}")
            if isinstance(nested['items'], list):
                logger.info(f"🔍 Items count: {len(nested['items'])}")
            else:
                logger.info(f"🔍 Items value: {str(nested['items'])[:100]}")
        
        return nested

    def _process_conditionals(self, content: str, context: Dict[str, Any]) -> str:
        """Process conditional statements"""
        try:
            def replace_conditional(match):
                condition = match.group(1).strip()
                conditional_content = match.group(2)
                if condition in context and context[condition]:
                    return conditional_content
                return ""

            return self.conditional_pattern.sub(replace_conditional, content)

        except Exception as e:
            logger.error(f"Conditional processing failed: {e}")
            return content

    def validate_template(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Validate template structure"""
        try:
            result = {"valid": True, "warnings": [], "errors": [], "suggestions": []}
            required_fields = ["name", "subject", "html_content"]
            for f in required_fields:
                if not template.get(f):
                    result["errors"].append(f"Missing required field: {f}")
                    result["valid"] = False

            html_size = len(template.get("html_content", ""))
            if html_size > settings.MAX_TEMPLATE_SIZE_KB * 1024:
                result["warnings"].append(f"Template size ({html_size} bytes) exceeds recommended limit")

            html_content = template.get("html_content", "").lower()
            if "unsubscribe" not in html_content:
                result["warnings"].append("Template should include an unsubscribe link")

            variables = self.variable_pattern.findall(template.get("html_content", ""))
            if not variables:
                result["suggestions"].append("Consider adding personalization variables like {{first_name}}")

            if "{{" in template.get("html_content", "") and "}}" in template.get("html_content", ""):
                unmatched_braces = template.get("html_content", "").count("{{") - template.get("html_content", "").count("}}")
                if unmatched_braces != 0:
                    result["errors"].append("Unmatched template variable braces")
                    result["valid"] = False

            return result

        except Exception as e:
            logger.error(f"Template validation failed: {e}")
            return {"valid": False, "errors": [f"Validation error: {str(e)}"], "warnings": [], "suggestions": []}

    def get_template_statistics(self, template_id: str) -> Dict[str, Any]:
        """Get usage statistics"""
        try:
            from database import get_sync_campaigns_collection
            campaigns_collection = get_sync_campaigns_collection()

            campaigns_using_template = campaigns_collection.count_documents({"template_id": template_id})
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_campaigns = campaigns_collection.count_documents({
                "template_id": template_id,
                "created_at": {"$gte": thirty_days_ago}
            })

            pipeline = [
                {"$match": {"template_id": template_id}},
                {"$group": {
                    "_id": None,
                    "total_sent": {"$sum": "$sent_count"},
                    "total_delivered": {"$sum": "$delivered_count"},
                    "total_failed": {"$sum": "$failed_count"},
                    "avg_sent": {"$avg": "$sent_count"}
                }}
            ]

            stats = list(campaigns_collection.aggregate(pipeline))
            perf = stats[0] if stats else {}

            return {
                "template_id": template_id,
                "total_campaigns": campaigns_using_template,
                "recent_campaigns_30d": recent_campaigns,
                "performance": {
                    "total_emails_sent": perf.get("total_sent", 0),
                    "total_delivered": perf.get("total_delivered", 0),
                    "total_failed": perf.get("total_failed", 0),
                    "average_sent_per_campaign": round(perf.get("avg_sent", 0), 2),
                    "delivery_rate": (perf.get("total_delivered", 0) / max(perf.get("total_sent", 1), 1)) * 100
                },
                "calculated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Template statistics calculation failed: {e}")
            return {"error": str(e)}

    def clear_template_cache(self, template_id: str = None):
        """Clear cache"""
        try:
            if template_id:
                cache_key = get_redis_key("template_cache", template_id)
                result = self.redis_client.delete(cache_key)
                logger.info(f"Cleared cache for template {template_id}: {result}")
                return {"cleared": result}
            else:
                pattern = get_redis_key("template_cache", "*")
                keys = list(self.redis_client.scan_iter(match=pattern))
                if keys:
                    result = self.redis_client.delete(*keys)
                    logger.info(f"Cleared all template caches: {result} keys")
                    return {"cleared": result}
                return {"cleared": 0}
        except Exception as e:
            logger.error(f"Template cache clearing failed: {e}")
            return {"error": str(e)}

@celery_app.task(bind=True, queue="templates", name="tasks.preload_template_cache")
def preload_template_cache(self, template_ids: List[str] = None):
    """Preload templates into cache"""
    try:
        processor = TemplateProcessor()
        if template_ids:
            templates_to_load = template_ids
        else:
            templates_collection = get_sync_templates_collection()
            active_templates = templates_collection.find({"status": {"$ne": "deleted"}}, {"_id": 1})
            templates_to_load = [str(t["_id"]) for t in active_templates]

        loaded = failed = 0
        for tid in templates_to_load:
            try:
                template = processor.get_template(tid, force_refresh=True)
                if template:
                    loaded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to preload template {tid}: {e}")
                failed += 1

        logger.info(f"Template cache preload: {loaded} loaded, {failed} failed")
        return {"loaded": loaded, "failed": failed, "total_requested": len(templates_to_load)}

    except Exception as e:
        logger.error(f"Template cache preload failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_template_cache")
def cleanup_template_cache(self):
    """Clean up expired template cache entries"""
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        pattern = get_redis_key("template_cache", "*")
        expired = total = 0

        for key in redis_client.scan_iter(match=pattern):
            total += 1
            try:
                cached_data = redis_client.get(key)
                if cached_data:
                    template_data = json.loads(cached_data)
                    cached_at = template_data.get("cached_at")
                    if cached_at:
                        cached_time = datetime.fromisoformat(cached_at)
                        if datetime.utcnow() - cached_time > timedelta(seconds=settings.TEMPLATE_CACHE_TTL_SECONDS):
                            redis_client.delete(key)
                            expired += 1
                else:
                    redis_client.delete(key)
                    expired += 1
            except (json.JSONDecodeError, ValueError):
                redis_client.delete(key)
                expired += 1

        logger.info(f"Template cache cleanup: {expired}/{total} entries removed")
        return {"expired_removed": expired, "total_checked": total}

    except Exception as e:
        logger.error(f"Template cache cleanup failed: {e}")
        return {"error": str(e)}

template_processor = TemplateProcessor()
