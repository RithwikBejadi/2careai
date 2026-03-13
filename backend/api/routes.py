from fastapi import APIRouter

from memory.redis_client import ping_redis

router = APIRouter()


@router.get("/redis/health")
def redis_health() -> dict[str, bool]:
    return {"ok": ping_redis()}


@router.get("/doctors")
def doctors_stub() -> list[dict[str, str]]:
    return [{"name": "Dr. Demo", "specialty": "General"}]
