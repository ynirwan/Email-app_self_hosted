# backend/tasks/resource_manager.py - COMPLETE RESOURCE MANAGEMENT
"""
Production-ready resource management for email campaigns
Handles memory monitoring, task limits, and system health
"""
import psutil
import logging
import time
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any
from core.campaign_config import settings, get_redis_key
import redis
import json

logger = logging.getLogger(__name__)

class ResourceManager:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        self.last_health_check = 0
        self.health_check_cache = {}
    
    def check_memory_usage(self) -> Tuple[bool, Dict[str, Any]]:
        """Check system memory usage"""
        try:
            memory = psutil.virtual_memory()
            memory_info = {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent,
                "free_percent": 100 - memory.percent
            }
            
            is_healthy = memory.percent <= settings.MAX_MEMORY_USAGE_PERCENT
            
            if not is_healthy:
                logger.warning(f"High memory usage: {memory.percent}% (limit: {settings.MAX_MEMORY_USAGE_PERCENT}%)")
            
            # Store metrics
            if settings.ENABLE_METRICS_COLLECTION:
                metrics_key = get_redis_key("memory_metrics", str(int(time.time())))
                self.redis_client.setex(metrics_key, settings.METRICS_RETENTION_HOURS * 3600, json.dumps(memory_info))
            
            return is_healthy, memory_info
            
        except Exception as e:
            logger.error(f"Memory check failed: {e}")
            return False, {"error": str(e)}
    
    def check_disk_usage(self) -> Tuple[bool, Dict[str, Any]]:
        """Check disk space availability"""
        try:
            disk = psutil.disk_usage('/')
            disk_info = {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": round((disk.used / disk.total) * 100, 2)
            }
            
            is_healthy = disk_info["used_percent"] < 90  # 90% threshold
            
            if not is_healthy:
                logger.warning(f"High disk usage: {disk_info['used_percent']}%")
            
            return is_healthy, disk_info
            
        except Exception as e:
            logger.error(f"Disk check failed: {e}")
            return False, {"error": str(e)}
    
    def check_cpu_usage(self) -> Tuple[bool, Dict[str, Any]]:
        """Check CPU usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_info = {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            }
            
            is_healthy = cpu_percent < 90  # 90% threshold
            
            if not is_healthy:
                logger.warning(f"High CPU usage: {cpu_percent}%")
            
            return is_healthy, cpu_info
            
        except Exception as e:
            logger.error(f"CPU check failed: {e}")
            return False, {"error": str(e)}
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        current_time = time.time()
        
        # Use cached health check if recent
        if (current_time - self.last_health_check) < settings.HEALTH_CHECK_INTERVAL_SECONDS:
            return self.health_check_cache
        
        health_status = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_healthy": True,
            "checks": {}
        }
        
        # Memory check
        memory_healthy, memory_info = self.check_memory_usage()
        health_status["checks"]["memory"] = {"healthy": memory_healthy, "info": memory_info}
        
        # Disk check
        disk_healthy, disk_info = self.check_disk_usage()
        health_status["checks"]["disk"] = {"healthy": disk_healthy, "info": disk_info}
        
        # CPU check
        cpu_healthy, cpu_info = self.check_cpu_usage()
        health_status["checks"]["cpu"] = {"healthy": cpu_healthy, "info": cpu_info}
        
        # Database connectivity check
        db_healthy, db_info = self.check_database_connectivity()
        health_status["checks"]["database"] = {"healthy": db_healthy, "info": db_info}
        
        # Redis connectivity check
        redis_healthy, redis_info = self.check_redis_connectivity()
        health_status["checks"]["redis"] = {"healthy": redis_healthy, "info": redis_info}
        
        # Overall health
        health_status["overall_healthy"] = all([
            memory_healthy, disk_healthy, cpu_healthy, db_healthy, redis_healthy
        ])
        
        # Cache results
        self.last_health_check = current_time
        self.health_check_cache = health_status
        
        # Store health metrics
        if settings.ENABLE_METRICS_COLLECTION:
            health_key = get_redis_key("health_metrics", str(int(current_time)))
            self.redis_client.setex(health_key, settings.METRICS_RETENTION_HOURS * 3600, json.dumps(health_status))
        
        return health_status
    
    def check_database_connectivity(self) -> Tuple[bool, Dict[str, Any]]:
        """Check database connectivity and performance"""
        try:
            from database_pool import DatabasePool
            
            start_time = time.time()
            client = DatabasePool.get_sync_client()
            result = client.admin.command("ping")
            ping_time = (time.time() - start_time) * 1000  # milliseconds
            
            db_info = {
                "ping_ms": round(ping_time, 2),
                "connection_healthy": ping_time < 100,  # 100ms threshold
                "server_status": "connected"
            }
            
            is_healthy = db_info["connection_healthy"]
            
            return is_healthy, db_info
            
        except Exception as e:
            logger.error(f"Database connectivity check failed: {e}")
            return False, {"error": str(e), "server_status": "disconnected"}
    
    def check_redis_connectivity(self) -> Tuple[bool, Dict[str, Any]]:
        """Check Redis connectivity and performance"""
        try:
            start_time = time.time()
            self.redis_client.ping()
            ping_time = (time.time() - start_time) * 1000  # milliseconds
            
            redis_info = {
                "ping_ms": round(ping_time, 2),
                "connection_healthy": ping_time < 50,  # 50ms threshold
                "server_status": "connected"
            }
            
            is_healthy = redis_info["connection_healthy"]
            
            return is_healthy, redis_info
            
        except Exception as e:
            logger.error(f"Redis connectivity check failed: {e}")
            return False, {"error": str(e), "server_status": "disconnected"}
    
    def get_celery_queue_metrics(self) -> Dict[str, Any]:
        """Get Celery queue and task metrics"""
        try:
            from celery_app import celery_app
            
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            active = inspect.active()
            reserved = inspect.reserved()
            
            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "workers": {},
                "total_active": 0,
                "total_reserved": 0,
                "queue_lengths": {}
            }
            
            if stats:
                for worker, worker_stats in stats.items():
                    metrics["workers"][worker] = {
                        "pool_processes": worker_stats.get("pool", {}).get("processes", 0),
                        "rusage": worker_stats.get("rusage", {}),
                        "total_tasks": worker_stats.get("total", {})
                    }
            
            if active:
                for worker, tasks in active.items():
                    metrics["total_active"] += len(tasks)
            
            if reserved:
                for worker, tasks in reserved.items():
                    metrics["total_reserved"] += len(tasks)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Celery metrics collection failed: {e}")
            return {"error": str(e)}
    
    def can_process_batch(self, batch_size: int, campaign_id: str = None) -> Tuple[bool, str, Dict[str, Any]]:
        """Comprehensive check if system can handle batch processing"""
        
        # Get system health
        health = self.get_system_health()
        
        if not health["overall_healthy"]:
            unhealthy_checks = [check for check, data in health["checks"].items() if not data["healthy"]]
            return False, f"system_unhealthy: {', '.join(unhealthy_checks)}", health
        
        # Check memory specifically
        if not health["checks"]["memory"]["healthy"]:
            return False, "memory_limit_exceeded", health
        
        # Check active task count
        celery_metrics = self.get_celery_queue_metrics()
        if celery_metrics.get("total_active", 0) > settings.MAX_CONCURRENT_TASKS:
            return False, "queue_overloaded", celery_metrics
        
        # Campaign-specific checks
        if campaign_id:
            campaign_pause_key = get_redis_key("campaign_paused", campaign_id)
            if self.redis_client.get(campaign_pause_key):
                return False, "campaign_paused", {"campaign_id": campaign_id}
        
        # All checks passed
        return True, "ok", health
    
    def get_optimal_batch_size(self, requested_size: int, campaign_id: str = None) -> int:
        """Get optimal batch size based on current system resources"""
        
        can_process, reason, metrics = self.can_process_batch(requested_size, campaign_id)
        
        if can_process:
            return requested_size
        
        # Reduce batch size based on the issue
        if "memory" in reason:
            return max(10, requested_size // 4)  # Reduce to 25%
        elif "queue_overloaded" in reason:
            return max(25, requested_size // 2)  # Reduce to 50%
        elif "cpu" in reason:
            return max(50, int(requested_size * 0.75))  # Reduce to 75%
        else:
            return max(10, requested_size // 2)  # Default 50% reduction
    
    def cleanup_old_metrics(self):
        """Clean up old metrics from Redis"""
        try:
            # Clean memory metrics
            pattern = get_redis_key("memory_metrics", "*")
            self._cleanup_keys_by_pattern(pattern, settings.METRICS_RETENTION_HOURS * 3600)
            
            # Clean health metrics
            pattern = get_redis_key("health_metrics", "*")
            self._cleanup_keys_by_pattern(pattern, settings.METRICS_RETENTION_HOURS * 3600)
            
            logger.info("Old metrics cleaned up successfully")
            
        except Exception as e:
            logger.error(f"Metrics cleanup failed: {e}")
    
    def _cleanup_keys_by_pattern(self, pattern: str, max_age_seconds: int):
        """Clean up Redis keys older than max_age"""
        current_time = time.time()
        
        for key in self.redis_client.scan_iter(match=pattern):
            try:
                # Extract timestamp from key
                timestamp = int(key.decode().split(':')[-1])
                if current_time - timestamp > max_age_seconds:
                    self.redis_client.delete(key)
            except (ValueError, IndexError):
                # Skip malformed keys
                continue

# Global resource manager instance
resource_manager = ResourceManager()

