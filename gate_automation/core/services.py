from __future__ import annotations

from collections.abc import Iterable

from gate_automation.core.interfaces import CredentialLoader, PortalClient, ResultSink
from gate_automation.core.models import CandidateResult


class GateResultService:
    def __init__(
        self,
        credential_loader: CredentialLoader,
        portal_client: PortalClient,
        result_sinks: Iterable[ResultSink],
    ) -> None:
        self._credential_loader = credential_loader
        self._portal_client = portal_client
        self._result_sinks = list(result_sinks)

    def run(self) -> list[CandidateResult]:
        credentials = self._credential_loader.load_credentials()
        results: list[CandidateResult] = []

        try:
            for credential in credentials:
                try:
                    result = self._portal_client.fetch_candidate_result(credential)
                except Exception as error:
                    result = CandidateResult(
                        enrollment_id=credential.enrollment_id,
                        status="failed",
                        message=f"Unhandled error: {error}",
                    )

                for sink in self._result_sinks:
                    sink.publish(result)

                results.append(result)
        finally:
            self._portal_client.close()

        return results
