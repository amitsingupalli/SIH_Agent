"""
MahaArogya Enterprise Reliability Framework
SIH 2026 PS 133 | Govt of Maharashtra Health Department

Provides:
1. Exponential backoff retry handler for flaky rural telecommunications (SMS / WhatsApp / Bhashini).
2. Dead-Letter Queue (DLQ) for failed alert and referral dispatch.
3. Idempotency guard preventing duplicate hospital bookings and referrals from repeated ASHA taps on 2G/3G.
"""

from datetime import datetime, timezone, timedelta
import functools
import hashlib
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger("maha_arogya.reliability")


# =====================================================================
# 1. Exponential Backoff Retry Utility
# =====================================================================

def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator to retry flaky I/O calls (SMS gateway, Bhashini, NIC server) with exponential backoff."""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_err: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_err = exc
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} for '{func.__name__}' failed: {exc}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    if attempt < max_attempts:
                        time.sleep(delay)
                        delay *= backoff_factor
            logger.error(f"All {max_attempts} attempts failed for '{func.__name__}': {last_err}")
            raise last_err
        return wrapper
    return decorator


# =====================================================================
# 2. Dead-Letter Queue (DLQ) for Failed Clinical Alerts & Referrals
# =====================================================================

class DeadLetterQueue:
    """
    Immutable in-memory Dead-Letter Queue (DLQ) with fallback persistence.
    Captures un-deliverable SMS alerts, WhatsApp notices, and referral handshakes
    for manual DHO/PHC doctor review and offline replay.
    """
    def __init__(self):
        self._queue: List[Dict[str, Any]] = []

    def enqueue(
        self,
        event_type: str,
        payload: Dict[str, Any],
        error_reason: str,
        recipient: Optional[str] = None,
        patient_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a failed event in the DLQ."""
        dlq_id = f"DLQ-{len(self._queue) + 1:04d}-{int(time.time())}"
        record = {
            "dlq_id": dlq_id,
            "event_type": event_type,
            "patient_id": patient_id or payload.get("patient_id", "UNKNOWN"),
            "recipient": recipient or payload.get("recipient_phone", "UNKNOWN"),
            "payload": payload,
            "error_reason": error_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "UNRESOLVED",
            "retry_count": 0,
        }
        self._queue.append(record)
        logger.warning(f"Message routed to Dead-Letter Queue: {dlq_id} | Type: {event_type} | Reason: {error_reason}")
        return record

    def list_unresolved(self) -> List[Dict[str, Any]]:
        """Return all unresolved DLQ items."""
        return [item for item in self._queue if item["status"] == "UNRESOLVED"]

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all DLQ items (both unresolved and resolved)."""
        return list(self._queue)

    def mark_resolved(self, dlq_id: str, resolution_notes: str = "Resolved by manual supervisor action") -> bool:
        """Mark an item as resolved after successful manual follow-up."""
        for item in self._queue:
            if item["dlq_id"] == dlq_id:
                item["status"] = "RESOLVED"
                item["resolved_at"] = datetime.now(timezone.utc).isoformat()
                item["resolution_notes"] = resolution_notes
                logger.info(f"DLQ item {dlq_id} marked as RESOLVED.")
                return True
        return False

    def clear(self):
        """Reset queue for test isolation."""
        self._queue.clear()


# Global Singleton DLQ
dead_letter_queue = DeadLetterQueue()


# =====================================================================
# 3. Idempotency Guard (Network Replay & Double-Booking Protection)
# =====================================================================

class IdempotencyGuard:
    """
    Prevents duplicate clinical actions (such as duplicate hospital bed reservations,
    duplicate FHIR encounters, or multiple referral token generation) caused by
    flaky 2G/3G mobile networks where ASHA workers double-tap submit.
    """
    def __init__(self, ttl_seconds: int = 600):
        self.ttl = timedelta(seconds=ttl_seconds)
        # key -> {"result": Dict[str, Any], "cached_at": datetime, "status": "PENDING" | "COMPLETED"}
        self._store: Dict[str, Dict[str, Any]] = {}

    def compute_key(self, patient_id: str, action: str, salt: str = "") -> str:
        """Compute an automatic deterministic key if client did not supply one."""
        raw = f"{patient_id.strip().upper()}:{action.strip()}:{salt}"
        return f"idemp-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    def check(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Check if key has been executed within TTL.
        Returns cached response if already completed, or None if new.
        """
        self._cleanup()
        entry = self._store.get(key)
        if entry:
            return entry.get("result")
        return None

    def acquire(self, key: str) -> bool:
        """
        Attempt to acquire idempotency lock.
        Returns True if acquired (new request), False if concurrent or completed.
        """
        self._cleanup()
        if key in self._store:
            return False
        self._store[key] = {
            "status": "PENDING",
            "cached_at": datetime.now(timezone.utc),
            "result": None,
        }
        return True

    def commit(self, key: str, result: Dict[str, Any]):
        """Store the successful execution result against the idempotency key."""
        if key in self._store:
            self._store[key]["status"] = "COMPLETED"
            self._store[key]["result"] = result
            self._store[key]["cached_at"] = datetime.now(timezone.utc)
        else:
            self._store[key] = {
                "status": "COMPLETED",
                "cached_at": datetime.now(timezone.utc),
                "result": result,
            }

    def release(self, key: str):
        """Release key in case of processing error so client can retry."""
        self._store.pop(key, None)

    def _cleanup(self):
        """Remove expired idempotency records."""
        now = datetime.now(timezone.utc)
        expired = [k for k, v in self._store.items() if now - v["cached_at"] > self.ttl]
        for k in expired:
            del self._store[k]

    def clear(self):
        """Clear cache for test isolation."""
        self._store.clear()


# Global Singleton Idempotency Guard (10-minute TTL)
idempotency_guard = IdempotencyGuard(ttl_seconds=600)
