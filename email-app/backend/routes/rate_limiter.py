# app/services/rate_limiter.py
import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Deque
import logging

class RateLimiter:
    def __init__(self):
        self.counters: Dict[str, Dict[str, Deque]] = defaultdict(lambda: {
            'minute': deque(),
            'hour': deque(), 
            'day': deque()
        })
        self.limits = {
            'per_minute': 100,
            'per_hour': 3600,
            'per_day': 50000
        }
    
    async def update_limits(self, new_limits: dict):
        """Update rate limits from settings"""
        self.limits = {
            'per_minute': new_limits.get('per_minute', 100),
            'per_hour': new_limits.get('per_hour', 3600),
            'per_day': new_limits.get('per_day', 50000)
        }
        logging.info(f"Rate limits updated: {self.limits}")
    
    async def check_rate_limit(self, user_id: str = "global") -> dict:
        """Check if sending is within rate limits"""
        now = time.time()
        counters = self.counters[user_id]
        
        # Clean old entries and count current usage
        self._clean_old_entries(counters, now)
        
        current_usage = {
            'minute': len(counters['minute']),
            'hour': len(counters['hour']),
            'day': len(counters['day'])
        }
        
        # Check limits
        if current_usage['minute'] >= self.limits['per_minute']:
            return {
                "allowed": False,
                "reason": "Minute limit exceeded",
                "current": current_usage,
                "limits": self.limits,
                "retry_after": 60 - (now % 60)
            }
        
        if current_usage['hour'] >= self.limits['per_hour']:
            return {
                "allowed": False,
                "reason": "Hour limit exceeded", 
                "current": current_usage,
                "limits": self.limits,
                "retry_after": 3600 - (now % 3600)
            }
        
        if current_usage['day'] >= self.limits['per_day']:
            return {
                "allowed": False,
                "reason": "Daily limit exceeded",
                "current": current_usage,
                "limits": self.limits,
                "retry_after": 86400 - (now % 86400)
            }
        
        return {
            "allowed": True,
            "current": current_usage,
            "limits": self.limits,
            "remaining": {
                "minute": self.limits['per_minute'] - current_usage['minute'],
                "hour": self.limits['per_hour'] - current_usage['hour'],
                "day": self.limits['per_day'] - current_usage['day']
            }
        }
    
    async def record_send(self, user_id: str = "global"):
        """Record an email send"""
        now = time.time()
        counters = self.counters[user_id]
        
        counters['minute'].append(now)
        counters['hour'].append(now)
        counters['day'].append(now)
    
    def _clean_old_entries(self, counters: dict, now: float):
        """Remove old entries outside time windows"""
        # Remove entries older than 1 minute
        while counters['minute'] and now - counters['minute'][0] > 60:
            counters['minute'].popleft()
        
        # Remove entries older than 1 hour  
        while counters['hour'] and now - counters['hour'][0] > 3600:
            counters['hour'].popleft()
        
        # Remove entries older than 1 day
        while counters['day'] and now - counters['day'][0] > 86400:
            counters['day'].popleft()

# Global rate limiter instance
rate_limiter = RateLimiter()

async def update_rate_limiter(limits: dict):
    """Update global rate limiter settings"""
    await rate_limiter.update_limits({
        'per_minute': limits.per_minute,
        'per_hour': limits.per_hour,
        'per_day': limits.per_day
    })

