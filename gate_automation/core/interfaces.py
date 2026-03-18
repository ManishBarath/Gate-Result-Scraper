from __future__ import annotations

from abc import ABC, abstractmethod

from gate_automation.core.models import CandidateCredential, CandidateResult


class CredentialLoader(ABC):
    @abstractmethod
    def load_credentials(self) -> list[CandidateCredential]:
        raise NotImplementedError


class CaptchaSolver(ABC):
    @abstractmethod
    def solve(self, image_bytes: bytes) -> str:
        raise NotImplementedError


class PortalClient(ABC):
    @abstractmethod
    def fetch_candidate_result(self, credential: CandidateCredential) -> CandidateResult:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class ResultSink(ABC):
    @abstractmethod
    def publish(self, result: CandidateResult) -> None:
        raise NotImplementedError
