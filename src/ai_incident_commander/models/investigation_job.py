"""Investigation job payload for queued execution."""

from __future__ import annotations

import uuid
import json
from typing import Any

from pydantic import BaseModel


def derive_investigation_id(idempotency_key: str | None = None) -> str:
    """
    Derive a stable investigation ID from an idempotency key.

    Args:
        idempotency_key: Optional stable external identifier such as a PagerDuty event ID.

    Returns:
        UUID string — deterministic when ``idempotency_key`` is provided.
    """
    if idempotency_key:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key.strip()))
    return str(uuid.uuid4())


class InvestigationJob(BaseModel):
    """Serializable investigation work item for in-process or Redis queues."""

    investigation_id: str
    service: str
    description: str
    channel_id: str
    idempotency_key: str | None = None
    action_token: str | None = None
    assistant_thread: tuple[str, str] | None = None

    def to_redis_payload(self) -> str:
        """
        Serialize the job for Redis list storage.

        Returns:
            JSON string representation of the job.
        """
        payload: dict[str, Any] = self.model_dump()
        if self.assistant_thread is not None:
            payload["assistant_thread"] = list(self.assistant_thread)
        return json.dumps(payload)

    @classmethod
    def from_redis_payload(cls, raw: str) -> "InvestigationJob":
        """
        Deserialize a job from Redis list storage.

        Args:
            raw: JSON string from ``to_redis_payload``.

        Returns:
            Parsed ``InvestigationJob`` instance.
        """
        job = cls.model_validate_json(raw)
        thread = job.assistant_thread
        if isinstance(thread, list) and len(thread) == 2:
            job.assistant_thread = (str(thread[0]), str(thread[1]))
        return job
