from redis import Redis
from redis.exceptions import RedisError

from config import settings


def get_redis_client() -> Redis:
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is not configured")
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def ping_redis() -> bool:
    client = get_redis_client()
    try:
        return bool(client.ping())
    except RedisError:
        return False
