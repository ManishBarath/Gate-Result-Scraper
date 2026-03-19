with open('streamlit_app.py', 'r') as f:
    content = f.read()

target = """        db_df = db_repo.get_all_results_df()
        if not db_df.empty:
            st.dataframe(db_df, use_container_width=True)
            st.download_button('Download Database as CSV', db_df.to_csv(index=False).encode('utf-8'), 'gate_database_export.csv', 'text/csv')
            st.divider()"""

replacement = """        db_df = db_repo.get_all_results_df()
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
                
            st.divider()"""

content = content.replace(target, replacement)

with open('streamlit_app.py', 'w') as f:
    f.write(content)
