"""
Task Queue Helper for SkillSight
Enqueue background jobs via Redis Queue.
"""
import logging
import os
import threading
from datetime import timedelta
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QUEUE_NAME = "skillsight"

_redis_conn = None
_redis_lock = threading.Lock()


def _get_redis():
    """Return a shared Redis connection (thread-safe singleton)."""
    global _redis_conn
    if _redis_conn is not None:
        return _redis_conn
    with _redis_lock:
        if _redis_conn is not None:
            return _redis_conn
        from redis import Redis
        _redis_conn = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=0,
            socket_connect_timeout=5,
            socket_keepalive=True,
            retry_on_timeout=True,
        )
        return _redis_conn


def _get_queue():
    from rq import Queue
    return Queue(QUEUE_NAME, connection=_get_redis())


def enqueue_process_doc(doc_id: str, job_id: str) -> Optional[str]:
    """
    Enqueue a document processing job.
    Returns the RQ job ID if successful, None if Redis is unavailable.
    """
    try:
        q = _get_queue()
        job = q.enqueue(
            "backend.worker.run_job",
            doc_id,
            job_id,
            job_timeout=600,
            result_ttl=86400,
        )
        return job.id
    except Exception as e:
        logger.warning("[queue] Failed to enqueue job: %s", e)
        return None


def enqueue_assessment_repair(
    session_id: str,
    repair_job_id: str,
    delay_seconds: int = 0,
) -> Optional[str]:
    """Enqueue an assessment repair job."""
    try:
        q = _get_queue()
        enqueue_kwargs = {
            "job_timeout": 300,
            "result_ttl": 86400,
        }
        if delay_seconds > 0:
            job = q.enqueue_in(
                timedelta(seconds=max(1, int(delay_seconds))),
                "backend.worker.run_assessment_repair",
                session_id,
                repair_job_id,
                **enqueue_kwargs,
            )
        else:
            job = q.enqueue(
                "backend.worker.run_assessment_repair",
                session_id,
                repair_job_id,
                **enqueue_kwargs,
            )
        return job.id
    except Exception as e:
        logger.warning("[queue] Failed to enqueue assessment repair job: %s", e)
        return None


def get_queue_status() -> dict:
    """Get queue status information."""
    try:
        q = _get_queue()
        return {
            "connected": True,
            "queue_name": QUEUE_NAME,
            "pending_jobs": len(q),
            "failed_jobs": len(q.failed_job_registry),
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }
