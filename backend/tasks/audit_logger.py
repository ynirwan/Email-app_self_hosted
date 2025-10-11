# backend/tasks/audit_logger.py - COMPLETE AUDIT & COMPLIANCE LOGGING
"""
Production-ready audit logging system
Comprehensive activity tracking, compliance logging, and audit trails
"""
import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from enum import Enum
from bson import ObjectId
from celery_app import celery_app
from database_pool import get_sync_audit_collection, get_sync_campaigns_collection
from core.campaign_config import settings, get_redis_key
import redis

logger = logging.getLogger(__name__)

class AuditEventType(Enum):
    """Audit event categories"""
    # Campaign events
    CAMPAIGN_CREATED = "campaign_created"
    CAMPAIGN_STARTED = "campaign_started"
    CAMPAIGN_PAUSED = "campaign_paused"
    CAMPAIGN_RESUMED = "campaign_resumed"
    CAMPAIGN_STOPPED = "campaign_stopped"
    CAMPAIGN_COMPLETED = "campaign_completed"
    CAMPAIGN_FAILED = "campaign_failed"
    
    # Email events
    EMAIL_SENT = "email_sent"
    EMAIL_DELIVERED = "email_delivered"
    EMAIL_BOUNCED = "email_bounced"
    EMAIL_FAILED = "email_failed"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_UNSUBSCRIBED = "email_unsubscribed"
    
    # Subscriber events
    SUBSCRIBER_ADDED = "subscriber_added"
    SUBSCRIBER_UPDATED = "subscriber_updated"
    SUBSCRIBER_DELETED = "subscriber_deleted"
    SUBSCRIBER_SUPPRESSED = "subscriber_suppressed"
    SUBSCRIBER_UNSUPPRESSED = "subscriber_unsuppressed"
    
    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    WORKER_STARTED = "worker_started"
    WORKER_STOPPED = "worker_stopped"
    DATABASE_MIGRATION = "database_migration"
    
    # Admin events
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    SETTINGS_CHANGED = "settings_changed"
    TEMPLATE_CREATED = "template_created"
    TEMPLATE_UPDATED = "template_updated"
    TEMPLATE_DELETED = "template_deleted"
    
    # Security events
    AUTHENTICATION_FAILED = "authentication_failed"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    
    # Compliance events
    GDPR_DATA_EXPORT = "gdpr_data_export"
    GDPR_DATA_DELETION = "gdpr_data_deletion"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_WITHDRAWN = "consent_withdrawn"

class AuditSeverity(Enum):
    """Audit event severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AuditLogger:
    """Comprehensive audit logging system"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        self.batch_buffer = []
        self.batch_size = 100
        
    def log_event(self, 
                  event_type: AuditEventType, 
                  details: Dict[str, Any],
                  severity: AuditSeverity = AuditSeverity.INFO,
                  user_id: str = None,
                  campaign_id: str = None,
                  subscriber_id: str = None,
                  ip_address: str = None,
                  user_agent: str = None) -> str:
        """Log an audit event"""
        
        try:
            # Create audit record
            audit_record = {
                "_id": ObjectId(),
                "event_type": event_type.value,
                "severity": severity.value,
                "timestamp": datetime.utcnow(),
                "details": details,
                "context": {
                    "user_id": user_id,
                    "campaign_id": ObjectId(campaign_id) if campaign_id else None,
                    "subscriber_id": subscriber_id,
                    "ip_address": ip_address if not settings.LOG_SENSITIVE_DATA else self._hash_ip(ip_address),
                    "user_agent": user_agent[:500] if user_agent else None  # Truncate long user agents
                },
                "metadata": {
                    "source": "audit_logger",
                    "version": "1.0",
                    "environment": settings.LOG_LEVEL,
                    "node_id": self._get_node_id()
                }
            }
            
            # Add data classification for compliance
            audit_record["data_classification"] = self._classify_audit_data(event_type, details)
            
            # Hash sensitive fields if required
            if settings.LOG_SENSITIVE_DATA == False:
                audit_record = self._sanitize_sensitive_data(audit_record)
            
            # Store audit record
            if settings.ENABLE_AUDIT_LOGGING:
                audit_id = self._store_audit_record(audit_record)
                
                # Cache recent events for quick access
                self._cache_recent_event(audit_record)
                
                # Check for critical events that need immediate attention
                if severity == AuditSeverity.CRITICAL:
                    self._handle_critical_event(audit_record)
                
                return str(audit_id)
            else:
                logger.debug(f"Audit logging disabled - would log: {event_type.value}")
                return "disabled"
                
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")
            # Don't fail the main operation due to audit logging issues
            return "error"
    
    def _store_audit_record(self, audit_record: Dict[str, Any]) -> ObjectId:
        """Store audit record in database"""
        try:
            audit_collection = get_sync_audit_collection()
            result = audit_collection.insert_one(audit_record)
            return result.inserted_id
            
        except Exception as e:
            logger.error(f"Failed to store audit record: {e}")
            # Try to store in Redis as backup
            self._store_audit_backup(audit_record)
            raise
    
    def _store_audit_backup(self, audit_record: Dict[str, Any]):
        """Store audit record in Redis as backup"""
        try:
            backup_key = get_redis_key("audit_backup", str(audit_record["_id"]))
            self.redis_client.setex(
                backup_key,
                86400,  # 24 hours
                json.dumps(audit_record, default=str)
            )
        except Exception as e:
            logger.error(f"Failed to store audit backup: {e}")
    
    def _cache_recent_event(self, audit_record: Dict[str, Any]):
        """Cache recent events for quick retrieval"""
        try:
            # Store in recent events list
            recent_key = get_redis_key("audit_recent", "events")
            event_summary = {
                "id": str(audit_record["_id"]),
                "event_type": audit_record["event_type"],
                "severity": audit_record["severity"],
                "timestamp": audit_record["timestamp"].isoformat(),
                "user_id": audit_record["context"].get("user_id"),
                "campaign_id": str(audit_record["context"]["campaign_id"]) if audit_record["context"].get("campaign_id") else None
            }
            
            # Add to list (keep last 1000 events)
            self.redis_client.lpush(recent_key, json.dumps(event_summary, default=str))
            self.redis_client.ltrim(recent_key, 0, 999)
            self.redis_client.expire(recent_key, 3600)  # 1 hour expiry
            
        except Exception as e:
            logger.error(f"Failed to cache recent event: {e}")
    
    def _handle_critical_event(self, audit_record: Dict[str, Any]):
        """Handle critical audit events that need immediate attention"""
        try:
            critical_key = get_redis_key("audit_critical", str(int(datetime.utcnow().timestamp())))
            self.redis_client.setex(
                critical_key,
                3600,  # 1 hour
                json.dumps({
                    "event_type": audit_record["event_type"],
                    "details": audit_record["details"],
                    "timestamp": audit_record["timestamp"].isoformat(),
                    "context": audit_record["context"]
                }, default=str)
            )
            
            # Log to system logger as well
            logger.critical(f"CRITICAL AUDIT EVENT: {audit_record['event_type']} - {audit_record['details']}")
            
        except Exception as e:
            logger.error(f"Failed to handle critical event: {e}")
    
    def _classify_audit_data(self, event_type: AuditEventType, details: Dict[str, Any]) -> str:
        """Classify audit data for compliance purposes"""
        
        # Personal data events
        personal_data_events = [
            AuditEventType.EMAIL_SENT, AuditEventType.SUBSCRIBER_ADDED,
            AuditEventType.SUBSCRIBER_UPDATED, AuditEventType.GDPR_DATA_EXPORT,
            AuditEventType.GDPR_DATA_DELETION, AuditEventType.EMAIL_OPENED,
            AuditEventType.EMAIL_CLICKED
        ]
        
        if event_type in personal_data_events:
            return "personal_data"
        elif "security" in event_type.value or "authentication" in event_type.value:
            return "security_sensitive"
        elif event_type in [AuditEventType.SYSTEM_STARTUP, AuditEventType.WORKER_STARTED]:
            return "system_operational"
        else:
            return "business_operational"
    
    def _sanitize_sensitive_data(self, audit_record: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or hash sensitive data for GDPR compliance"""
        try:
            sanitized = audit_record.copy()
            
            # Hash email addresses
            if "email" in sanitized["details"]:
                sanitized["details"]["email"] = self._hash_email(sanitized["details"]["email"])
            
            # Hash IP addresses
            if sanitized["context"].get("ip_address"):
                sanitized["context"]["ip_address"] = self._hash_ip(sanitized["context"]["ip_address"])
            
            # Remove user agent details but keep basic info
            if sanitized["context"].get("user_agent"):
                sanitized["context"]["user_agent"] = self._sanitize_user_agent(sanitized["context"]["user_agent"])
            
            return sanitized
            
        except Exception as e:
            logger.error(f"Data sanitization failed: {e}")
            return audit_record
    
    def _hash_email(self, email: str) -> str:
        """Hash email address for privacy"""
        if not email:
            return ""
        return hashlib.sha256(email.lower().encode()).hexdigest()[:16]
    
    def _hash_ip(self, ip_address: str) -> str:
        """Hash IP address for privacy"""
        if not ip_address:
            return ""
        return hashlib.sha256(ip_address.encode()).hexdigest()[:16]
    
    def _sanitize_user_agent(self, user_agent: str) -> str:
        """Sanitize user agent string"""
        if not user_agent:
            return ""
        
        # Extract basic browser info without detailed version
        if "Chrome" in user_agent:
            return "Chrome"
        elif "Firefox" in user_agent:
            return "Firefox"
        elif "Safari" in user_agent:
            return "Safari"
        elif "Edge" in user_agent:
            return "Edge"
        else:
            return "Unknown"
    
    def _get_node_id(self) -> str:
        """Get unique node identifier"""
        try:
            import socket
            return hashlib.md5(socket.gethostname().encode()).hexdigest()[:8]
        except:
            return "unknown"
    
    def search_audit_logs(self, 
                         start_date: datetime = None,
                         end_date: datetime = None,
                         event_types: List[AuditEventType] = None,
                         user_id: str = None,
                         campaign_id: str = None,
                         severity: AuditSeverity = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Search audit logs with filters"""
        try:
            audit_collection = get_sync_audit_collection()
            
            # Build query
            query = {}
            
            # Date range filter
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter["$gte"] = start_date
                if end_date:
                    date_filter["$lte"] = end_date
                query["timestamp"] = date_filter
            
            # Event type filter
            if event_types:
                query["event_type"] = {"$in": [et.value for et in event_types]}
            
            # User filter
            if user_id:
                query["context.user_id"] = user_id
            
            # Campaign filter
            if campaign_id:
                query["context.campaign_id"] = ObjectId(campaign_id)
            
            # Severity filter
            if severity:
                query["severity"] = severity.value
            
            # Execute query
            results = list(audit_collection.find(query)
                          .sort("timestamp", -1)
                          .limit(limit))
            
            # Convert ObjectIds to strings for JSON serialization
            for result in results:
                result["_id"] = str(result["_id"])
                if result["context"].get("campaign_id"):
                    result["context"]["campaign_id"] = str(result["context"]["campaign_id"])
            
            return results
            
        except Exception as e:
            logger.error(f"Audit log search failed: {e}")
            return []
    
    def generate_compliance_report(self, 
                                  start_date: datetime,
                                  end_date: datetime,
                                  report_type: str = "full") -> Dict[str, Any]:
        """Generate compliance report for audit purposes"""
        try:
            audit_collection = get_sync_audit_collection()
            
            # Date range query
            date_query = {
                "timestamp": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
            
            report = {
                "report_type": report_type,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "duration_days": (end_date - start_date).days
                },
                "generated_at": datetime.utcnow().isoformat(),
                "summary": {},
                "details": {}
            }
            
            # Event type summary
            event_type_pipeline = [
                {"$match": date_query},
                {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            
            event_summary = list(audit_collection.aggregate(event_type_pipeline))
            report["summary"]["events_by_type"] = {
                item["_id"]: item["count"] for item in event_summary
            }
            
            # Severity summary
            severity_pipeline = [
                {"$match": date_query},
                {"$group": {"_id": "$severity", "count": {"$sum": 1}}}
            ]
            
            severity_summary = list(audit_collection.aggregate(severity_pipeline))
            report["summary"]["events_by_severity"] = {
                item["_id"]: item["count"] for item in severity_summary
            }
            
            # Daily activity
            daily_pipeline = [
                {"$match": date_query},
                {"$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp"
                        }
                    },
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            
            daily_activity = list(audit_collection.aggregate(daily_pipeline))
            report["details"]["daily_activity"] = daily_activity
            
            # User activity (if tracking users)
            user_pipeline = [
                {"$match": {**date_query, "context.user_id": {"$ne": None}}},
                {"$group": {
                    "_id": "$context.user_id",
                    "event_count": {"$sum": 1},
                    "unique_events": {"$addToSet": "$event_type"}
                }},
                {"$sort": {"event_count": -1}},
                {"$limit": 20}
            ]
            
            user_activity = list(audit_collection.aggregate(user_pipeline))
            report["details"]["top_users"] = user_activity
            
            # GDPR/Compliance specific events
            compliance_events = [
                AuditEventType.GDPR_DATA_EXPORT.value,
                AuditEventType.GDPR_DATA_DELETION.value,
                AuditEventType.CONSENT_GRANTED.value,
                AuditEventType.CONSENT_WITHDRAWN.value,
                AuditEventType.SUBSCRIBER_SUPPRESSED.value
            ]
            
            compliance_count = audit_collection.count_documents({
                **date_query,
                "event_type": {"$in": compliance_events}
            })
            
            report["summary"]["compliance_events"] = compliance_count
            
            # Security events
            security_events = [
                AuditEventType.AUTHENTICATION_FAILED.value,
                AuditEventType.UNAUTHORIZED_ACCESS.value,
                AuditEventType.SUSPICIOUS_ACTIVITY.value,
                AuditEventType.RATE_LIMIT_EXCEEDED.value
            ]
            
            security_count = audit_collection.count_documents({
                **date_query,
                "event_type": {"$in": security_events}
            })
            
            report["summary"]["security_events"] = security_count
            
            # Total events
            total_events = audit_collection.count_documents(date_query)
            report["summary"]["total_events"] = total_events
            
            return report
            
        except Exception as e:
            logger.error(f"Compliance report generation failed: {e}")
            return {"error": str(e)}
    
    def cleanup_old_audit_logs(self, retention_days: int = None):
        """Clean up old audit logs based on retention policy"""
        try:
            if retention_days is None:
                retention_days = settings.AUDIT_LOG_RETENTION_DAYS
            
            audit_collection = get_sync_audit_collection()
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # Delete old logs
            result = audit_collection.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            logger.info(f"Audit log cleanup: {result.deleted_count} old records removed")
            
            return {
                "deleted_count": result.deleted_count,
                "cutoff_date": cutoff_date.isoformat(),
                "retention_days": retention_days
            }
            
        except Exception as e:
            logger.error(f"Audit log cleanup failed: {e}")
            return {"error": str(e)}

# Convenience functions for common audit events
def log_campaign_event(event_type: AuditEventType, campaign_id: str, details: Dict[str, Any], 
                      user_id: str = None):
    """Log a campaign-related audit event"""
    audit_logger.log_event(
        event_type=event_type,
        details=details,
        campaign_id=campaign_id,
        user_id=user_id
    )

def log_email_event(event_type: AuditEventType, campaign_id: str, subscriber_id: str, 
                   email: str, details: Dict[str, Any]):
    """Log an email-related audit event"""
    # Hash email for privacy if needed
    if not settings.LOG_SENSITIVE_DATA:
        details = details.copy()
        details["email_hash"] = audit_logger._hash_email(email)
        if "email" in details:
            del details["email"]
    else:
        details["email"] = email
    
    audit_logger.log_event(
        event_type=event_type,
        details=details,
        campaign_id=campaign_id,
        subscriber_id=subscriber_id
    )

def log_system_event(event_type: AuditEventType, details: Dict[str, Any], 
                    severity: AuditSeverity = AuditSeverity.INFO):
    """Log a system-related audit event"""
    audit_logger.log_event(
        event_type=event_type,
        details=details,
        severity=severity
    )

def log_security_event(event_type: AuditEventType, details: Dict[str, Any], 
                      ip_address: str = None, user_agent: str = None,
                      severity: AuditSeverity = AuditSeverity.WARNING):
    """Log a security-related audit event"""
    audit_logger.log_event(
        event_type=event_type,
        details=details,
        severity=severity,
        ip_address=ip_address,
        user_agent=user_agent
    )

# Celery tasks for audit log management
@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_audit_logs")
def cleanup_audit_logs(self, retention_days: int = None):
    """Celery task to clean up old audit logs"""
    try:
        return audit_logger.cleanup_old_audit_logs(retention_days)
    except Exception as e:
        logger.error(f"Audit cleanup task failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="analytics", name="tasks.generate_daily_compliance_report")
def generate_daily_compliance_report(self):
    """Generate daily compliance report"""
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=1)
        
        report = audit_logger.generate_compliance_report(start_date, end_date, "daily")
        
        # Store report in Redis for quick access
        report_key = get_redis_key("compliance_report", end_date.strftime("%Y-%m-%d"))
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.setex(report_key, 86400 * 7, json.dumps(report, default=str))  # Keep for 7 days
        
        return report
        
    except Exception as e:
        logger.error(f"Daily compliance report generation failed: {e}")
        return {"error": str(e)}

# Global audit logger instance
audit_logger = AuditLogger()

