from __future__ import annotations

import csv
from pathlib import Path

from gate_automation.core.interfaces import CredentialLoader
from gate_automation.core.models import CandidateCredential


class CsvCredentialLoader(CredentialLoader):
    def __init__(self, csv_path: str | Path) -> None:
        self._csv_path = Path(csv_path)

    def load_credentials(self) -> list[CandidateCredential]:
        if not self._csv_path.exists():
            raise FileNotFoundError(f"Credential file not found: {self._csv_path}")

        credentials: list[CandidateCredential] = []
        with self._csv_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            
            # Clean up field names in case they have trailing spaces (like 'Username ' or 'Password ')
            if reader.fieldnames:
                reader.fieldnames = [str(field).strip() for field in reader.fieldnames]

            if not reader.fieldnames:
                raise ValueError("CSV is empty or missing headers")

            for row in reader:
                # Support standard headers, or the headers from the uploaded Data.csv
                enrollment_id = (row.get("enrollment_id") or row.get("Username") or row.get("Username ") or "").strip()
                password = (row.get("password") or row.get("Password") or row.get("Password ") or "").strip()
                
                if enrollment_id and password and enrollment_id != "NA" and password != "NA":
                    credentials.append(
                        CandidateCredential(
                            enrollment_id=enrollment_id,
                            password=password,
                        )
                    )

        if not credentials:
            raise ValueError("No valid credentials found in CSV")

        return credentials
