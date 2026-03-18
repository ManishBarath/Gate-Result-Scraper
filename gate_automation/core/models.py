from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CandidateCredential:
    enrollment_id: str
    password: str


@dataclass(slots=True)
class CandidateResult:
    enrollment_id: str
    status: str
    message: str
    extracted: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))
