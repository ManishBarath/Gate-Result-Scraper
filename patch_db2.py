import re

with open('gate_automation/infrastructure/database.py', 'r') as f:
    content = f.read()

new_methods = """
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
"""

content = content.replace('    def clear_database(self) -> None:\n        self.execute_query("DELETE FROM candidate_results")', new_methods)

with open('gate_automation/infrastructure/database.py', 'w') as f:
    f.write(content)
