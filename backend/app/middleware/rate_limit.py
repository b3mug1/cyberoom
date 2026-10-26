import hashlib
import logging
import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import Settings

logger = logging.getLogger(__name__)

INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client: Redis, settings: Settings) -> None:
        super().__init__(app)
        self.redis_client = redis_client
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if not path.startswith("/api/v1/") or request.method == "OPTIONS":
            return await call_next(request)

        is_auth = path in {
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
        }
        limit = self.settings.auth_rate_limit_per_minute if is_auth else self.settings.rate_limit_per_minute
        window = 60
        peer = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        client_key = hashlib.sha256(peer.encode("utf-8")).hexdigest()
        window_id = int(time.time() // window)
        key = f"cyberoom:rate-limit:v1:{'auth' if is_auth else 'api'}:{client_key}:{window_id}"

        try:
            count = int(await self.redis_client.eval(INCREMENT_SCRIPT, 1, key, window))
            ttl = max(1, await self.redis_client.ttl(key))
        except RedisError:
            logger.exception("Rate limit storage is unavailable")
            if self.settings.app_env == "production":
                return JSONResponse(
                    status_code=503,
                    content={"detail": {"code": "RATE_LIMIT_UNAVAILABLE", "message": "Requests are temporarily unavailable."}},
                    headers={"Retry-After": str(window)},
                )
            return await call_next(request)

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": {"code": "RATE_LIMITED", "message": "Too many requests. Try again shortly."}},
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response
