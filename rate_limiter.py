import time
import asyncio
from typing import Dict, Optional
import redis.asyncio as redis
from contextlib import asynccontextmanager

class RateLimiter:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis = None
        if redis_url:
            try:
                self.redis = redis.from_url(redis_url)
            except Exception:
                self.redis = None
        
        # In-memory storage if Redis is not available
        self.user_requests: Dict[int, list] = {}
        self.global_requests: list = []
    
    async def is_rate_limited(self, user_id: int) -> bool:
        current_time = time.time()
        
        # Global rate limiting (10 requests per second)
        if self.redis:
            global_key = "global_requests"
            # Keep only requests from last second
            await self.redis.zremrangebyscore(global_key, 0, current_time - 1)
            global_count = await self.redis.zcard(global_key)
            
            if global_count >= 10:
                return True
            await self.redis.zadd(global_key, {str(current_time): current_time})
        else:
            # In-memory global rate limiting
            self.global_requests = [t for t in self.global_requests if t > current_time - 1]
            if len(self.global_requests) >= 10:
                return True
            self.global_requests.append(current_time)
        
        # User rate limiting (60 requests per minute)
        if self.redis:
            user_key = f"user_{user_id}"
            # Keep only requests from last minute
            await self.redis.zremrangebyscore(user_key, 0, current_time - 60)
            user_count = await self.redis.zcard(user_key)
            
            if user_count >= 60:
                return True
            await self.redis.zadd(user_key, {str(current_time): current_time})
        else:
            # In-memory user rate limiting
            if user_id not in self.user_requests:
                self.user_requests[user_id] = []
            
            user_requests = self.user_requests[user_id]
            user_requests = [t for t in user_requests if t > current_time - 60]
            
            if len(user_requests) >= 60:
                return True
            
            user_requests.append(current_time)
            self.user_requests[user_id] = user_requests
        
        return False

    @asynccontextmanager
    async def limit_context(self, user_id: int):
        if await self.is_rate_limited(user_id):
            raise RateLimitExceeded("Rate limit exceeded")
        yield

class RateLimitExceeded(Exception):
    pass