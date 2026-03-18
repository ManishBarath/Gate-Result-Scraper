from __future__ import annotations

import csv
from pathlib import Path

from gate_automation.core.interfaces import ResultSink
from gate_automation.core.models import CandidateResult


class ConsoleResultSink(ResultSink):
    def publish(self, result: CandidateResult) -> None:
        print(
            f"[{result.status.upper()}] {result.enrollment_id}: {result.message}"
        )
        if result.extracted:
            print(f"  Extracted: {result.extracted}")


class CsvResultSink(ResultSink):
    def __init__(self, output_path: str | Path) -> None:
        self._output_path = Path(output_path)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, result: CandidateResult) -> None:
        file_exists = self._output_path.exists()
        with self._output_path.open("a", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "fetched_at",
                    "enrollment_id",
                    "status",
                    "message",
                    "extracted",
                ],
            )
            if not file_exists:
                writer.writeheader()

            writer.writerow(
                {
                    "fetched_at": result.fetched_at,
                    "enrollment_id": result.enrollment_id,
                    "status": result.status,
                    "message": result.message,
                    "extracted": result.extracted,
                }
            )
