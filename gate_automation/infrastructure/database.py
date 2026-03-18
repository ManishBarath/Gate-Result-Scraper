from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from gate_automation.core.interfaces import ResultSink
from gate_automation.core.models import CandidateResult

class SQLiteResultRepository(ResultSink):
    """
    Implements a database storage sink following SOLID principles.
    Can be used like any other ResultSink (Console, CSV), but writes to SQLite.
    """

    def __init__(self, db_path: str | Path='output/gate_results.db') -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute('\n                CREATE TABLE IF NOT EXISTS candidate_results (\n                    enrollment_id TEXT PRIMARY KEY,\n                    status TEXT,\n                    message TEXT,\n                    data_json TEXT,\n                    fetched_at TEXT\n                )\n            ')

    def publish(self, result: CandidateResult) -> None:
        self.save_result(result)

    def save_result(self, result: CandidateResult) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute('\n                INSERT INTO candidate_results (enrollment_id, status, message, data_json, fetched_at)\n                VALUES (?, ?, ?, ?, ?)\n                ON CONFLICT(enrollment_id) DO UPDATE SET\n                    status=excluded.status,\n                    message=excluded.message,\n                    data_json=excluded.data_json,\n                    fetched_at=excluded.fetched_at\n            ', (result.enrollment_id, result.status, result.message, json.dumps(result.extracted), result.fetched_at))

    def get_all_results_df(self):
        """Returns a Pandas DataFrame of the currently stored database results."""
        import pandas as pd
        with sqlite3.connect(self._db_path) as conn:
            df = pd.read_sql_query('SELECT * FROM candidate_results', conn)
            if not df.empty and 'data_json' in df.columns:
                expanded_data = df['data_json'].apply(lambda x: json.loads(x) if x else {})
                df = df.drop(columns=['data_json']).join(pd.json_normalize(expanded_data))
            return df
