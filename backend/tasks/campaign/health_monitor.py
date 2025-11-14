# backend/tasks/health_monitor.py - COMPLETE HEALTH MONITORING
"""
Production-ready health monitoring system
Comprehensive health checks, alerting, and automatic recovery
"""
import logging
import time
import json
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from celery_app import celery_app
from database import ping_sync_database, initialize_sync_client, ping_sync_database
from core.config import settings, get_redis_key
from .resource_manager import resource_manager
from .metrics_collector import metrics_collector
import redis

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning" 
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class HealthCheck:
    def __init__(self, name: str, check_func, thresholds: Dict[str, float] = None):
        self.name = name
        self.check_func = check_func
        self.thresholds = thresholds or {}
        self.last_check_time = 0
        self.last_result = None

class HealthMonitor:
    """Comprehensive system health monitoring"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        self.health_checks = {}
        self.alert_history = []
        self._register_health_checks()
    
    def _register_health_checks(self):
        """Register all health check functions"""
        
        self.health_checks = {
            "memory_usage": HealthCheck(
                "memory_usage",
                self._check_memory_usage,
                {"warning": 80.0, "critical": 90.0}
            ),
            "cpu_usage": HealthCheck(
                "cpu_usage", 
                self._check_cpu_usage,
                {"warning": 80.0, "critical": 95.0}
            ),
            "disk_usage": HealthCheck(
                "disk_usage",
                self._check_disk_usage,
                {"warning": 85.0, "critical": 95.0}
            ),
            "database_connectivity": HealthCheck(
                "database_connectivity",
                self._check_database_connectivity,
                {"warning": 100.0, "critical": 1000.0}  # ping time in ms
            ),
            "redis_connectivity": HealthCheck(
                "redis_connectivity",
                self._check_redis_connectivity,
                {"warning": 50.0, "critical": 200.0}  # ping time in ms
            ),
            "celery_workers": HealthCheck(
                "celery_workers",
                self._check_celery_workers,
                {"warning": 1, "critical": 0}  # minimum worker count
            ),
            "email_throughput": HealthCheck(
                "email_throughput",
                self._check_email_throughput,
                {"warning": 100, "critical": 10}  # emails per hour minimum
            ),
            "queue_backlog": HealthCheck(
                "queue_backlog",
                self._check_queue_backlog,
                {"warning": 1000, "critical": 5000}  # maximum queued tasks
            ),
            "failed_campaigns": HealthCheck(
                "failed_campaigns",
                self._check_failed_campaigns,
                {"warning": 5, "critical": 10}  # failed campaigns in last hour
            ),
            "smtp_errors": HealthCheck(
                "smtp_errors",
                self._check_smtp_errors,
                {"warning": 50, "critical": 200}  # SMTP errors per hour
            )
        }
    
    def _check_memory_usage(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check system memory usage"""
        try:
            memory = psutil.virtual_memory()
            usage_percent = memory.percent
            
            status = HealthStatus.HEALTHY
            if usage_percent >= self.health_checks["memory_usage"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif usage_percent >= self.health_checks["memory_usage"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            return status, {
                "usage_percent": usage_percent,
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2)
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def _check_cpu_usage(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check system CPU usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            status = HealthStatus.HEALTHY
            if cpu_percent >= self.health_checks["cpu_usage"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif cpu_percent >= self.health_checks["cpu_usage"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            # Get load average if available
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
            
            return status, {
                "usage_percent": cpu_percent,
                "cpu_count": cpu_count,
                "load_average": {
                    "1min": load_avg[0],
                    "5min": load_avg[1], 
                    "15min": load_avg[2]
                }
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def _check_disk_usage(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check disk space usage"""
        try:
            disk = psutil.disk_usage('/')
            usage_percent = (disk.used / disk.total) * 100
            
            status = HealthStatus.HEALTHY
            if usage_percent >= self.health_checks["disk_usage"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif usage_percent >= self.health_checks["disk_usage"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            return status, {
                "usage_percent": round(usage_percent, 2),
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2)
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def _check_database_connectivity(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check database connectivity and performance"""
        try:
            start_time = time.time()
            client = ping_sync_database()
            result = client.admin.command("ping")
            ping_time = (time.time() - start_time) * 1000  # milliseconds
            
            status = HealthStatus.HEALTHY
            if ping_time >= self.health_checks["database_connectivity"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif ping_time >= self.health_checks["database_connectivity"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            return status, {
                "ping_ms": round(ping_time, 2),
                "connection_successful": result.get("ok", 0) == 1,
                "server_status": "connected" if result.get("ok", 0) == 1 else "error"
            }
            
        except Exception as e:
            return HealthStatus.CRITICAL, {
                "error": str(e),
                "connection_successful": False,
                "server_status": "disconnected"
            }
    
    def _check_redis_connectivity(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check Redis connectivity and performance"""
        try:
            start_time = time.time()
            ping_result = self.redis_client.ping()
            ping_time = (time.time() - start_time) * 1000  # milliseconds
            
            status = HealthStatus.HEALTHY
            if ping_time >= self.health_checks["redis_connectivity"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif ping_time >= self.health_checks["redis_connectivity"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            # Get Redis info
            info = self.redis_client.info()
            
            return status, {
                "ping_ms": round(ping_time, 2),
                "connection_successful": ping_result,
                "memory_used_mb": round(info.get("used_memory", 0) / (1024*1024), 2),
                "connected_clients": info.get("connected_clients", 0),
                "operations_per_sec": info.get("instantaneous_ops_per_sec", 0)
            }
            
        except Exception as e:
            return HealthStatus.CRITICAL, {
                "error": str(e),
                "connection_successful": False
            }
    
    def _check_celery_workers(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check Celery worker health"""
        try:
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            active = inspect.active()
            
            worker_count = len(stats) if stats else 0
            total_active_tasks = 0
            
            if active:
                total_active_tasks = sum(len(tasks) for tasks in active.values())
            
            status = HealthStatus.HEALTHY
            if worker_count <= self.health_checks["celery_workers"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif worker_count <= self.health_checks["celery_workers"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            worker_details = {}
            if stats:
                for worker, worker_stats in stats.items():
                    worker_details[worker] = {
                        "status": "online",
                        "pool_processes": worker_stats.get("pool", {}).get("processes", 0),
                        "total_tasks": worker_stats.get("total", {}),
                        "load_avg": worker_stats.get("rusage", {}).get("utime", 0)
                    }
            
            return status, {
                "worker_count": worker_count,
                "total_active_tasks": total_active_tasks,
                "workers": worker_details
            }
            
        except Exception as e:
            return HealthStatus.CRITICAL, {
                "error": str(e),
                "worker_count": 0
            }
    
    def _check_email_throughput(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check email processing throughput"""
        try:
            from database import get_sync_email_logs_collection
            
            email_logs = get_sync_email_logs_collection()
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            
            # Count emails processed in last hour
            emails_last_hour = email_logs.count_documents({
                "last_attempted_at": {"$gte": one_hour_ago}
            })
            
            status = HealthStatus.HEALTHY
            if emails_last_hour <= self.health_checks["email_throughput"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif emails_last_hour <= self.health_checks["email_throughput"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            # Get success rate
            successful_emails = email_logs.count_documents({
                "last_attempted_at": {"$gte": one_hour_ago},
                "latest_status": {"$in": ["sent", "delivered"]}
            })
            
            success_rate = (successful_emails / emails_last_hour * 100) if emails_last_hour > 0 else 0
            
            return status, {
                "emails_per_hour": emails_last_hour,
                "successful_emails": successful_emails,
                "success_rate_percent": round(success_rate, 2),
                "projected_daily_rate": emails_last_hour * 24
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def _check_queue_backlog(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check Celery queue backlog"""
        try:
            inspect = celery_app.control.inspect()
            reserved = inspect.reserved()
            active = inspect.active()
            
            total_queued = 0
            total_active = 0
            
            if reserved:
                total_queued = sum(len(tasks) for tasks in reserved.values())
            
            if active:
                total_active = sum(len(tasks) for tasks in active.values())
            
            total_backlog = total_queued + total_active
            
            status = HealthStatus.HEALTHY
            if total_backlog >= self.health_checks["queue_backlog"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif total_backlog >= self.health_checks["queue_backlog"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            return status, {
                "total_backlog": total_backlog,
                "queued_tasks": total_queued,
                "active_tasks": total_active,
                "queue_utilization_percent": min(100, (total_backlog / settings.MAX_CONCURRENT_TASKS) * 100)
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def _check_failed_campaigns(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check for failed campaigns"""
        try:
            from database import get_sync_campaigns_collection
            
            campaigns = get_sync_campaigns_collection()
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            
            # Count recently failed campaigns
            failed_campaigns = campaigns.count_documents({
                "status": "failed",
                "failed_at": {"$gte": one_hour_ago}
            })
            
            status = HealthStatus.HEALTHY
            if failed_campaigns >= self.health_checks["failed_campaigns"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif failed_campaigns >= self.health_checks["failed_campaigns"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            # Get failure reasons
            failure_reasons = list(campaigns.aggregate([
                {"$match": {"status": "failed", "failed_at": {"$gte": one_hour_ago}}},
                {"$group": {"_id": "$failure_reason", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]))
            
            return status, {
                "failed_campaigns_last_hour": failed_campaigns,
                "failure_reasons": failure_reasons,
                "total_failed_campaigns": campaigns.count_documents({"status": "failed"})
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def _check_smtp_errors(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Check SMTP error rates"""
        try:
            # Check Redis for SMTP error counts
            smtp_error_patterns = ["*smtp_errors*", "*email_failures*", "*circuit_breaker*"]
            smtp_error_count = 0
            circuit_breakers_open = 0
            
            for pattern in smtp_error_patterns:
                keys = list(self.redis_client.scan_iter(match=get_redis_key(pattern, "*")))
                for key in keys:
                    try:
                        if "circuit_breaker" in key.decode() and self.redis_client.get(key) == "open":
                            circuit_breakers_open += 1
                        else:
                            value = self.redis_client.get(key)
                            if value and value.decode().isdigit():
                                smtp_error_count += int(value.decode())
                    except:
                        continue
            
            status = HealthStatus.HEALTHY
            if smtp_error_count >= self.health_checks["smtp_errors"].thresholds["critical"]:
                status = HealthStatus.CRITICAL
            elif smtp_error_count >= self.health_checks["smtp_errors"].thresholds["warning"]:
                status = HealthStatus.WARNING
            
            return status, {
                "smtp_errors_per_hour": smtp_error_count,
                "circuit_breakers_open": circuit_breakers_open,
                "smtp_health_status": "degraded" if circuit_breakers_open > 0 else "healthy"
            }
            
        except Exception as e:
            return HealthStatus.UNKNOWN, {"error": str(e)}
    
    def run_health_check(self, check_name: str) -> Dict[str, Any]:
        """Run a specific health check"""
        if check_name not in self.health_checks:
            return {"error": f"Health check '{check_name}' not found"}
        
        health_check = self.health_checks[check_name]
        
        try:
            start_time = time.time()
            status, details = health_check.check_func()
            check_duration = time.time() - start_time
            
            result = {
                "check_name": check_name,
                "status": status.value,
                "details": details,
                "timestamp": datetime.utcnow().isoformat(),
                "check_duration_ms": round(check_duration * 1000, 2),
                "thresholds": health_check.thresholds
            }
            
            # Store result
            health_check.last_check_time = time.time()
            health_check.last_result = result
            
            return result
            
        except Exception as e:
            logger.error(f"Health check '{check_name}' failed: {e}")
            return {
                "check_name": check_name,
                "status": HealthStatus.UNKNOWN.value,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def run_all_health_checks(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive report"""
        try:
            health_report = {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": HealthStatus.HEALTHY.value,
                "checks": {},
                "summary": {
                    "total_checks": len(self.health_checks),
                    "healthy_count": 0,
                    "warning_count": 0,
                    "critical_count": 0,
                    "unknown_count": 0
                }
            }
            
            # Run each health check
            for check_name in self.health_checks:
                check_result = self.run_health_check(check_name)
                health_report["checks"][check_name] = check_result
                
                # Update summary counts
                status = check_result.get("status", "unknown")
                if status == "healthy":
                    health_report["summary"]["healthy_count"] += 1
                elif status == "warning":
                    health_report["summary"]["warning_count"] += 1
                elif status == "critical":
                    health_report["summary"]["critical_count"] += 1
                else:
                    health_report["summary"]["unknown_count"] += 1
            
            # Determine overall status
            if health_report["summary"]["critical_count"] > 0:
                health_report["overall_status"] = HealthStatus.CRITICAL.value
            elif health_report["summary"]["warning_count"] > 0:
                health_report["overall_status"] = HealthStatus.WARNING.value
            elif health_report["summary"]["unknown_count"] > 0:
                health_report["overall_status"] = HealthStatus.WARNING.value
            
            # Store health report
            self._store_health_report(health_report)
            
            return health_report
            
        except Exception as e:
            logger.error(f"Health check execution failed: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": HealthStatus.UNKNOWN.value,
                "error": str(e)
            }
    
    def _store_health_report(self, health_report: Dict[str, Any]):
        """Store health report in Redis"""
        try:
            # Store latest health report
            latest_key = get_redis_key("health_report", "latest")
            self.redis_client.setex(latest_key, 3600, json.dumps(health_report, default=str))
            
            # Store timestamped health report
            timestamp = int(time.time())
            timestamped_key = get_redis_key("health_report", str(timestamp))
            self.redis_client.setex(timestamped_key, settings.METRICS_RETENTION_HOURS * 3600, 
                                   json.dumps(health_report, default=str))
            
        except Exception as e:
            logger.error(f"Failed to store health report: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status"""
        try:
            latest_key = get_redis_key("health_report", "latest")
            latest_report = self.redis_client.get(latest_key)
            
            if latest_report:
                return json.loads(latest_report)
            else:
                # No cached report, run checks now
                return self.run_all_health_checks()
                
        except Exception as e:
            logger.error(f"Failed to get health status: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": HealthStatus.UNKNOWN.value,
                "error": str(e)
            }

# Celery tasks for health monitoring
@celery_app.task(bind=True, queue="monitoring", name="tasks.run_health_checks")
def run_health_checks(self):
    """Celery task to run all health checks"""
    try:
        monitor = HealthMonitor()
        health_report = monitor.run_all_health_checks()
        
        # Log critical issues
        if health_report.get("overall_status") == "critical":
            critical_checks = [
                name for name, check in health_report.get("checks", {}).items()
                if check.get("status") == "critical"
            ]
            logger.critical(f"CRITICAL HEALTH ISSUES: {', '.join(critical_checks)}")
        
        return health_report
        
    except Exception as e:
        logger.error(f"Health check task failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_health_reports")
def cleanup_health_reports(self):
    """Clean up old health reports"""
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        
        # Clean up health reports older than retention period
        current_time = time.time()
        cutoff_time = current_time - (settings.METRICS_RETENTION_HOURS * 3600)
        
        cleaned_count = 0
        pattern = get_redis_key("health_report", "*")
        
        for key in redis_client.scan_iter(match=pattern):
            try:
                # Skip "latest" key
                if key.decode().endswith(":latest"):
                    continue
                
                # Extract timestamp from key
                timestamp_str = key.decode().split(":")[-1]
                if timestamp_str.isdigit():
                    timestamp = int(timestamp_str)
                    if timestamp < cutoff_time:
                        redis_client.delete(key)
                        cleaned_count += 1
            except (ValueError, UnicodeDecodeError):
                continue
        
        logger.info(f"Health reports cleanup: {cleaned_count} old reports removed")
        
        return {"cleaned_reports": cleaned_count}
        
    except Exception as e:
        logger.error(f"Health reports cleanup failed: {e}")
        return {"error": str(e)}

# Global health monitor instance
health_monitor = HealthMonitor()

