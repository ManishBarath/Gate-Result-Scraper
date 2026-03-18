import time
import pandas as pd
import streamlit as st
import concurrent.futures
from gate_automation.core.models import CandidateCredential
from gate_automation.infrastructure.browser.playwright_client import PlaywrightPortalClient
from gate_automation.infrastructure.captcha.factory import CaptchaSolverFactory
from gate_automation.infrastructure.database import SQLiteResultRepository
st.set_page_config(page_title='GATE Credentials Checker', layout='wide')
db_repo = SQLiteResultRepository()
st.title('GATE Students Login Validation')
st.markdown('Load candidates from the CSV file and check if their stored passwords match the GATE portal.')

@st.cache_data
def load_and_clean_data(file_path='data/Data.csv'):
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        st.error(f'File not found: {file_path}')
        return pd.DataFrame()
    df.columns = df.columns.str.strip()
    if 'Username' in df.columns:
        df['Username'] = df['Username'].astype(str).str.replace('\\s+', '', regex=True)
    if 'Password' in df.columns:
        df['Password'] = df['Password'].astype(str).str.strip()
    return df

def worker_verify_credential(row_tuple):
    idx, row = row_tuple
    username = str(row.get('Username', '')).strip()
    password = str(row.get('Password', '')).strip()
    if not username or username.lower() in ['nan', 'na'] or (not password) or (password.lower() in ['nan', 'na']):
        return (idx, row, 'skip', None)
    solver = CaptchaSolverFactory.create('ocr')
    client = PlaywrightPortalClient(base_url='https://goaps.iitg.ac.in/login', captcha_solver=solver, headless=True, timeout_ms=15000, max_captcha_attempts=8)
    cred = CandidateCredential(enrollment_id=username, password=password)
    try:
        result = client.fetch_candidate_result(cred)
        db_repo.save_result(result)
        return (idx, row, 'done', result)
    except Exception as e:
        return (idx, row, 'error', str(e))
    finally:
        client.close()
    return df
dataset = load_and_clean_data()
tabs = st.tabs(['Check Credentials Flow', 'Database Records'])
with tabs[0]:
    if not dataset.empty:
        st.subheader('Data Overview')
    st.dataframe(dataset, use_container_width=True)
    st.divider()
    st.subheader('Validate Passwords (Multithreaded)')
    st.warning('Note: Checking all records requires automating browser login for each row. The system will use multiple browsers simultaneously to speed this up.')
    col1, col2 = st.columns([1, 1])
    with col1:
        test_limit = st.slider('Max records to test (0 = all)', min_value=0, max_value=len(dataset), value=20)
    with col2:
        max_workers = st.slider('Concurrent Playwright Bots', min_value=1, max_value=10, value=4, help='More bots = faster, but high numbers may overload your CPU or get temporarily blocked by the GATE server.')
    start_check = st.button('Start Checking Passwords', type='primary')
    if start_check:
        progress_bar = st.progress(0)
        status_text = st.empty()
        st.markdown('### ❌ Users with Invalid Credentials')
        wrong_users_table = st.empty()
        wrong_users_list = []
        rows_to_check = dataset if test_limit == 0 else dataset.head(test_limit)
        total_rows = len(rows_to_check)
        completed = 0
        status_text.text(f'Starting {max_workers} concurrent thread(s)...')
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker_verify_credential, row_tuple): row_tuple for row_tuple in rows_to_check.iterrows()}
            for future in concurrent.futures.as_completed(futures):
                idx, row, status, result = future.result()
                completed += 1
                progress_bar.progress(completed / total_rows)
                status_text.text(f"Progress ({completed}/{total_rows}) - Just finished checking: {row.get('Username', '')}")
                if status == 'error':
                    st.toast(f"Error checking {row.get('Username')}: {result}", icon='⚠️')
                elif status == 'done' and result.status == 'failed':
                    msg = result.message.lower()
                    if 'invalid' in msg or 'incorrect' in msg or 'captcha attempts' in msg:
                        wrong_users_list.append(row.to_dict())
                        df_wrong = pd.DataFrame(wrong_users_list)
                        wrong_users_table.dataframe(df_wrong, use_container_width=True)
        status_text.success(f'Finished checking {total_rows} records!')
        if not wrong_users_list:
            st.balloons()
            st.success('All checked passwords were valid! (Or no invalid credentials matched the failure criteria).')
        else:
            st.error(f'Found {len(wrong_users_list)} invalid logins.')
with tabs[1]:
    st.subheader('Persistent Database Records')
    st.markdown('This view reads directly from the local `output/gate_results.db` SQLite database.')
    if st.button('Refresh Database View'):
        pass
    db_df = db_repo.get_all_results_df()
    if not db_df.empty:
        st.dataframe(db_df, use_container_width=True)
        csv_data = db_df.to_csv(index=False).encode('utf-8')
        st.download_button(label='Download Database as CSV', data=csv_data, file_name='gate_database_export.csv', mime='text/csv')
    else:
        st.info('The database is currently empty. Run a check to populate it.')
