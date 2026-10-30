from threading import RLock
from uuid import uuid4

from .models import now


class Execution:
    """Per-invocation telemetry, not model reasoning or business authority."""

    def __init__(self, run_id, session_id, principal, emit=None):
        self.run_id = run_id
        self.session_id = session_id
        self.principal = principal
        self.emit = emit
        self.events = []
        self.lock = RLock()
        self.evidence = {}

    def event(self, kind, agent, **data):
        with self.lock:
            return self._event(kind, agent, **data)

    def _event(self, kind, agent, **data):
        value = {
            "id": str(uuid4()),
            "run_id": self.run_id,
            "sequence": len(self.events) + 1,
            "timestamp": now(),
            "kind": kind,
            "agent": agent,
            **data,
        }
        self.events.append(value)
        if self.emit:
            self.emit(value)
        return value

    def add_evidence(self, evidence):
        self.evidence[evidence.id] = evidence
        return evidence.id
