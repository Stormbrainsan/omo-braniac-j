import redis
from django.conf import settings

# A single module-level connection pool. redis-py's connection pool is
# thread-safe, so this is safe to share across requests/workers within one
# process. We deliberately do NOT use django-redis / Django's cache
# framework here: OTP storage and rate limiting need atomic INCR+EXPIRE and
# an atomic "read-then-delete" (via a Lua script) that the cache framework's
# generic API doesn't expose cleanly.
_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)
