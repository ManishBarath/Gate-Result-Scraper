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

def worker_verify_credential_chunk(rows_chunk):
    results = []
    # Initialize one Playwright client for this whole chunk to save massive RAM and CPU
    solver = CaptchaSolverFactory.create('ocr')
    client = PlaywrightPortalClient(base_url='https://goaps.iitg.ac.in/login', captcha_solver=solver, headless=True, timeout_ms=15000, max_captcha_attempts=8)
    
    try:
        for idx, row in rows_chunk:
            username = str(row.get('Username', '')).strip()
            password = str(row.get('Password', '')).strip()
            
            if not username or username.lower() in ['nan', 'na'] or (not password) or (password.lower() in ['nan', 'na']):
                results.append((idx, row, 'skip', None))
                continue
                
            cred = CandidateCredential(enrollment_id=username, password=password)
            try:
                result = client.fetch_candidate_result(cred)
                results.append((idx, row, 'done', result))
            except Exception as e:
                results.append((idx, row, 'error', str(e)))
    finally:
        # Close the browser once ALL rows in this chunk are finished
        client.close()
        
    return results
dataset = load_and_clean_data()

# Initialize session state for dataset if not exists so we can edit it inline
if "edited_dataset" not in st.session_state:
    st.session_state.edited_dataset = dataset.copy()

tabs = st.tabs(['Check Credentials Flow', 'Scrape Results', 'Single User Check', 'Database Records'])
with tabs[0]:
    if not st.session_state.edited_dataset.empty:
        st.subheader('Editable Data Overview')
        st.markdown("You can edit cells directly, or **delete/add rows** using the table controls. Click **Save Changes** below to apply.")
    
    # Use st.data_editor which allows editing, adding, and deleting rows!
    st.session_state.edited_dataset = st.data_editor(
        st.session_state.edited_dataset, 
        use_container_width=True, 
        num_rows="dynamic", # Enables adding/deleting rows natively in the UI
        key="data_editor"
    )
    
    if st.button("Save Changes to CSV", type="secondary"):
        st.session_state.edited_dataset.to_csv('data/Data.csv', index=False)
        st.success("Changes saved to data/Data.csv successfully!")
        load_and_clean_data.clear() # Clear cache so next reload fetches fresh data

    st.divider()
    st.subheader('Validate Passwords (Multithreaded)')
    st.warning('Note: Checking all records requires automating browser login for each row. The system will use multiple browsers simultaneously to speed this up.')
    col1, col2 = st.columns([1, 1])
    with col1:
        test_limit = st.slider('Max records to test (0 = all)', min_value=0, max_value=len(dataset), value=20)
    with col2:
        max_workers = st.slider('Concurrent Playwright Bots', min_value=1, max_value=20, value=4, help='More bots = faster, but high numbers may overload your CPU or get temporarily blocked by the GATE server.')
    start_check = st.button('Start Checking Passwords', type='primary')
    if start_check:
        progress_bar = st.progress(0)
        status_text = st.empty()
        st.markdown('### ❌ Users with Invalid Credentials')
        wrong_users_table = st.empty()
        wrong_users_list = []
        rows_to_check = st.session_state.edited_dataset if test_limit == 0 else st.session_state.edited_dataset.head(test_limit)
        total_rows = len(rows_to_check)
        completed = 0
        status_text.text(f'Starting {max_workers} concurrent thread(s)...')
        
        # Split dataframe into chunks equal to number of workers to share browser contexts
        import math
        chunk_size = max(1, math.ceil(total_rows / max_workers))
        row_list = list(rows_to_check.iterrows())
        chunks = [row_list[i:i + chunk_size] for i in range(0, len(row_list), chunk_size)]
        
        all_success_results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker_verify_credential_chunk, chunk): chunk for chunk in chunks}
            
            for future in concurrent.futures.as_completed(futures):
                chunk_results = future.result()
                
                for idx, row, status, result in chunk_results:
                    completed += 1
                    progress_bar.progress(completed / total_rows)
                    status_text.text(f"Progress ({completed}/{total_rows}) - Checked: {row.get('Username', '')}")
                    
                    if status == 'error':
                        st.toast(f"Error checking {row.get('Username')}: {result}", icon='⚠️')
                    elif status == 'done':
                        if result:
                            all_success_results.append(result)
                        if result.status == 'failed':
                            msg = result.message.lower()
                            if 'invalid' in msg or 'incorrect' in msg or 'captcha attempts' in msg:
                                wrong_users_list.append(row.to_dict())
                                df_wrong = pd.DataFrame(wrong_users_list)
                                wrong_users_table.dataframe(df_wrong, use_container_width=True)
                                
        # Perform ONE bulk database insert instead of locking 259 times
        if all_success_results:
            db_repo.save_many_results(all_success_results)
            
        status_text.success(f'Finished checking {total_rows} records!')
        if not wrong_users_list:
            st.balloons()
            st.success('All checked passwords were valid! (Or no invalid credentials matched the failure criteria).')
        else:
            st.error(f'Found {len(wrong_users_list)} invalid logins.')

with tabs[1]:
    st.subheader('Scrape Candidate Results')
    st.markdown("Run this to extract Marks, Rank, and Score from the GATE portal.")
    
    col3, col4 = st.columns([1, 1])
    with col3:
        scrape_test_limit = st.slider('Max records to scrape (0 = all)', min_value=0, max_value=len(dataset), value=0, key='scrape_lim')
    with col4:
        scrape_max_workers = st.slider('Concurrent Playwright Bots', min_value=1, max_value=20, value=4, key='scrape_work')
        
    start_scrape = st.button('Start Scraping Results', type='primary', key='scrape_btn')
    
    if start_scrape:
        progress_bar_2 = st.progress(0)
        status_text_2 = st.empty()
        st.markdown('### ✅ Successfully Scraped Results')
        results_table = st.empty()
        results_list = []
        
        rows_to_scrape = st.session_state.edited_dataset if scrape_test_limit == 0 else st.session_state.edited_dataset.head(scrape_test_limit)
        total_rows_scrape = len(rows_to_scrape)
        completed_scrape = 0
        status_text_2.text(f'Starting {scrape_max_workers} concurrent thread(s)...')
        
        import math
        chunk_size_2 = max(1, math.ceil(total_rows_scrape / scrape_max_workers))
        row_list_2 = list(rows_to_scrape.iterrows())
        chunks_2 = [row_list_2[i:i + chunk_size_2] for i in range(0, len(row_list_2), chunk_size_2)]
        
        all_success_results_2 = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=scrape_max_workers) as executor:
            futures_2 = {executor.submit(worker_verify_credential_chunk, chunk): chunk for chunk in chunks_2}
            
            for future in concurrent.futures.as_completed(futures_2):
                chunk_results = future.result()
                
                for idx, row, status, result in chunk_results:
                    completed_scrape += 1
                    progress_bar_2.progress(completed_scrape / total_rows_scrape)
                    status_text_2.text(f"Progress ({completed_scrape}/{total_rows_scrape}) - Scraped: {row.get('Username', '')}")
                    
                    if status == 'error':
                        st.toast(f"Error scraping {row.get('Username')}: {result}", icon='⚠️')
                    elif status == 'done':
                        if result:
                            all_success_results_2.append(result)
                        if result.status == 'success':
                            # Build row data for the table
                            row_data = {"Username": row.get('Username', '')}
                            if result.extracted:
                                row_data.update(result.extracted)
                            else:
                                row_data['Info'] = 'Results logged in, but not found on page.'
                                
                            results_list.append(row_data)
                            df_results = pd.DataFrame(results_list)
                            results_table.dataframe(df_results, use_container_width=True)
                                
        if all_success_results_2:
            db_repo.save_many_results(all_success_results_2)
            
        status_text_2.success(f'Finished scraping {total_rows_scrape} records!')

with tabs[2]:
    st.subheader('Single User Check')
    st.markdown("Manually check the results or validate credentials for a specific candidate without modifying the dataset.")
    
    with st.form("single_user_form"):
        col_u, col_p = st.columns(2)
        with col_u:
            single_user = st.text_input("Enrollment ID / Email")
        with col_p:
            single_pass = st.text_input("Password", type="password")
            
        submitted = st.form_submit_button("Fetch Result")
        
    if submitted:
        if not single_user or not single_pass:
            st.warning("Please enter both an Enrollment ID and Password.")
        else:
            with st.spinner("Logging into GATE portal..."):
                solver = CaptchaSolverFactory.create('ocr')
                client = PlaywrightPortalClient(base_url='https://goaps.iitg.ac.in/login', captcha_solver=solver, headless=True, timeout_ms=20000, max_captcha_attempts=8)
                
                cred = CandidateCredential(enrollment_id=single_user.strip(), password=single_pass.strip())
                
                try:
                    result = client.fetch_candidate_result(cred)
                    db_repo.save_result(result) 
                    
                    if result.status == 'success':
                        st.success(f"Successfully logged in as {single_user}!")
                        if result.extracted:
                            st.write("### Extracted Result Data")
                            st.json(result.extracted)
                        else:
                            st.warning("Logged in, but no score/result data was found on the page.")
                    else:
                        st.error(f"Failed to fetch: {result.message}")
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                finally:
                    client.close()
        
with tabs[3]:
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
