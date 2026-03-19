import time
import os
import json
import pandas as pd
import streamlit as st
import concurrent.futures
import logging

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("output/scraper.log", mode='a')
    ]
)
logger = logging.getLogger(__name__)

from gate_automation.core.models import CandidateCredential
from gate_automation.infrastructure.browser.playwright_client import PlaywrightPortalClient
from gate_automation.infrastructure.captcha.factory import CaptchaSolverFactory
from gate_automation.infrastructure.database import SQLiteResultRepository

st.set_page_config(page_title='GATE Credentials Checker', layout='wide')

# Setup Workspaces Directoy
WORKSPACES_DIR = "workspaces"
os.makedirs(WORKSPACES_DIR, exist_ok=True)

def get_workspaces():
    return [d for d in os.listdir(WORKSPACES_DIR) if os.path.isdir(os.path.join(WORKSPACES_DIR, d))]

def load_workspace_config(workspace_name):
    config_path = os.path.join(WORKSPACES_DIR, workspace_name, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)
    return {"data_file": None, "cutoff_oc": 30.0, "cutoff_obc": 27.0, "cutoff_sc": 20.0, "webpage_link": "https://goaps.iitg.ac.in/login"}

def save_workspace_config(workspace_name, config):
    config_path = os.path.join(WORKSPACES_DIR, workspace_name, "config.json")
    with open(config_path, "w") as f:
        json.dump(config, f)

# Navigation state
if "current_workspace" not in st.session_state:
    st.session_state.current_workspace = None

# HOME SCREEN
if st.session_state.current_workspace is None:
    st.title('Welcome to GATE Automation Workspace Manager')
    st.divider()

    st.subheader('Create New Workspace')
    new_ws_name = st.text_input('Workspace Name')
    if st.button('Create'):
        if new_ws_name:
            ws_path = os.path.join(WORKSPACES_DIR, new_ws_name)
            if not os.path.exists(ws_path):
                os.makedirs(ws_path)
                save_workspace_config(new_ws_name, {"data_file": None, "cutoff_oc": 30.0, "cutoff_obc": 27.0, "cutoff_sc": 20.0, "webpage_link": "https://goaps.iitg.ac.in/login"})
                st.success(f"Workspace '{new_ws_name}' created!")
                st.rerun()
            else:
                st.error("Workspace already exists.")

    st.divider()
    st.subheader('Existing Workspaces')
    workspaces = get_workspaces()
    if workspaces:
        for ws in workspaces:
            col1, col2 = st.columns([4, 1])
            col1.write(f"📁 **{ws}**")
            if col2.button('Open', key=f"open_{ws}"):
                st.session_state.current_workspace = ws
                st.rerun()
    else:
        st.info("No workspaces available. Create one above.")

# WORKSPACE SCREEN
else:
    ws_name = st.session_state.current_workspace
    config = load_workspace_config(ws_name)
    ws_dir = os.path.join(WORKSPACES_DIR, ws_name)
    
    # Each workspace gets its own database
    db_file = os.path.join(ws_dir, "gate_results.db")
    db_repo = SQLiteResultRepository(db_path=db_file)

    st.sidebar.title(f"Workspace: {ws_name}")
    if st.sidebar.button("← Back to Home"):
        st.session_state.current_workspace = None
        st.rerun()

    st.sidebar.subheader("Workspace Config")
    with st.sidebar.form("ws_config"):
        cutoff_oc = st.number_input("General/OC Cutoff", value=config.get("cutoff_oc", 30.0))
        cutoff_obc = st.number_input("OBC Cutoff", value=config.get("cutoff_obc", 27.0))
        cutoff_sc = st.number_input("SC/ST Cutoff", value=config.get("cutoff_sc", 20.0))
        webpage_link = st.text_input("Webpage Link", value=config.get("webpage_link", "https://goaps.iitg.ac.in/login"))
        st.markdown("**Required Columns:** `Username`, `Password`<br>**Optional:** `Category` (for pass/fail cutoffs), `Name of the Candidate`", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Upload Candidates Excel/CSV", type=["csv", "xlsx"])
        
        if st.form_submit_button("Save Config & Data"):
            config["cutoff_oc"] = cutoff_oc
            config["cutoff_obc"] = cutoff_obc
            config["cutoff_sc"] = cutoff_sc
            config["webpage_link"] = webpage_link
            
            if uploaded_file is not None:
                file_ext = uploaded_file.name.split('.')[-1]
                save_path = os.path.join(ws_dir, f"data.{file_ext}")
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                config["data_file"] = save_path
                
            save_workspace_config(ws_name, config)
            st.success("Configuration updated!")
            if "edited_dataset" in st.session_state:
                del st.session_state.edited_dataset
            st.rerun()

    st.title(f'GATE Students Validate - {ws_name}')

    @st.cache_data
    def load_and_clean_data(file_path):
        if not file_path or not os.path.exists(file_path):
            return pd.DataFrame()
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
        except Exception as e:
            st.error(f'Error reading file: {e}')
            return pd.DataFrame()
        
        df.columns = df.columns.str.strip()
        if 'Username' in df.columns:
            df['Username'] = df['Username'].astype(str).str.replace('\\s+', '', regex=True)
        if 'Password' in df.columns:
            df['Password'] = df['Password'].astype(str).str.strip()
            
        cat_col = next((col for col in df.columns if 'category' in col.lower()), None)
        if cat_col and cat_col != 'Category':
            df.rename(columns={cat_col: 'Category'}, inplace=True)
            
        return df

    dataset = load_and_clean_data(config.get("data_file"))

    if dataset.empty:
        st.warning("Please upload a CSV or Excel file via the sidebar config to proceed.")
        st.info("""
        ### 📄 Required CSV/Excel Formatting
        For the scraper to work correctly, ensure your uploaded file has the following column headers (exact spelling is recommended, though trailing spaces are ignored):
        
        - **`Username`** *(Required)*: The enrollment ID or email address used to log into the portal.
        - **`Password`** *(Required)*: The password for the GATE portal.
        - **`Category`** *(Highly Recommended)*: Used to determine PASS/FAIL status based on your custom cutoffs in the sidebar. (e.g., `General`, `OBC-NCL`, `SC`). The app will auto-detect any column with "Category" in its name.
        - **`Name of the Candidate`** *(Optional)*: If provided, this name will be used in the final saved database instead of the potentially slightly different name scraped from the portal to keep your records consistent.
        """)
        st.stop()

    if "edited_dataset" not in st.session_state:
        st.session_state.edited_dataset = dataset.copy()

    def worker_verify_credential_chunk(rows_chunk):
        results = []
        solver = CaptchaSolverFactory.create('ocr')
        client = PlaywrightPortalClient(base_url=config.get("webpage_link", "https://goaps.iitg.ac.in/login"), captcha_solver=solver, headless=True, timeout_ms=15000, max_captcha_attempts=8)
        try:
            for idx, row in rows_chunk:
                username = str(row.get('Username', '')).strip()
                password = str(row.get('Password', '')).strip()
                if not username or username.lower() in ['nan', 'na'] or not password or password.lower() in ['nan', 'na']:
                    results.append((idx, row, 'skip', None))
                    continue
                cred = CandidateCredential(enrollment_id=username, password=password)
                logger.info(f"Initiating credential payload for {username}")
                try:
                    result = client.fetch_candidate_result(cred)
                    if result.status == 'success':
                        logger.info(f"Successfully scraped portal for {username}")
                    else:
                        logger.warning(f"Failed to scrape {username}: {result.message}")
                    results.append((idx, row, 'done', result))
                except Exception as e:
                    results.append((idx, row, 'error', str(e)))
        finally:
            client.close()
        return results

    tabs = st.tabs(['Check Credentials Flow', 'Scrape Results', 'Single User Check', 'Database Records'])
    
    with tabs[0]:
        db_df_global = db_repo.get_all_results_df()
        if not db_df_global.empty:
            st.subheader('Overall Results Dashboard')
            c1, c2, c3, c4 = st.columns(4)
            tot_db = len(db_df_global)
            pf_col = 'pass_fail' if 'pass_fail' in db_df_global.columns else None
            st_col = 'status' if 'status' in db_df_global.columns else None
            
            passed_db = len(db_df_global[db_df_global[pf_col] == 'PASS']) if pf_col else 0
            failed_db = len(db_df_global[db_df_global[pf_col] == 'FAIL']) if pf_col else 0
            errors_db = len(db_df_global[db_df_global[st_col] != 'success']) if st_col else 0
            
            c1.metric("Total in DB", tot_db)
            c2.metric("Total Passed", passed_db)
            c3.metric("Failed (Cutoff)", failed_db)
            c4.metric("Failed Attempts", errors_db)
            
            name_map = {}
            if not dataset.empty and 'Username' in dataset.columns:
                name_col_csv = 'Name of the Candidate' if 'Name of the Candidate' in dataset.columns else 'Username'
                name_map = dict(zip(dataset['Username'].astype(str), dataset[name_col_csv].astype(str)))

            if st_col and errors_db > 0:
                with st.expander(f"View {errors_db} Failed Attempts (Login/Fetch Errors)"):
                    err_ids = db_df_global[db_df_global[st_col] != 'success']['enrollment_id'].astype(str).tolist()
                    err_data = []
                    for eid in err_ids:
                        name_display = name_map.get(eid, eid)
                        msg = db_df_global[db_df_global['enrollment_id'] == eid]['message'].iloc[0] if 'message' in db_df_global.columns else 'Unknown Error'
                        err_data.append({"Name": name_display, "ID": eid, "Error": msg})
                    st.dataframe(err_data, use_container_width=True, hide_index=True)

            if pf_col and failed_db > 0:
                with st.expander(f"View {failed_db} Students Failed by Cutoff"):
                    fail_ids = db_df_global[db_df_global[pf_col] == 'FAIL']['enrollment_id'].astype(str).tolist()
                    fail_data = []
                    for eid in fail_ids:
                        name_display = name_map.get(eid, eid)
                        marks_val = db_df_global[db_df_global['enrollment_id'] == eid]['marks'].iloc[0] if 'marks' in db_df_global.columns else 'N/A'
                        fail_data.append({"Name": name_display, "ID": eid, "Marks": marks_val})
                    st.dataframe(fail_data, use_container_width=True, hide_index=True)

            if pf_col and passed_db > 0:
                with st.expander(f"View {passed_db} Students Passed by Cutoff"):
                    pass_ids = db_df_global[db_df_global[pf_col] == 'PASS']['enrollment_id'].astype(str).tolist()
                    pass_data = []
                    for eid in pass_ids:
                        name_display = name_map.get(eid, eid)
                        marks_val = db_df_global[db_df_global['enrollment_id'] == eid]['marks'].iloc[0] if 'marks' in db_df_global.columns else 'N/A'
                        pass_data.append({"Name": name_display, "ID": eid, "Marks": marks_val})
                    st.dataframe(pass_data, use_container_width=True, hide_index=True)

            st.divider()

        st.subheader('Editable Data Overview')
        st.session_state.edited_dataset = st.data_editor(st.session_state.edited_dataset, use_container_width=True, num_rows="dynamic")
        
        st.divider()
        st.subheader('Validate Passwords')
        
        col1, col2 = st.columns([1, 1])
        with col1:
            test_limit = st.slider('Max records to test (0 = all)', 0, len(dataset), min(20, len(dataset)))
        with col2:
            max_workers = st.slider('Concurrent Bots', 1, 20, 4)
            
        if st.button('Start Checking', type='primary'):
            progress_bar = st.progress(0)
            status_text = st.empty()
            wrong_users_table = st.empty()
            wrong_users_list = []
            
            rows_to_check = st.session_state.edited_dataset if test_limit == 0 else st.session_state.edited_dataset.head(test_limit)
            total_rows = len(rows_to_check)
            completed = 0
            
            import math
            chunk_size = max(1, math.ceil(total_rows / max_workers))
            row_list = list(rows_to_check.iterrows())
            chunks = [row_list[i:i + chunk_size] for i in range(0, len(row_list), chunk_size)]
            all_success = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(worker_verify_credential_chunk, chunk): chunk for chunk in chunks}
                for future in concurrent.futures.as_completed(futures):
                    for idx, row, status, result in future.result():
                        completed += 1
                        progress_bar.progress(completed / total_rows)
                        status_text.text(f"Progress ({completed}/{total_rows})")
                        if status == 'done':
                            if result: all_success.append(result)
                            if result.status == 'failed':
                                wrong_users_list.append(row.to_dict())
                                wrong_users_table.dataframe(pd.DataFrame(wrong_users_list), use_container_width=True)
            if all_success: db_repo.save_many_results(all_success)
            status_text.success("Finished checking!")

    with tabs[1]:
        st.subheader('Scrape Candidate Results')
        col3, col4 = st.columns([1, 1])
        with col3:
            scrape_test_limit = st.slider('Max records to scrape (0 = all)', 0, len(dataset), 0, key='scrape_lim')
        with col4:
            scrape_max_workers = st.slider('Concurrent Bots', 1, 20, 4, key='scrape_work')
            
        skip_existing = st.checkbox("Skip successful results in Database", value=True)
        if st.button('Start Scraping', type='primary'):
            progress_bar_2 = st.progress(0)
            status_text_2 = st.empty()
            results_table = st.empty()
            results_list = []
            
            rows_to_scrape = st.session_state.edited_dataset if scrape_test_limit == 0 else st.session_state.edited_dataset.head(scrape_test_limit)
            if skip_existing:
                db_df = db_repo.get_all_results_df()
                if not db_df.empty and 'enrollment_id' in db_df.columns:
                    success_users = db_df[db_df['status'] == 'success']['enrollment_id'].astype(str).tolist()
                    rows_to_scrape = rows_to_scrape[~rows_to_scrape['Username'].astype(str).isin(success_users)]
            
            total_rows_scrape = len(rows_to_scrape)
            if total_rows_scrape == 0:
                st.success("No candidates left to scrape!")
                st.stop()
                
            completed_scrape = 0
            fetched_success = 0
            passed_count = 0
            failed_exam_count = 0
            failed_fetch_count = 0



            import math
            chunk_size_2 = max(1, math.ceil(total_rows_scrape / scrape_max_workers))
            row_list_2 = list(rows_to_scrape.iterrows())
            chunks_2 = [row_list_2[i:i + chunk_size_2] for i in range(0, len(row_list_2), chunk_size_2)]
            all_results_to_save = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=scrape_max_workers) as executor:
                futures_2 = {executor.submit(worker_verify_credential_chunk, chunk): chunk for chunk in chunks_2}
                for future in concurrent.futures.as_completed(futures_2):
                    for idx, row, status, result in future.result():
                        completed_scrape += 1
                        progress_bar_2.progress(completed_scrape / total_rows_scrape)
                        status_text_2.text(f"Progress ({completed_scrape}/{total_rows_scrape}) - Processing: {row.get('Username', '')}")
                        
                        row_data = {"Username": row.get('Username', '')}
                        
                        csv_name = str(row.get('Name of the Candidate', '')).strip()
                        if csv_name and csv_name.lower() not in ['nan', 'na', '']:
                            row_data['name'] = csv_name

                        if status == 'done' and result:
                            # Ensure URL is not saved in DB
                            if result.extracted and 'url' in result.extracted:
                                result.extracted.pop('url', None)

                            all_results_to_save.append(result)
                            
                            # Also overwrite the object's extracted name so it gets saved to DB
                            if csv_name and csv_name.lower() not in ['nan', 'na', '']:
                                if result.extracted is None:
                                    result.extracted = {}
                                result.extracted['name'] = csv_name

                            # Override success if marks were not extracted
                            if result.status == 'success' and (not result.extracted or 'marks' not in result.extracted):
                                result.status = 'failed'
                                result.message = 'Logged in successfully, but could not parse marks from the result page.'

                            if result.status == 'success':
                                fetched_success += 1
                                if result.extracted and 'marks' in result.extracted:
                                    try:
                                        marks_val = float(result.extracted['marks'])
                                        category = str(row.get('Category', 'GENERAL')).upper()
                                        cutoff = config["cutoff_oc"]
                                        if 'OBC' in category: cutoff = config["cutoff_obc"]
                                        elif 'SC' in category or 'ST' in category: cutoff = config["cutoff_sc"]
                                        
                                        result.extracted['pass_fail'] = 'PASS' if marks_val >= cutoff else 'FAIL'
                                        if result.extracted['pass_fail'] == 'PASS':
                                            passed_count += 1
                                        else:
                                            failed_exam_count += 1

                                        result.extracted['required_cutoff'] = str(cutoff)
                                        result.extracted['category_used'] = category
                                    except ValueError:
                                        result.extracted['pass_fail'] = 'UNKNOWN'
                                        
                                if result.extracted:
                                    row_data.update(result.extracted)
                                row_data['Fetch Status'] = 'Success'
                                row_data['Fail Reason'] = ''
                            else:
                                failed_fetch_count += 1
                                row_data['Fetch Status'] = 'Failed'
                                row_data['Fail Reason'] = result.message
                        else:
                            failed_fetch_count += 1
                            row_data['Fetch Status'] = 'Error'
                            row_data['Fail Reason'] = str(result)
                            
                        results_list.append(row_data)
            results_table.dataframe(pd.DataFrame(results_list), use_container_width=True)
                        

            if all_results_to_save: db_repo.save_many_results(all_results_to_save)
            status_text_2.success("Finished scraping!")


    with tabs[2]:
        st.subheader('Single User Check')
        with st.form("single_user_form"):
            single_user = st.text_input("Enrollment ID / Email")
            single_pass = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Fetch Result")
        if submitted:
            with st.spinner("Logging into GATE portal..."):
                solver = CaptchaSolverFactory.create('ocr')
                client = PlaywrightPortalClient(base_url=config.get("webpage_link", "https://goaps.iitg.ac.in/login"), captcha_solver=solver, headless=True, timeout_ms=20000, max_captcha_attempts=8)
                cred = CandidateCredential(enrollment_id=single_user.strip(), password=single_pass.strip())
                try:
                    result = client.fetch_candidate_result(cred)
                    db_repo.save_result(result)
                    if result.status == 'success':
                        st.success(f"Success for {single_user}!")
                        st.json(result.extracted)
                    else:
                        st.error(f"Failed: {result.message}")
                finally:
                    client.close()
                    
    with tabs[3]:
        st.subheader('Database Records Management')
        st.markdown('Here you can view, delete individually, or mass-clear your database entries.')
        
        db_df = db_repo.get_all_results_df()
        if not db_df.empty:
            st.info("You can edit cells directly inside this table! Once finished, click **Save DB Changes** below.")
            edited_db_df = st.data_editor(db_df, disabled=["enrollment_id"], use_container_width=True, num_rows="fixed")
            
            c_save, c_down = st.columns([1, 4])
            with c_save:
                if st.button("Save DB Changes", type='primary'):
                    db_repo.update_records_from_df(edited_db_df)
                    st.success("Database records updated successfully!")
            with c_down:
                st.download_button('Download Database as CSV', edited_db_df.to_csv(index=False).encode('utf-8'), 'gate_database_export.csv', 'text/csv')
                
            st.divider()
            
            st.subheader("Edit / Modify Records")
            col_admin1, col_admin2 = st.columns(2)
            
            with col_admin1:
                with st.form("delete_record_form"):
                    st.write("**Delete Specific Entry**")
                    target_id = st.text_input("Enrollment ID to delete from database:")
                    submit_del = st.form_submit_button("Delete Record")
                    if submit_del and target_id:
                        db_repo.delete_record(target_id.strip())
                        st.success(f"Deleted record {target_id}. Refresh to see changes.")
                        st.rerun()
                        
            with col_admin2:
                with st.form("clear_db_form"):
                    st.write("**DANGER: Wipe Entire Database**")
                    confirm = st.checkbox("I understand this deletes ALL data in this workspace's database forever.")
                    submit_clear = st.form_submit_button("Clear Database")
                    if submit_clear:
                        if confirm:
                            db_repo.clear_database()
                            st.success("Database wiped successfully.")
                            st.rerun()
                        else:
                            st.error("You must check the confirmation box.")
        else:
            st.info("Database is currently empty.")
