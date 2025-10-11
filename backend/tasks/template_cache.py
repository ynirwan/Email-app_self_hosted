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
from database_pool import get_sync_templates_collection
from core.campaign_config import settings, get_redis_key
import redis
import re

logger = logging.getLogger(__name__)

class TemplateProcessor:
    """Template processing and personalization engine"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        self.personalization_cache = {}
        
        # Regex patterns for template variables
        self.variable_pattern = re.compile(r'\{\{\s*([^}]+)\s*\}\}')
        self.conditional_pattern = re.compile(r'\{%\s*if\s+([^%]+)\s*%\}(.*?)\{%\s*endif\s*%\}', re.DOTALL)
        self.loop_pattern = re.compile(r'\{%\s*for\s+(\w+)\s+in\s+([^%]+)\s*%\}(.*?)\{%\s*endfor\s*%\}', re.DOTALL)
    
    def get_template(self, template_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get template with caching support"""
        try:
            # Check cache first unless force refresh
            if not force_refresh and settings.ENABLE_TEMPLATE_CACHING:
                cached_template = self._get_cached_template(template_id)
                if cached_template:
                    return cached_template
            
            # Load from database
            templates_collection = get_sync_templates_collection()
            template = templates_collection.find_one({"_id": ObjectId(template_id)})
            
            if not template:
                logger.warning(f"Template not found: {template_id}")
                return None
            
            # Process and cache template
            processed_template = self._process_template(template)
            
            if settings.ENABLE_TEMPLATE_CACHING:
                self._cache_template(template_id, processed_template)
            
            return processed_template
            
        except Exception as e:
            logger.error(f"Failed to get template {template_id}: {e}")
            return None
    
    def _get_cached_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get template from cache"""
        try:
            cache_key = get_redis_key("template_cache", template_id)
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                template_data = json.loads(cached_data)
                
                # Check if cache is still valid
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
            
            # Extract variables from template content
            html_content = template.get("html_content", "")
            text_content = template.get("text_content", "")
            subject = template.get("subject", "")
            
            # Find all template variables
            variables = set()
            for content in [html_content, text_content, subject]:
                if content:
                    variables.update(self.variable_pattern.findall(content))
            
            processed["required_variables"] = list(variables)
            processed["processed_at"] = datetime.utcnow()
            processed["variable_count"] = len(variables)
            
            # Pre-compile regex patterns for faster personalization
            processed["_compiled_patterns"] = {
                "variables": [(var, re.compile(r'\{\{\s*' + re.escape(var) + r'\s*\}\}')) 
                             for var in variables]
            }
            
            # Check template size
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
            
            # Create personalization context
            context = self._create_personalization_context(subscriber_data, fallback_values)
            
            # Personalize each content field
            content_fields = ["html_content", "text_content", "subject"]
            
            for field in content_fields:
                original_content = template.get(field, "")
                if original_content:
                    personalized_content = self._personalize_content(
                        original_content, 
                        context,
                        template.get("_compiled_patterns", {})
                    )
                    personalized[field] = personalized_content
                else:
                    personalized[field] = original_content
            
            # Add metadata
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
        """Create personalization context from subscriber data"""
        context = {}
        
        # Standard fields
        standard_fields = subscriber_data.get("standard_fields", {})
        context.update({
            "first_name": standard_fields.get("first_name") or fallback_values.get("first_name", ""),
            "last_name": standard_fields.get("last_name") or fallback_values.get("last_name", ""),
            "email": subscriber_data.get("email", ""),
            "full_name": f"{standard_fields.get('first_name', '')} {standard_fields.get('last_name', '')}".strip()
        })
        
        # Custom fields
        custom_fields = subscriber_data.get("custom_fields", {})
        context.update(custom_fields)
        
        # System fields
        context.update({
            "subscriber_id": str(subscriber_data.get("_id", "")),
            "subscription_date": subscriber_data.get("created_at", ""),
            "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "current_year": str(datetime.utcnow().year)
        })
        
        # Apply fallback values for missing fields
        for key, fallback in fallback_values.items():
            if not context.get(key):
                context[key] = fallback
        
        return context
    
    def _personalize_content(self, content: str, context: Dict[str, Any], 
                           compiled_patterns: Dict[str, Any] = None) -> str:
        """Personalize content with context data"""
        try:
            personalized = content
            
            # Use compiled patterns if available for better performance
            if compiled_patterns and "variables" in compiled_patterns:
                for var_name, pattern in compiled_patterns["variables"]:
                    value = context.get(var_name, f"{{{{{var_name}}}}}")  # Keep original if not found
                    if value is not None:
                        personalized = pattern.sub(str(value), personalized)
            else:
                # Fallback to standard regex replacement
                for var_name, value in context.items():
                    if value is not None:
                        pattern = r'\{\{\s*' + re.escape(var_name) + r'\s*\}\}'
                        personalized = re.sub(pattern, str(value), personalized)
            
            # Process conditionals (basic implementation)
            personalized = self._process_conditionals(personalized, context)
            
            return personalized
            
        except Exception as e:
            logger.error(f"Content personalization failed: {e}")
            return content
    
    def _process_conditionals(self, content: str, context: Dict[str, Any]) -> str:
        """Process conditional statements in templates"""
        try:
            # Basic conditional processing: {% if variable %}content{% endif %}
            def replace_conditional(match):
                condition = match.group(1).strip()
                conditional_content = match.group(2)
                
                # Simple condition evaluation
                if condition in context and context[condition]:
                    return conditional_content
                else:
                    return ""
            
            return self.conditional_pattern.sub(replace_conditional, content)
            
        except Exception as e:
            logger.error(f"Conditional processing failed: {e}")
            return content
    
    def validate_template(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Validate template structure and content"""
        try:
            validation_result = {
                "valid": True,
                "warnings": [],
                "errors": [],
                "suggestions": []
            }
            
            # Check required fields
            required_fields = ["name", "subject", "html_content"]
            for field in required_fields:
                if not template.get(field):
                    validation_result["errors"].append(f"Missing required field: {field}")
                    validation_result["valid"] = False
            
            # Check template size
            html_size = len(template.get("html_content", ""))
            if html_size > settings.MAX_TEMPLATE_SIZE_KB * 1024:
                validation_result["warnings"].append(f"Template size ({html_size} bytes) exceeds recommended limit")
            
            # Check for unsubscribe link
            html_content = template.get("html_content", "").lower()
            if "unsubscribe" not in html_content:
                validation_result["warnings"].append("Template should include an unsubscribe link")
            
            # Check for personalization variables
            variables = self.variable_pattern.findall(template.get("html_content", ""))
            if not variables:
                validation_result["suggestions"].append("Consider adding personalization variables like {{first_name}}")
            
            # Check for common issues
            if "{{" in template.get("html_content", "") and "}}" in template.get("html_content", ""):
                unmatched_braces = template.get("html_content", "").count("{{") - template.get("html_content", "").count("}}")
                if unmatched_braces != 0:
                    validation_result["errors"].append("Unmatched template variable braces")
                    validation_result["valid"] = False
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Template validation failed: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "warnings": [],
                "suggestions": []
            }
    
    def get_template_statistics(self, template_id: str) -> Dict[str, Any]:
        """Get usage statistics for a template"""
        try:
            from database_pool import get_sync_campaigns_collection
            
            campaigns_collection = get_sync_campaigns_collection()
            
            # Get campaigns using this template
            campaigns_using_template = campaigns_collection.count_documents({"template_id": template_id})
            
            # Get recent usage
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_campaigns = campaigns_collection.count_documents({
                "template_id": template_id,
                "created_at": {"$gte": thirty_days_ago}
            })
            
            # Get performance stats
            performance_pipeline = [
                {"$match": {"template_id": template_id}},
                {"$group": {
                    "_id": None,
                    "total_sent": {"$sum": "$sent_count"},
                    "total_delivered": {"$sum": "$delivered_count"},
                    "total_failed": {"$sum": "$failed_count"},
                    "avg_sent": {"$avg": "$sent_count"}
                }}
            ]
            
            performance_stats = list(campaigns_collection.aggregate(performance_pipeline))
            performance = performance_stats[0] if performance_stats else {}
            
            return {
                "template_id": template_id,
                "total_campaigns": campaigns_using_template,
                "recent_campaigns_30d": recent_campaigns,
                "performance": {
                    "total_emails_sent": performance.get("total_sent", 0),
                    "total_delivered": performance.get("total_delivered", 0),
                    "total_failed": performance.get("total_failed", 0),
                    "average_sent_per_campaign": round(performance.get("avg_sent", 0), 2),
                    "delivery_rate": (performance.get("total_delivered", 0) / max(performance.get("total_sent", 0), 1)) * 100
                },
                "calculated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Template statistics calculation failed: {e}")
            return {"error": str(e)}
    
    def clear_template_cache(self, template_id: str = None):
        """Clear template cache for specific template or all templates"""
        try:
            if template_id:
                # Clear specific template cache
                cache_key = get_redis_key("template_cache", template_id)
                result = self.redis_client.delete(cache_key)
                logger.info(f"Cleared cache for template {template_id}: {result}")
                return {"cleared": result}
            else:
                # Clear all template caches
                pattern = get_redis_key("template_cache", "*")
                keys = list(self.redis_client.scan_iter(match=pattern))
                if keys:
                    result = self.redis_client.delete(*keys)
                    logger.info(f"Cleared all template caches: {result} keys")
                    return {"cleared": result}
                else:
                    return {"cleared": 0}
                    
        except Exception as e:
            logger.error(f"Template cache clearing failed: {e}")
            return {"error": str(e)}

# Celery tasks for template management
@celery_app.task(bind=True, queue="templates", name="tasks.preload_template_cache")
def preload_template_cache(self, template_ids: List[str] = None):
    """Preload templates into cache"""
    try:
        processor = TemplateProcessor()
        
        if template_ids:
            templates_to_load = template_ids
        else:
            # Load all active templates
            templates_collection = get_sync_templates_collection()
            active_templates = templates_collection.find(
                {"status": {"$ne": "deleted"}},
                {"_id": 1}
            )
            templates_to_load = [str(t["_id"]) for t in active_templates]
        
        loaded_count = 0
        failed_count = 0
        
        for template_id in templates_to_load:
            try:
                template = processor.get_template(template_id, force_refresh=True)
                if template:
                    loaded_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Failed to preload template {template_id}: {e}")
                failed_count += 1
        
        logger.info(f"Template cache preload: {loaded_count} loaded, {failed_count} failed")
        
        return {
            "loaded": loaded_count,
            "failed": failed_count,
            "total_requested": len(templates_to_load)
        }
        
    except Exception as e:
        logger.error(f"Template cache preload failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_template_cache")
def cleanup_template_cache(self):
    """Clean up expired template cache entries"""
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        processor = TemplateProcessor()
        
        pattern = get_redis_key("template_cache", "*")
        expired_count = 0
        total_count = 0
        
        for key in redis_client.scan_iter(match=pattern):
            total_count += 1
            try:
                cached_data = redis_client.get(key)
                if cached_data:
                    template_data = json.loads(cached_data)
                    cached_at = template_data.get("cached_at")
                    
                    if cached_at:
                        cached_time = datetime.fromisoformat(cached_at)
                        if datetime.utcnow() - cached_time > timedelta(seconds=settings.TEMPLATE_CACHE_TTL_SECONDS):
                            redis_client.delete(key)
                            expired_count += 1
                else:
                    # Empty cache entry, remove it
                    redis_client.delete(key)
                    expired_count += 1
                    
            except (json.JSONDecodeError, ValueError):
                # Invalid cache entry, remove it
                redis_client.delete(key)
                expired_count += 1
        
        logger.info(f"Template cache cleanup: {expired_count}/{total_count} entries removed")
        
        return {
            "expired_removed": expired_count,
            "total_checked": total_count
        }
        
    except Exception as e:
        logger.error(f"Template cache cleanup failed: {e}")
        return {"error": str(e)}

# Global template processor instance
template_processor = TemplateProcessor()

