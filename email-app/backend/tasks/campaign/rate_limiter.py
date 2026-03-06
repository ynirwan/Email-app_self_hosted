# backend/tasks/rate_limiter.py - COMPLETE RATE LIMITING SYSTEM
"""
Production-ready dynamic rate limiting system
Adapts rates based on success/failure patterns and provider limits
"""
import redis
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
from core.config import settings, get_redis_key
from enum import Enum

logger = logging.getLogger(__name__)

class EmailProvider(Enum):
    """Supported email providers"""
    DEFAULT = "default"
    SENDGRID = "sendgrid"
    SES = "ses"
    MAILGUN = "mailgun"
    SMTP = "smtp"

class RateLimitResult(Enum):
    """Rate limit check results"""
    ALLOWED = "allowed"
    RATE_LIMITED = "rate_limited"
    PROVIDER_THROTTLED = "provider_throttled"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"

class DynamicRateLimiter:
    """Dynamic rate limiter with provider-specific rules"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        
        # Provider-specific rate limits (emails per minute)
        self.provider_limits = {
            EmailProvider.DEFAULT: {"base": 10000, "max": 500, "min": 10},
            EmailProvider.SENDGRID: {"base": 200, "max": 1000, "min": 20},
            EmailProvider.SES: {"base": 300, "max": 1500, "min": 30},
            EmailProvider.MAILGUN: {"base": 150, "max": 750, "min": 15},
            EmailProvider.SMTP: {"base": 50, "max": 200, "min": 5}
        }
    
    def get_provider_from_config(self, email_settings: Dict) -> EmailProvider:
        """Determine email provider from settings"""
        try:
            service_type = email_settings.get("email_service", "smtp").lower()
            
            if "sendgrid" in service_type:
                return EmailProvider.SENDGRID
            elif "ses" in service_type or "amazon" in service_type:
                return EmailProvider.SES
            elif "mailgun" in service_type:
                return EmailProvider.MAILGUN
            elif "smtp" in service_type:
                return EmailProvider.SMTP
            else:
                return EmailProvider.DEFAULT
                
        except Exception as e:
            logger.warning(f"Could not determine provider: {e}")
            return EmailProvider.DEFAULT
    
    def get_current_rate_limit(self, provider: EmailProvider = EmailProvider.DEFAULT) -> int:
        """Get current dynamic rate limit for provider"""
        try:
            # Get cached rate limit
            cache_key = get_redis_key("rate_limit", provider.value)
            cached_rate = self.redis_client.get(cache_key)
            
            if cached_rate:
                return int(cached_rate)
            
            # Calculate new rate based on recent performance
            success_rate = self._calculate_success_rate(provider)
            base_rate = self.provider_limits[provider]["base"]
            max_rate = self.provider_limits[provider]["max"]
            min_rate = self.provider_limits[provider]["min"]
            
            # Adjust rate based on success rate
            if success_rate >= settings.RATE_LIMIT_SUCCESS_THRESHOLD:
                # High success rate - increase rate by 20%
                new_rate = min(max_rate, int(base_rate * 1.2))
            elif success_rate <= settings.RATE_LIMIT_FAILURE_THRESHOLD:
                # Low success rate - decrease rate by 50%
                new_rate = max(min_rate, int(base_rate * 0.5))
            else:
                # Normal success rate - use base rate
                new_rate = base_rate
            
            # Cache the rate for 5 minutes
            self.redis_client.setex(cache_key, 300, new_rate)
            
            logger.info(f"Rate limit for {provider.value}: {new_rate}/min (success rate: {success_rate:.2%})")
            
            return new_rate
            
        except Exception as e:
            logger.error(f"Rate limit calculation failed for {provider.value}: {e}")
            return self.provider_limits[provider]["base"]
    
    def _calculate_success_rate(self, provider: EmailProvider) -> float:
        """Calculate success rate for the provider in the last hour"""
        try:
            # Get success and failure counts from the last hour
            success_key = get_redis_key(f"email_success_{provider.value}", "hourly")
            failure_key = get_redis_key(f"email_failures_{provider.value}", "hourly")
            
            success_count = int(self.redis_client.get(success_key) or 0)
            failure_count = int(self.redis_client.get(failure_key) or 0)
            
            total_count = success_count + failure_count
            
            if total_count == 0:
                return 1.0  # No data - assume good
            
            return success_count / total_count
            
        except Exception as e:
            logger.error(f"Success rate calculation failed: {e}")
            return 1.0  # Default to good rate on error
    
    def can_send_email(self, provider: EmailProvider = EmailProvider.DEFAULT, campaign_id: str = None) -> Tuple[RateLimitResult, Dict]:
        """Check if email can be sent within rate limits"""
        try:
            # Check if circuit breaker is open
            if self._is_circuit_breaker_open(provider):
                return RateLimitResult.CIRCUIT_BREAKER_OPEN, {
                    "reason": "circuit_breaker_open",
                    "provider": provider.value
                }
            
            # Check campaign-specific pause
            if campaign_id and self._is_campaign_rate_limited(campaign_id):
                return RateLimitResult.RATE_LIMITED, {
                    "reason": "campaign_rate_limited",
                    "campaign_id": campaign_id
                }
            
            # Get current rate limit
            rate_limit = self.get_current_rate_limit(provider)
            
            # Check current window usage
            current_minute = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
            window_key = get_redis_key(f"rate_window_{provider.value}", str(current_minute))
            
            # Atomic increment and check
            pipe = self.redis_client.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, settings.RATE_LIMIT_WINDOW_SECONDS)
            results = pipe.execute()
            
            current_count = results[0]
            
            if current_count > rate_limit:
                # Rate limit exceeded
                return RateLimitResult.RATE_LIMITED, {
                    "reason": "rate_limit_exceeded",
                    "current_count": current_count,
                    "rate_limit": rate_limit,
                    "provider": provider.value
                }
            
            # Check for provider-specific throttling patterns
            if self._detect_provider_throttling(provider):
                return RateLimitResult.PROVIDER_THROTTLED, {
                    "reason": "provider_throttling_detected",
                    "provider": provider.value
                }
            
            # All checks passed
            return RateLimitResult.ALLOWED, {
                "current_count": current_count,
                "rate_limit": rate_limit,
                "provider": provider.value
            }
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Fail safe - allow the email but log the error
            return RateLimitResult.ALLOWED, {"error": str(e)}
    
    def _is_circuit_breaker_open(self, provider: EmailProvider) -> bool:
        """Check if circuit breaker is open for provider"""
        try:
            cb_key = get_redis_key(f"circuit_breaker_{provider.value}", "status")
            cb_status = self.redis_client.get(cb_key)
            
            if cb_status == "open":
                # Check if circuit breaker should be closed (timeout expired)
                cb_timeout_key = get_redis_key(f"circuit_breaker_{provider.value}", "timeout")
                timeout_timestamp = self.redis_client.get(cb_timeout_key)
                
                if timeout_timestamp:
                    if time.time() > float(timeout_timestamp):
                        # Circuit breaker timeout expired - close it
                        self.redis_client.delete(cb_key)
                        self.redis_client.delete(cb_timeout_key)
                        logger.info(f"Circuit breaker closed for {provider.value}")
                        return False
                    else:
                        return True
                else:
                    # No timeout set - close circuit breaker
                    self.redis_client.delete(cb_key)
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            return False
    
    def _is_campaign_rate_limited(self, campaign_id: str) -> bool:
        """Check if specific campaign is rate limited"""
        try:
            rate_limit_key = get_redis_key("campaign_rate_limited", campaign_id)
            return self.redis_client.get(rate_limit_key) == "true"
        except:
            return False
    
    def _detect_provider_throttling(self, provider: EmailProvider) -> bool:
        """Detect if provider is throttling based on recent error patterns"""
        try:
            # Look for throttling indicators in recent errors
            throttling_key = get_redis_key(f"throttling_errors_{provider.value}", "recent")
            throttling_count = int(self.redis_client.get(throttling_key) or 0)
            
            # If we've had more than 5 throttling errors in the last 5 minutes
            return throttling_count >= 5
            
        except Exception as e:
            logger.error(f"Throttling detection failed: {e}")
            return False
    
    def record_email_result(self, success: bool, provider: EmailProvider = EmailProvider.DEFAULT, 
                           error_type: str = None, campaign_id: str = None):
        """Record email send result for rate limiting decisions"""
        try:
            current_hour = int(time.time() // 3600)
            
            if success:
                # Record success
                success_key = get_redis_key(f"email_success_{provider.value}", "hourly")
                self.redis_client.incr(success_key)
                self.redis_client.expire(success_key, 3600)
                
                # Reset any circuit breaker on success
                self._reset_circuit_breaker(provider)
                
            else:
                # Record failure
                failure_key = get_redis_key(f"email_failures_{provider.value}", "hourly")
                self.redis_client.incr(failure_key)
                self.redis_client.expire(failure_key, 3600)
                
                # Check if we should open circuit breaker
                self._check_circuit_breaker(provider, error_type)
                
                # Record throttling errors specifically
                if error_type and any(keyword in error_type.lower() for keyword in 
                                     ['throttl', 'rate', 'limit', '429', 'quota']):
                    throttling_key = get_redis_key(f"throttling_errors_{provider.value}", "recent")
                    self.redis_client.incr(throttling_key)
                    self.redis_client.expire(throttling_key, 300)  # 5 minutes
            
            # Store detailed metrics if enabled
            if settings.ENABLE_METRICS_COLLECTION:
                self._store_detailed_metrics(success, provider, error_type, campaign_id)
                
        except Exception as e:
            logger.error(f"Failed to record email result: {e}")
    
    def _reset_circuit_breaker(self, provider: EmailProvider):
        """Reset circuit breaker on successful sends"""
        try:
            cb_key = get_redis_key(f"circuit_breaker_{provider.value}", "status")
            cb_timeout_key = get_redis_key(f"circuit_breaker_{provider.value}", "timeout")
            error_count_key = get_redis_key(f"circuit_breaker_errors_{provider.value}", "count")
            
            self.redis_client.delete(cb_key)
            self.redis_client.delete(cb_timeout_key)
            self.redis_client.delete(error_count_key)
            
        except Exception as e:
            logger.error(f"Circuit breaker reset failed: {e}")
    
    def _check_circuit_breaker(self, provider: EmailProvider, error_type: str = None):
        """Check if circuit breaker should be opened"""
        try:
            error_count_key = get_redis_key(f"circuit_breaker_errors_{provider.value}", "count")
            current_errors = self.redis_client.incr(error_count_key)
            self.redis_client.expire(error_count_key, settings.SMTP_ERROR_WINDOW_SECONDS)
            
            if current_errors >= settings.SMTP_ERROR_THRESHOLD:
                # Open circuit breaker
                cb_key = get_redis_key(f"circuit_breaker_{provider.value}", "status")
                cb_timeout_key = get_redis_key(f"circuit_breaker_{provider.value}", "timeout")
                
                timeout_timestamp = time.time() + settings.SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS
                
                self.redis_client.setex(cb_key, settings.SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS, "open")
                self.redis_client.setex(cb_timeout_key, settings.SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS, 
                                       str(timeout_timestamp))
                
                logger.warning(f"Circuit breaker OPENED for {provider.value} after {current_errors} errors")
                
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
    
    def _store_detailed_metrics(self, success: bool, provider: EmailProvider, 
                               error_type: str = None, campaign_id: str = None):
        """Store detailed metrics for analysis"""
        try:
            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "success": success,
                "provider": provider.value,
                "error_type": error_type,
                "campaign_id": campaign_id
            }
            
            metrics_key = get_redis_key("email_metrics", str(int(time.time())))
            self.redis_client.setex(metrics_key, settings.METRICS_RETENTION_HOURS * 3600, 
                                   json.dumps(metrics))
            
        except Exception as e:
            logger.error(f"Detailed metrics storage failed: {e}")
    
    def get_rate_limit_stats(self, provider: EmailProvider = None) -> Dict:
        """Get comprehensive rate limiting statistics"""
        try:
            stats = {
                "timestamp": datetime.utcnow().isoformat(),
                "providers": {}
            }
            
            providers_to_check = [provider] if provider else list(EmailProvider)
            
            for prov in providers_to_check:
                provider_stats = {
                    "current_rate_limit": self.get_current_rate_limit(prov),
                    "success_rate": self._calculate_success_rate(prov),
                    "circuit_breaker_open": self._is_circuit_breaker_open(prov),
                    "base_limits": self.provider_limits[prov]
                }
                
                # Get current window usage
                current_minute = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
                window_key = get_redis_key(f"rate_window_{prov.value}", str(current_minute))
                current_usage = int(self.redis_client.get(window_key) or 0)
                
                provider_stats["current_window_usage"] = current_usage
                provider_stats["usage_percentage"] = (current_usage / provider_stats["current_rate_limit"]) * 1000
                
                stats["providers"][prov.value] = provider_stats
            
            return stats
            
        except Exception as e:
            logger.error(f"Rate limit stats collection failed: {e}")
            return {"error": str(e)}
    
    def manually_adjust_rate_limit(self, provider: EmailProvider, new_rate: int, duration_minutes: int = 60):
        """Manually set rate limit for a provider"""
        try:
            if new_rate < 1 or new_rate > 10000:
                raise ValueError("Rate limit must be between 1 and 10000")
            
            cache_key = get_redis_key("rate_limit", provider.value)
            self.redis_client.setex(cache_key, duration_minutes * 60, new_rate)
            
            logger.info(f"Manual rate limit set for {provider.value}: {new_rate}/min for {duration_minutes} minutes")
            
            return {
                "provider": provider.value,
                "new_rate": new_rate,
                "duration_minutes": duration_minutes,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Manual rate limit adjustment failed: {e}")
            return {"error": str(e), "success": False}
    
    def cleanup_old_metrics(self):
        """Clean up old rate limiting metrics"""
        try:
            # Clean up email metrics
            pattern = get_redis_key("email_metrics", "*")
            self._cleanup_old_keys(pattern, settings.METRICS_RETENTION_HOURS * 3600)
            
            # Clean up rate windows older than 24 hours
            current_minute = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
            minutes_in_day = 24 * 60
            
            for provider in EmailProvider:
                for i in range(minutes_in_day):
                    old_minute = current_minute - i
                    old_window_key = get_redis_key(f"rate_window_{provider.value}", str(old_minute))
                    self.redis_client.delete(old_window_key)
            
            logger.info("Rate limiting metrics cleanup completed")
            
        except Exception as e:
            logger.error(f"Rate limiting metrics cleanup failed: {e}")
    
    def _cleanup_old_keys(self, pattern: str, max_age_seconds: int):
        """Helper to clean up old Redis keys"""
        current_time = time.time()
        
        for key in self.redis_client.scan_iter(match=pattern):
            try:
                # Extract timestamp from key
                timestamp = int(key.decode().split(':')[-1])
                if current_time - timestamp > max_age_seconds:
                    self.redis_client.delete(key)
            except (ValueError, IndexError):
                continue

# Global rate limiter instance
rate_limiter = DynamicRateLimiter()

