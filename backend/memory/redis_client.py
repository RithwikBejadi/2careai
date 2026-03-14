import ssl
from redis import Redis
from redis.exceptions import RedisError

from config import settings

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

def get_redis_client() -> Redis:
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is not configured")
    return Redis.from_url(settings.REDIS_URL, decode_responses=True, ssl_cert_reqs=None)


def ping_redis() -> bool:
    client = get_redis_client()
    try:
        return bool(client.ping())
    except RedisError:
        return False
