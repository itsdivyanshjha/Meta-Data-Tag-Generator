"""
Redis client for job state persistence and pub/sub progress updates.

Job state is stored in Redis hashes with 24-hour TTL.
Progress updates are published via Redis pub/sub channels.
"""

import json
import logging
from typing import Optional, Dict, Any, List

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# Singleton connection pool
_redis: Optional[aioredis.Redis] = None

JOB_TTL = 86400  # 24 hours


async def get_redis() -> aioredis.Redis:
    """Get or create the async Redis connection."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis


async def close_redis():
    """Close the Redis connection."""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
        logger.info("Redis connection closed")


# ---- Job State Helpers ----

def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _results_key(job_id: str) -> str:
    return f"job:{job_id}:results"


def _progress_channel(job_id: str) -> str:
    return f"job:{job_id}:progress"


async def set_job_state(job_id: str, state: Dict[str, Any]):
    """Store the full job state as a Redis hash."""
    r = await get_redis()
    key = _job_key(job_id)
    # Flatten complex values to JSON strings
    flat: Dict[str, str] = {}
    for k, v in state.items():
        flat[k] = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
    await r.hset(key, mapping=flat)
    await r.expire(key, JOB_TTL)


async def get_job_state(job_id: str) -> Optional[Dict[str, str]]:
    """Get the full job state hash."""
    r = await get_redis()
    data = await r.hgetall(_job_key(job_id))
    return data if data else None


async def update_job_field(job_id: str, field: str, value: Any):
    """Update a single field in the job state."""
    r = await get_redis()
    v = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    await r.hset(_job_key(job_id), field, v)


async def get_job_field(job_id: str, field: str) -> Optional[str]:
    """Get a single field from the job state."""
    r = await get_redis()
    return await r.hget(_job_key(job_id), field)


async def append_result(job_id: str, result: Dict[str, Any]):
    """Append a document result to the job's results list."""
    r = await get_redis()
    key = _results_key(job_id)
    await r.rpush(key, json.dumps(result))
    await r.expire(key, JOB_TTL)


async def get_results(job_id: str) -> List[Dict[str, Any]]:
    """Get all results for a job."""
    r = await get_redis()
    raw = await r.lrange(_results_key(job_id), 0, -1)
    return [json.loads(item) for item in raw]


async def get_results_count(job_id: str) -> int:
    """Get the count of results for a job."""
    r = await get_redis()
    return await r.llen(_results_key(job_id))


# ---- Pub/Sub ----

async def publish_progress(job_id: str, update: Dict[str, Any]):
    """Publish a progress update for WebSocket observers."""
    r = await get_redis()
    await r.publish(_progress_channel(job_id), json.dumps(update))


async def subscribe_progress(job_id: str):
    """Subscribe to progress updates for a job. Returns a pubsub object."""
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(_progress_channel(job_id))
    return pubsub


# ---- Job Command (cancel/pause/resume) ----

async def set_job_command(job_id: str, command: str):
    """Set a command for the processing loop to pick up."""
    await update_job_field(job_id, "command", command)


async def get_job_command(job_id: str) -> Optional[str]:
    """Get and clear the current command for a job."""
    r = await get_redis()
    key = _job_key(job_id)
    cmd = await r.hget(key, "command")
    if cmd and cmd != "none":
        await r.hset(key, "command", "none")
        return cmd
    return None


# ---- Active Job Scanning ----

async def get_active_job_ids() -> List[str]:
    """Scan for all jobs with status=processing."""
    r = await get_redis()
    job_ids = []
    async for key in r.scan_iter(match="job:*", count=100):
        # Skip results keys and progress channels
        if ":results" in key or ":progress" in key:
            continue
        status = await r.hget(key, "status")
        if status == "processing":
            # Extract job_id from key "job:{job_id}"
            job_id = key.split(":", 1)[1]
            job_ids.append(job_id)
    return job_ids


async def cleanup_job(job_id: str):
    """Delete all Redis keys for a job."""
    r = await get_redis()
    await r.delete(_job_key(job_id), _results_key(job_id))
