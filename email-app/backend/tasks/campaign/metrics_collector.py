# backend/tasks/metrics_collector.py - COMPLETE METRICS SYSTEM
"""
Production-ready metrics collection system
Comprehensive monitoring for email campaigns, system health, and performance
"""
import logging
import time
import json
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from bson import ObjectId
from celery_app import celery_app
from database import (
    get_sync_campaigns_collection, get_sync_email_logs_collection,
    get_sync_subscribers_collection, get_sync_analytics_collection, initialize_sync_client, get_sync_database
)
from core.config import settings, get_redis_key
import redis

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Comprehensive metrics collection system"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
    
    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system-level metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
            
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            
            # Network metrics (if available)
            try:
                network = psutil.net_io_counters()
                network_metrics = {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                }
            except:
                network_metrics = {}
            
            system_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "cpu": {
                    "usage_percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "load_average": {
                        "1min": load_avg[0],
                        "5min": load_avg[1],
                        "15min": load_avg[2]
                    }
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "usage_percent": memory.percent,
                    "free_percent": 100 - memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "usage_percent": round((disk.used / disk.total) * 100, 2)
                },
                "network": network_metrics
            }
            
            return system_metrics
            
        except Exception as e:
            logger.error(f"System metrics collection failed: {e}")
            return {"error": str(e)}
    
    def collect_celery_metrics(self) -> Dict[str, Any]:
        """Collect Celery worker and queue metrics"""
        try:
            inspect = celery_app.control.inspect()
            
            # Get worker statistics
            stats = inspect.stats()
            active = inspect.active()
            reserved = inspect.reserved()
            registered = inspect.registered()
            
            celery_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "workers": {},
                "queues": {
                    "total_active": 0,
                    "total_reserved": 0,
                    "by_queue": {}
                },
                "tasks": {
                    "registered_count": 0,
                    "registered_tasks": []
                }
            }
            
            # Process worker stats
            if stats:
                for worker, worker_stats in stats.items():
                    pool_info = worker_stats.get("pool", {})
                    rusage_info = worker_stats.get("rusage", {})
                    
                    celery_metrics["workers"][worker] = {
                        "pool_processes": pool_info.get("processes", 0),
                        "pool_max_processes": pool_info.get("max-processes", 0),
                        "pool_max_tasks_per_child": pool_info.get("max-tasks-per-child", 0),
                        "memory_usage": {
                            "rss": rusage_info.get("rss", 0),  # Resident set size
                            "vms": rusage_info.get("vms", 0)   # Virtual memory size
                        },
                        "cpu_time": {
                            "user": rusage_info.get("utime", 0),
                            "system": rusage_info.get("stime", 0)
                        },
                        "total_tasks": worker_stats.get("total", {})
                    }
            
            # Process active tasks
            if active:
                for worker, tasks in active.items():
                    celery_metrics["queues"]["total_active"] += len(tasks)
                    for task in tasks:
                        queue_name = task.get("delivery_info", {}).get("routing_key", "unknown")
                        if queue_name not in celery_metrics["queues"]["by_queue"]:
                            celery_metrics["queues"]["by_queue"][queue_name] = {"active": 0, "reserved": 0}
                        celery_metrics["queues"]["by_queue"][queue_name]["active"] += 1
            
            # Process reserved tasks
            if reserved:
                for worker, tasks in reserved.items():
                    celery_metrics["queues"]["total_reserved"] += len(tasks)
                    for task in tasks:
                        queue_name = task.get("delivery_info", {}).get("routing_key", "unknown")
                        if queue_name not in celery_metrics["queues"]["by_queue"]:
                            celery_metrics["queues"]["by_queue"][queue_name] = {"active": 0, "reserved": 0}
                        celery_metrics["queues"]["by_queue"][queue_name]["reserved"] += 1
            
            # Process registered tasks
            if registered:
                all_registered = set()
                for worker, tasks in registered.items():
                    all_registered.update(tasks)
                
                celery_metrics["tasks"]["registered_count"] = len(all_registered)
                celery_metrics["tasks"]["registered_tasks"] = list(all_registered)
            
            return celery_metrics
            
        except Exception as e:
            logger.error(f"Celery metrics collection failed: {e}")
            return {"error": str(e)}
    
    def collect_email_metrics(self) -> Dict[str, Any]:
        """Collect email campaign metrics"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            email_logs_collection = get_sync_email_logs_collection()
            
            # Time ranges for analysis
            now = datetime.utcnow()
            one_hour_ago = now - timedelta(hours=1)
            twenty_four_hours_ago = now - timedelta(hours=24)
            
            email_metrics = {
                "timestamp": now.isoformat(),
                "campaigns": {
                    "total": 0,
                    "by_status": {},
                    "active_campaigns": 0
                },
                "emails": {
                    "last_hour": {},
                    "last_24_hours": {},
                    "total_processed": 0
                },
                "performance": {
                    "hourly_rate": 0,
                    "daily_rate": 0,
                    "success_rate_24h": 0,
                    "failure_rate_24h": 0
                }
            }
            
            # Campaign statistics
            campaign_stats = list(campaigns_collection.aggregate([
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]))
            
            total_campaigns = 0
            for stat in campaign_stats:
                count = stat["count"]
                email_metrics["campaigns"]["by_status"][stat["_id"]] = count
                total_campaigns += count
                
                if stat["_id"] in ["sending", "scheduled"]:
                    email_metrics["campaigns"]["active_campaigns"] += count
            
            email_metrics["campaigns"]["total"] = total_campaigns
            
            # Email statistics for last hour
            hourly_email_stats = list(email_logs_collection.aggregate([
                {"$match": {"last_attempted_at": {"$gte": one_hour_ago}}},
                {"$group": {"_id": "$latest_status", "count": {"$sum": 1}}}
            ]))
            
            hourly_total = 0
            for stat in hourly_email_stats:
                count = stat["count"]
                email_metrics["emails"]["last_hour"][stat["_id"]] = count
                hourly_total += count
            
            email_metrics["performance"]["hourly_rate"] = hourly_total
            
            # Email statistics for last 24 hours
            daily_email_stats = list(email_logs_collection.aggregate([
                {"$match": {"last_attempted_at": {"$gte": twenty_four_hours_ago}}},
                {"$group": {"_id": "$latest_status", "count": {"$sum": 1}}}
            ]))
            
            daily_total = 0
            daily_success = 0
            daily_failed = 0
            
            for stat in daily_email_stats:
                count = stat["count"]
                status = stat["_id"]
                email_metrics["emails"]["last_24_hours"][status] = count
                daily_total += count
                
                if status in ["sent", "delivered"]:
                    daily_success += count
                elif status in ["failed", "bounced"]:
                    daily_failed += count
            
            email_metrics["performance"]["daily_rate"] = daily_total
            
            if daily_total > 0:
                email_metrics["performance"]["success_rate_24h"] = (daily_success / daily_total) * 100
                email_metrics["performance"]["failure_rate_24h"] = (daily_failed / daily_total) * 100
            
            # Total processed emails
            total_processed = email_logs_collection.count_documents({})
            email_metrics["emails"]["total_processed"] = total_processed
            
            return email_metrics
            
        except Exception as e:
            logger.error(f"Email metrics collection failed: {e}")
            return {"error": str(e)}
    
    def collect_database_metrics(self) -> Dict[str, Any]:
        """Collect database performance metrics"""
        try:
            from database import initialize_sync_client
            
            # Get database connection
            client = initialize_sync_client.get_sync_client()
            db = client.email_marketing
            
            db_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "connection_health": True,
                "collections": {},
                "indexes": {},
                "performance": {}
            }
            
            # Test connection
            start_time = time.time()
            ping_result = client.admin.command("ping")
            ping_time = (time.time() - start_time) * 1000  # milliseconds
            
            db_metrics["performance"]["ping_ms"] = round(ping_time, 2)
            db_metrics["connection_health"] = ping_result.get("ok", 0) == 1
            
            # Collection statistics
            collections_to_check = ["campaigns", "subscribers", "email_logs", "templates", "settings"]
            
            for collection_name in collections_to_check:
                try:
                    collection = db[collection_name]
                    
                    # Document count
                    doc_count = collection.count_documents({})
                    
                    # Collection stats
                    stats = db.command("collStats", collection_name)
                    
                    db_metrics["collections"][collection_name] = {
                        "document_count": doc_count,
                        "size_bytes": stats.get("size", 0),
                        "storage_size_bytes": stats.get("storageSize", 0),
                        "index_count": stats.get("nindexes", 0),
                        "index_size_bytes": stats.get("totalIndexSize", 0),
                        "avg_obj_size_bytes": stats.get("avgObjSize", 0)
                    }
                    
                    # Index information
                    indexes = collection.list_indexes()
                    index_info = []
                    for index in indexes:
                        index_info.append({
                            "name": index.get("name"),
                            "keys": index.get("key"),
                            "unique": index.get("unique", False),
                            "sparse": index.get("sparse", False)
                        })
                    
                    db_metrics["indexes"][collection_name] = index_info
                    
                except Exception as e:
                    logger.warning(f"Failed to get stats for collection {collection_name}: {e}")
                    db_metrics["collections"][collection_name] = {"error": str(e)}
            
            return db_metrics
            
        except Exception as e:
            logger.error(f"Database metrics collection failed: {e}")
            return {"error": str(e)}
    
    def collect_redis_metrics(self) -> Dict[str, Any]:
        """Collect Redis performance metrics"""
        try:
            redis_metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "connection_health": True,
                "performance": {},
                "memory": {},
                "keys": {},
                "operations": {}
            }
            
            # Test connection
            start_time = time.time()
            ping_result = self.redis_client.ping()
            ping_time = (time.time() - start_time) * 1000
            
            redis_metrics["performance"]["ping_ms"] = round(ping_time, 2)
            redis_metrics["connection_health"] = ping_result
            
            # Redis info
            info = self.redis_client.info()
            
            # Memory metrics
            redis_metrics["memory"] = {
                "used_memory_bytes": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak_bytes": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                "memory_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0)
            }
            
            # Key statistics
            redis_metrics["keys"] = {
                "total_keys": info.get("db0", {}).get("keys", 0) if "db0" in info else 0,
                "expired_keys": info.get("expired_keys", 0),
                "evicted_keys": info.get("evicted_keys", 0)
            }
            
            # Operation statistics
            redis_metrics["operations"] = {
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0)
            }
            
            # Calculate hit rate
            hits = redis_metrics["operations"]["keyspace_hits"]
            misses = redis_metrics["operations"]["keyspace_misses"]
            if hits + misses > 0:
                redis_metrics["operations"]["hit_rate_percent"] = (hits / (hits + misses)) * 100
            else:
                redis_metrics["operations"]["hit_rate_percent"] = 0
            
            return redis_metrics
            
        except Exception as e:
            logger.error(f"Redis metrics collection failed: {e}")
            return {"error": str(e)}
    
    def store_metrics(self, metrics: Dict[str, Any], metric_type: str):
        """Store metrics in Redis with TTL"""
        try:
            timestamp = int(time.time())
            metric_key = get_redis_key(f"metrics_{metric_type}", str(timestamp))
            
            # Store with TTL based on retention setting
            self.redis_client.setex(
                metric_key,
                settings.METRICS_RETENTION_HOURS * 3600,
                json.dumps(metrics, default=str)
            )
            
            # Also store as "latest" for quick access
            latest_key = get_redis_key(f"metrics_{metric_type}", "latest")
            self.redis_client.setex(latest_key, 3600, json.dumps(metrics, default=str))
            
        except Exception as e:
            logger.error(f"Failed to store {metric_type} metrics: {e}")
    
    def get_metrics_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Get a summary of metrics for the specified time period"""
        try:
            current_time = time.time()
            start_time = current_time - (hours * 3600)
            
            summary = {
                "period_hours": hours,
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.fromtimestamp(current_time).isoformat(),
                "system": {},
                "email": {},
                "celery": {},
                "database": {},
                "redis": {}
            }
            
            # Collect latest metrics for each type
            metric_types = ["system", "email", "celery", "database", "redis"]
            
            for metric_type in metric_types:
                latest_key = get_redis_key(f"metrics_{metric_type}", "latest")
                latest_data = self.redis_client.get(latest_key)
                
                if latest_data:
                    try:
                        summary[metric_type] = json.loads(latest_data)
                    except json.JSONDecodeError:
                        summary[metric_type] = {"error": "invalid_json"}
                else:
                    summary[metric_type] = {"error": "no_data"}
            
            return summary
            
        except Exception as e:
            logger.error(f"Metrics summary generation failed: {e}")
            return {"error": str(e)}

# Celery tasks for metrics collection
@celery_app.task(bind=True, queue="monitoring", name="tasks.collect_all_metrics")
def collect_all_metrics(self):
    """Collect all system metrics"""
    try:
        collector = MetricsCollector()
        
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "collection_results": {}
        }
        
        # Collect all metric types
        metric_types = {
            "system": collector.collect_system_metrics,
            "celery": collector.collect_celery_metrics,
            "email": collector.collect_email_metrics,
            "database": collector.collect_database_metrics,
            "redis": collector.collect_redis_metrics
        }
        
        for metric_type, collection_func in metric_types.items():
            try:
                metrics = collection_func()
                collector.store_metrics(metrics, metric_type)
                results["collection_results"][metric_type] = {
                    "success": "error" not in metrics,
                    "data_points": len(metrics) if isinstance(metrics, dict) else 0
                }
            except Exception as e:
                logger.error(f"Failed to collect {metric_type} metrics: {e}")
                results["collection_results"][metric_type] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results
        
    except Exception as e:
        logger.error(f"Metrics collection task failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_old_metrics")
def cleanup_old_metrics(self):
    """Clean up old metrics from Redis"""
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        collector = MetricsCollector()
        
        # Clean up metrics older than retention period
        current_time = time.time()
        cutoff_time = current_time - (settings.METRICS_RETENTION_HOURS * 3600)
        
        cleaned_count = 0
        metric_types = ["system", "celery", "email", "database", "redis"]
        
        for metric_type in metric_types:
            pattern = get_redis_key(f"metrics_{metric_type}", "*")
            
            for key in redis_client.scan_iter(match=pattern):
                try:
                    # Skip "latest" keys
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
        
        logger.info(f"Metrics cleanup: {cleaned_count} old metric entries removed")
        
        return {
            "cleaned_metrics": cleaned_count,
            "retention_hours": settings.METRICS_RETENTION_HOURS
        }
        
    except Exception as e:
        logger.error(f"Metrics cleanup failed: {e}")
        return {"error": str(e)}

# Global metrics collector instance
metrics_collector = MetricsCollector()

