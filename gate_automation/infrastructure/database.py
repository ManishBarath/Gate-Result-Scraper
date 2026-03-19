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
        self.save_many_results([result])

    def save_many_results(self, results: list[CandidateResult]) -> None:
        if not results:
            return
            
        # Optimization: Bulk insert using executemany to prevent SQLite locks
        query = '''
            INSERT INTO candidate_results (enrollment_id, status, message, data_json, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(enrollment_id) DO UPDATE SET
                status=excluded.status,
                message=excluded.message,
                data_json=excluded.data_json,
                fetched_at=excluded.fetched_at
        '''
        
        data_tuples = [
            (r.enrollment_id, r.status, r.message, json.dumps(r.extracted), r.fetched_at)
            for r in results
        ]
        
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(query, data_tuples)


    def execute_query(self, query: str, parameters: tuple = ()) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(query, parameters)
            conn.commit()
            
    def delete_record(self, enrollment_id: str) -> None:
        self.execute_query("DELETE FROM candidate_results WHERE enrollment_id=?", (enrollment_id,))
        

    def clear_database(self) -> None:
        self.execute_query("DELETE FROM candidate_results")

    def update_records_from_df(self, df) -> None:
        if df.empty or 'enrollment_id' not in df.columns:
            return
            
        import pandas as pd
        query = '''
            UPDATE candidate_results 
            SET status=?, message=?, data_json=?, fetched_at=?
            WHERE enrollment_id=?
        '''
        data_tuples = []
        for _, row in df.iterrows():
            eid = str(row['enrollment_id'])
            status = str(row.get('status', 'success'))
            message = str(row.get('message', ''))
            fetched_at = str(row.get('fetched_at', ''))
            
            extracted = {}
            for col in df.columns:
                if col not in ['enrollment_id', 'status', 'message', 'fetched_at']:
                    val = row[col]
                    if pd.notna(val) and val != "":
                        extracted[col] = str(val)
            
            data_tuples.append((status, message, json.dumps(extracted), fetched_at, eid))
            
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(query, data_tuples)
            conn.commit()


    def get_all_results_df(self):
        """Returns a Pandas DataFrame of the currently stored database results."""
        import pandas as pd
        with sqlite3.connect(self._db_path) as conn:
            df = pd.read_sql_query('SELECT * FROM candidate_results', conn)
            if not df.empty and 'data_json' in df.columns:
                expanded_data = df['data_json'].apply(lambda x: json.loads(x) if x else {})
                df = df.drop(columns=['data_json']).join(pd.json_normalize(expanded_data))
            return df
