import streamlit as st
import pandas as pd
import base64
from datetime import datetime, date
import calendar
import uuid
import os
import logging

# Import our custom modules
import google_service
import db
import extractor

def main():
    st.set_page_config(page_title="Gmail Transaction Tracker", page_icon="💰", layout="wide")
    
    st.title("Gmail Transaction Tracker")
    st.write("Extract and track your transactions from Gmail")
    
    # Initialize database
    conn = db.init_db()
    
    # Initialize session state for user
    if 'user' not in st.session_state:
        st.session_state['user'] = None
    
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    
    # Show user info in sidebar if logged in
    if st.session_state.get('user'):
        st.sidebar.success(f"Logged in as: {st.session_state['user']['email']}")
        st.sidebar.button("Logout", on_click=logout_user)
    
    # Navigation options
    page = st.sidebar.radio("Go to", ["Login", "Dashboard", "Settings"])
    
    if page == "Login":
        st.header("Login with Google")
        
        # Add information about required permissions
        st.info("""
        This app requires the following permissions:
        - Read-only access to your Gmail messages to extract transaction details
        - Access to your email address for user identification
        
        Your data remains private and is stored only on your local machine.
        """)
        
        # Check if token.json exists and show a message if it does
        if os.path.exists("token.json") and not st.session_state.get('authenticated', False):
            st.warning("""
            A previous authentication token was found. If you're experiencing login issues, 
            you may need to clear the token and re-authenticate.
            """)
            if st.button("Clear Authentication Token"):
                try:
                    os.remove("token.json")
                    st.success("Authentication token cleared. Please try logging in again.")
                except Exception as e:
                    st.error(f"Error clearing token: {str(e)}")
        
        if st.button("Login with Google"):
            with st.spinner("Authenticating with Google..."):
                try:
                    service = google_service.create_service()
                    
                    if service:
                        # Get user info from Gmail
                        user_info = google_service.get_user_info(service)
                        
                        if user_info:
                            # Save user to database
                            db.save_user(conn, user_info['user_id'], user_info['email'], user_info['name'])
                            
                            # Store user in session state
                            st.session_state['user'] = user_info
                            st.session_state['authenticated'] = True
                            st.session_state['service'] = service
                            
                            st.success(f"Authentication successful! Logged in as {user_info['email']}")
                        else:
                            st.error("Failed to get user information. Please try again.")
                    else:
                        st.error("Authentication failed. Please try again.")
                except Exception as e:
                    st.error(f"Authentication error: {str(e)}")
                    st.info("If you're experiencing scope change warnings, try clearing the authentication token and logging in again.")
        
        if st.session_state.get('authenticated', False) and st.session_state.get('user'):
            st.success(f"You are logged in as {st.session_state['user']['email']}")
            
            # Get current user ID
            user_id = st.session_state['user']['user_id']
            
            # Load extraction settings and update extractor flags
            use_llm_extraction = db.get_setting(conn, user_id, "use_llm_extraction", "false").lower() == "true"
            use_parallel_llm = db.get_setting(conn, user_id, "use_parallel_llm_extraction", "true").lower() == "true"
            
            # Set extractor flags based on saved settings
            extractor.USE_LLM_EXTRACTION = use_llm_extraction
            extractor.USE_PARALLEL_LLM_EXTRACTION = use_parallel_llm
            
            # Log which extraction method is being used
            if use_parallel_llm:
                logging.info("Starting with parallel LLM extraction enabled")
            elif use_llm_extraction:
                logging.info("Starting with regular LLM extraction enabled")
            else:
                logging.info("Starting with regex extraction enabled")
            
            # Create tabs for different fetch options
            fetch_tabs = st.tabs(["Quick Fetch", "Custom Fetch"])
            
            # Tab 1: Quick Fetch
            with fetch_tabs[0]:
                st.subheader("Quick Fetch")
                
                # Date range selection
                st.write("Select Date Range")
                
                # Get payroll day from settings
                payroll_day_str = db.get_setting(conn, user_id, "payroll_day", "1")
                try:
                    payroll_day = int(payroll_day_str)
                except ValueError:
                    payroll_day = 1
                
                # Date selection options
                date_selection_options = [
                    "Current Month",
                    "Last 3 Months",
                    "Last 6 Months",
                    "Last Year",
                    "Current Payroll Cycle",
                    "Last Payroll Cycle",
                    "Custom Date Range"
                ]
                
                # Get default date range from user settings
                default_date_range = db.get_setting(conn, user_id, "default_date_range", "Current Month")
                default_index = date_selection_options.index(default_date_range) if default_date_range in date_selection_options else 0
                
                date_selection = st.selectbox(
                    "Date Range", 
                    options=date_selection_options,
                    index=default_index
                )
                
                # Get default dates based on selection
                today = date.today()
                default_start, default_end = db.get_current_month_dates()
                
                if date_selection == "Current Payroll Cycle":
                    default_start, default_end = db.get_payroll_date_range(payroll_day)
                    st.info(f"Current payroll cycle: {default_start} to {default_end}")
                elif date_selection == "Last Payroll Cycle":
                    default_start, default_end = db.get_payroll_date_range(payroll_day, months_back=1)
                    st.info(f"Last payroll cycle: {default_start} to {default_end}")
                elif date_selection == "Last 3 Months":
                    default_start = date(today.year, today.month, 1) - pd.Timedelta(days=90)
                    default_end = today
                elif date_selection == "Last 6 Months":
                    default_start = date(today.year, today.month, 1) - pd.Timedelta(days=180)
                    default_end = today
                elif date_selection == "Last Year":
                    default_start = date(today.year - 1, today.month, today.day)
                    default_end = today
                
                # Only show date inputs for custom range
                if date_selection == "Custom Date Range":
                    col1, col2 = st.columns(2)
                    with col1:
                        start_date = st.date_input("Start Date", value=default_start)
                    with col2:
                        end_date = st.date_input("End Date", value=default_end)
                else:
                    start_date = default_start
                    end_date = default_end
                
                # Get default query from user settings
                default_query = db.get_setting(conn, user_id, "default_query", 'subject:"transaction alert"')
                
                if st.button("Fetch Transaction Emails", key="quick_fetch"):
                    with st.spinner("Fetching transaction emails..."):
                        try:
                            # Get raw email data from Gmail
                            message_data_list = google_service.fetch_transaction_emails(
                                st.session_state['service'],
                                query=default_query,
                                start_date=start_date,
                                end_date=end_date
                            )
                            
                            if message_data_list:
                                # Process email messages
                                with st.spinner('Processing email messages, this may take some time...'):
                                    # Get batch size and worker settings
                                    batch_size = int(db.get_setting(conn, user_id, "parallel_batch_size", "10"))
                                    max_workers = int(db.get_setting(conn, user_id, "parallel_max_workers", "4"))
                                    max_retries = int(db.get_setting(conn, user_id, "max_retries", "3"))
                                    field_retries = int(db.get_setting(conn, user_id, "field_retries", "2"))
                                    
                                    transactions = extractor.process_email_messages(
                                        message_data_list,
                                        batch_size=batch_size,
                                        max_workers=max_workers,
                                        max_retries=max_retries,
                                        field_retries=field_retries
                                    )
                                
                                # Save transactions to database with user ID
                                saved_count = db.save_transactions_to_db(conn, user_id, transactions)
                                st.success(f"Successfully saved {saved_count} transactions to database!")
                                
                                # Show sample of transactions
                                st.subheader("Sample of Fetched Transactions")
                                df = pd.DataFrame(transactions[:5])
                                st.dataframe(df)
                            else:
                                st.warning("No transaction emails found for the selected date range.")
                        except Exception as e:
                            st.error(f"Error fetching emails: {str(e)}")
                            st.info("If you're experiencing authentication issues, try logging out and logging back in.")
            
            # Tab 2: Custom Fetch
            with fetch_tabs[1]:
                st.subheader("Custom Fetch")
                
                # Custom Query
                default_query = db.get_setting(conn, user_id, "default_query", 'subject:"transaction alert"')
                custom_query = st.text_input("Gmail Search Query", value=default_query)
                
                # Date range for custom query
                st.write("Date Range for Custom Query")
                default_start, default_end = db.get_current_month_dates()
                
                col1, col2 = st.columns(2)
                with col1:
                    custom_start_date = st.date_input("Start Date", value=default_start, key="custom_start")
                with col2:
                    custom_end_date = st.date_input("End Date", value=default_end, key="custom_end")
                
                if st.button("Fetch with Custom Query", key="custom_fetch"):
                    with st.spinner(f"Fetching emails with query: {custom_query}"):
                        try:
                            # Get raw email data from Gmail
                            message_data_list = google_service.fetch_transaction_emails(
                                st.session_state['service'], 
                                query=custom_query,
                                start_date=custom_start_date,
                                end_date=custom_end_date
                            )
                            
                            if message_data_list:
                                # Process email messages
                                with st.spinner('Processing email messages, this may take some time...'):
                                    # Get batch size and worker settings
                                    batch_size = int(db.get_setting(conn, user_id, "parallel_batch_size", "10"))
                                    max_workers = int(db.get_setting(conn, user_id, "parallel_max_workers", "4"))
                                    max_retries = int(db.get_setting(conn, user_id, "max_retries", "3"))
                                    field_retries = int(db.get_setting(conn, user_id, "field_retries", "2"))
                                    
                                    transactions = extractor.process_email_messages(
                                        message_data_list,
                                        batch_size=batch_size,
                                        max_workers=max_workers,
                                        max_retries=max_retries,
                                        field_retries=field_retries
                                    )
                                
                                # Save transactions to database with user ID
                                saved_count = db.save_transactions_to_db(conn, user_id, transactions)
                                st.success(f"Successfully saved {saved_count} transactions to database!")
                                
                                # Save the custom query as default if it's different
                                if custom_query != default_query:
                                    if st.button("Save this query as default"):
                                        db.save_setting(conn, user_id, "default_query", custom_query)
                                        st.success("Query saved as default!")
                            else:
                                st.warning("No transaction emails found for the selected query and date range.")
                        except Exception as e:
                            st.error(f"Error fetching emails: {str(e)}")
                            st.info("If you're experiencing authentication issues, try logging out and logging back in.")
    
    elif page == "Dashboard":
        st.header("Transaction Dashboard")
        
        if not st.session_state.get('authenticated', False) or not st.session_state.get('user'):
            st.warning("Please login first to view your transactions.")
            return
        
        # Get current user ID
        user_id = st.session_state['user']['user_id']
        
        # Get user settings
        currency_symbol = db.get_setting(conn, user_id, "currency_symbol", "₹")
        default_date_range = db.get_setting(conn, user_id, "default_date_range", "Current Month")
        
        # Get transactions from database for current user
        df = db.get_transactions_from_db(conn, user_id)
        
        if df.empty:
            st.info("No transactions found. Please fetch transactions from the Login page.")
            return
        
        # Convert transaction_date to datetime for filtering
        df['transaction_date'] = pd.to_datetime(df['transaction_date'])
        
        # Get payroll day from settings
        payroll_day_str = db.get_setting(conn, user_id, "payroll_day", "1")
        try:
            payroll_day = int(payroll_day_str)
        except ValueError:
            payroll_day = 1
        
        # Date filter options
        date_filter_options = [
            "All Time",
            "Current Month",
            "Last Month",
            "Current Payroll Cycle",
            "Last Payroll Cycle",
            "Custom Date Range"
        ]
        
        # Set default date filter based on user settings
        default_index = 0  # All Time by default
        if default_date_range in date_filter_options:
            default_index = date_filter_options.index(default_date_range)
        elif default_date_range == "Last 3 Months" or default_date_range == "Last 6 Months" or default_date_range == "Last Year":
            default_index = 0  # Default to All Time if the saved preference isn't in the dashboard options
        
        date_filter = st.selectbox(
            "Date Filter", 
            options=date_filter_options,
            index=default_index
        )
        
        # Set date range based on selection
        if date_filter == "Current Month":
            filter_start_date, filter_end_date = db.get_current_month_dates()
        elif date_filter == "Last Month":
            today = date.today()
            last_month = today.month - 1
            last_year = today.year
            if last_month == 0:
                last_month = 12
                last_year -= 1
            _, last_day = calendar.monthrange(last_year, last_month)
            filter_start_date = date(last_year, last_month, 1)
            filter_end_date = date(last_year, last_month, last_day)
        elif date_filter == "Current Payroll Cycle":
            filter_start_date, filter_end_date = db.get_payroll_date_range(payroll_day)
        elif date_filter == "Last Payroll Cycle":
            filter_start_date, filter_end_date = db.get_payroll_date_range(payroll_day, months_back=1)
        elif date_filter == "Custom Date Range":
            # Date range filter for dashboard
            st.subheader("Custom Date Range")
            col1, col2 = st.columns(2)
            
            min_date = df['transaction_date'].min().date()
            max_date = df['transaction_date'].max().date()
            
            with col1:
                filter_start_date = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
            with col2:
                filter_end_date = st.date_input("To", value=max_date, min_value=min_date, max_value=max_date)
        else:  # All Time
            filter_start_date = df['transaction_date'].min().date()
            filter_end_date = df['transaction_date'].max().date()
        
        # Display selected date range
        if date_filter != "All Time" and date_filter != "Custom Date Range":
            st.info(f"Selected date range: {filter_start_date} to {filter_end_date}")
        
        # Convert to datetime for filtering
        filter_start = pd.Timestamp(filter_start_date)
        filter_end = pd.Timestamp(filter_end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        
        # Apply date filter
        if date_filter != "All Time":
            date_filtered_df = df[(df['transaction_date'] >= filter_start) & (df['transaction_date'] <= filter_end)]
        else:
            date_filtered_df = df
        
        # Display transaction statistics
        st.subheader("Transaction Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Transactions", len(date_filtered_df))
        
        with col2:
            debit_sum = date_filtered_df[date_filtered_df['transaction_type'] == 'Debit']['transaction_amount'].sum()
            st.metric("Total Debits", f"{currency_symbol}{debit_sum:,.2f}")
        
        with col3:
            credit_sum = date_filtered_df[date_filtered_df['transaction_type'] == 'Credit']['transaction_amount'].sum()
            st.metric("Total Credits", f"{currency_symbol}{credit_sum:,.2f}")
        
        with col4:
            net_flow = credit_sum - debit_sum
            st.metric("Net Cash Flow", f"{currency_symbol}{net_flow:,.2f}", delta=f"{net_flow:,.2f}")
        
        # Find payroll transactions
        payroll_keywords_str = db.get_setting(conn, user_id, "payroll_keywords", "salary,payroll,wage,income")
        payroll_keywords = [keyword.strip() for keyword in payroll_keywords_str.split(",")]
        
        # Look for potential payroll/salary based on transaction amount instead of description
        payroll_transactions = None
        try:
            # Try to identify the largest credit transaction as potential payroll
            if not date_filtered_df.empty and 'Credit' in date_filtered_df['transaction_type'].values:
                payroll_transactions = date_filtered_df[date_filtered_df['transaction_type'] == 'Credit'].nlargest(1, 'transaction_amount')
                
                # Display potential salary information
                if not payroll_transactions.empty:
                    largest_credit = payroll_transactions.iloc[0]
                    st.info(f"Potential Salary/Income: {currency_symbol}{largest_credit['transaction_amount']:,.2f} on {largest_credit['transaction_date'].strftime('%Y-%m-%d')}")
        except Exception as e:
            st.error(f"Error detecting potential salary: {e}")
        
        # Transaction filters
        st.subheader("Filter Transactions")
        col1, col2 = st.columns(2)
        
        with col1:
            # Remove account_number filter as it's not being extracted anymore
            pass
        
        with col2:
            # Only show transaction type filter
            type_filter = st.multiselect("Transaction Type", date_filtered_df['transaction_type'].unique())
        
        # Update the filtering section
        filtered_df = date_filtered_df
        
        # if account_filter:
        #    filtered_df = filtered_df[filtered_df['account_number'].isin(account_filter)]
        
        if type_filter:
            filtered_df = filtered_df[filtered_df['transaction_type'].isin(type_filter)]
        
        display_df = filtered_df.copy()
        
        # Format currency values
        display_df['transaction_amount'] = display_df['transaction_amount'].apply(lambda x: f"{currency_symbol}{x:,.2f}")
        display_df['available_balance'] = display_df['available_balance'].apply(lambda x: f"{currency_symbol}{x:,.2f}" if pd.notnull(x) else "")
        
        # Remove transaction_description and account_number from display
        st.dataframe(display_df[['transaction_date', 'transaction_type', 
                                'transaction_amount', 'available_balance']])
        
        # Download as CSV
        if st.button("Download as CSV"):
            csv = filtered_df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="transactions.csv">Download CSV File</a>'
            st.markdown(href, unsafe_allow_html=True)
    
    elif page == "Settings":
        st.header("Settings")
        
        if not st.session_state.get('authenticated', False) or not st.session_state.get('user'):
            st.warning("Please login first to access settings.")
            return
        
        # Get current user ID
        user_id = st.session_state['user']['user_id']
        
        # Create tabs for different settings categories
        tabs = st.tabs(["Payroll Settings", "Display Settings", "Email Settings", "Advanced Settings"])
        
        # Tab 1: Payroll Settings
        with tabs[0]:
            st.subheader("Payroll Settings")
            
            # Get current payroll day from settings
            current_payroll_day = db.get_setting(conn, user_id, "payroll_day", "1")
            try:
                current_payroll_day = int(current_payroll_day)
            except ValueError:
                current_payroll_day = 1
            
            payroll_day = st.number_input(
                "Payroll Day of Month", 
                min_value=1, 
                max_value=31, 
                value=current_payroll_day,
                help="The day of the month when you typically receive your salary"
            )
            
            # Payroll keywords
            current_payroll_keywords = db.get_setting(conn, user_id, "payroll_keywords", "salary,payroll,wage,income")
            payroll_keywords = st.text_input(
                "Payroll Keywords (comma separated)", 
                value=current_payroll_keywords,
                help="Keywords to identify payroll transactions in your bank statements"
            )
            
            if st.button("Save Payroll Settings"):
                db.save_setting(conn, user_id, "payroll_day", str(payroll_day))
                db.save_setting(conn, user_id, "payroll_keywords", payroll_keywords)
                st.success("Payroll settings saved successfully!")
        
        # Tab 2: Display Settings
        with tabs[1]:
            st.subheader("Display Settings")
            
            # Currency symbol
            current_currency = db.get_setting(conn, user_id, "currency_symbol", "₹")
            currency_symbol = st.text_input(
                "Currency Symbol", 
                value=current_currency,
                help="The currency symbol to display with transaction amounts"
            )
            
            # Default date range
            date_range_options = [
                "Current Month",
                "Last 3 Months",
                "Last 6 Months",
                "Last Year",
                "Current Payroll Cycle",
                "Last Payroll Cycle",
                "Custom Date Range"
            ]
            
            current_default_date_range = db.get_setting(conn, user_id, "default_date_range", "Current Month")
            default_date_range = st.selectbox(
                "Default Date Range", 
                options=date_range_options,
                index=date_range_options.index(current_default_date_range) if current_default_date_range in date_range_options else 0,
                help="The default date range to use when viewing transactions"
            )
            
            # Theme preference
            theme_options = ["Light", "Dark"]
            current_theme = db.get_setting(conn, user_id, "theme", "Light")
            theme = st.selectbox(
                "Theme", 
                options=theme_options,
                index=theme_options.index(current_theme) if current_theme in theme_options else 0,
                help="The visual theme for the application"
            )
            
            if st.button("Save Display Settings"):
                db.save_setting(conn, user_id, "currency_symbol", currency_symbol)
                db.save_setting(conn, user_id, "default_date_range", default_date_range)
                db.save_setting(conn, user_id, "theme", theme)
                st.success("Display settings saved successfully!")
        
        # Tab 3: Email Settings
        with tabs[2]:
            st.subheader("Email Settings")
            
            # Default email search query
            current_query = db.get_setting(conn, user_id, "default_query", 'subject:"transaction alert"')
            default_query = st.text_input(
                "Default Email Search Query", 
                value=current_query,
                help="The default Gmail search query to use when fetching transaction emails"
            )
            
            # Bank email domains
            current_domains = db.get_setting(conn, user_id, "bank_domains", "bank.com,banking.com")
            bank_domains = st.text_input(
                "Bank Email Domains (comma separated)", 
                value=current_domains,
                help="Email domains from your banks to prioritize in searches"
            )
            
            # Transaction email labels
            current_labels = db.get_setting(conn, user_id, "transaction_labels", "Transactions,Banking,Finance")
            transaction_labels = st.text_input(
                "Transaction Email Labels (comma separated)", 
                value=current_labels,
                help="Gmail labels that contain your transaction emails"
            )
            
            if st.button("Save Email Settings"):
                db.save_setting(conn, user_id, "default_query", default_query)
                db.save_setting(conn, user_id, "bank_domains", bank_domains)
                db.save_setting(conn, user_id, "transaction_labels", transaction_labels)
                st.success("Email settings saved successfully!")
        
        # Tab 4: Advanced Settings
        with tabs[3]:
            st.subheader("Advanced Settings")
            
            # Database Management
            st.write("Database Management")
            
            if st.button("Clear My Transactions"):
                if st.session_state.get('authenticated', False):
                    db.clear_transactions_db(conn, user_id)
                    st.success("Your transactions have been cleared successfully!")
                else:
                    st.warning("Please login first to manage the database.")
            
            # LLM Extraction Settings
            st.write("LLM Extraction Settings")
            
            # Check if Ollama is available for either extraction method
            try:
                try:
                    from parallel_llm_extraction import test_ollama_connection as test_parallel_ollama
                    parallel_ollama_available = test_parallel_ollama()
                except ImportError:
                    parallel_ollama_available = False
                
                try:
                    from extractor_llm import test_ollama_connection as test_regular_ollama
                    regular_ollama_available = test_regular_ollama()
                except ImportError:
                    regular_ollama_available = False
                
                ollama_available = parallel_ollama_available or regular_ollama_available
            except Exception:
                ollama_available = False
            
            if ollama_available:
                # Get current LLM extraction settings
                use_llm_extraction = db.get_setting(conn, user_id, "use_llm_extraction", "false").lower() == "true"
                use_parallel_llm = db.get_setting(conn, user_id, "use_parallel_llm_extraction", "true").lower() == "true"
                
                # Create radio selection for extraction method
                extraction_method = st.radio(
                    "Transaction Extraction Method",
                    ["Regex (Basic)", "Regular LLM", "Parallel LLM (Recommended)"],
                    index=2 if use_parallel_llm else (1 if use_llm_extraction else 0),
                    help="Choose how to extract transaction details from emails"
                )
                
                # Batch size and worker settings for parallel processing
                if extraction_method == "Parallel LLM (Recommended)":
                    col1, col2 = st.columns(2)
                    with col1:
                        parallel_batch_size = st.number_input(
                            "Batch Size", 
                            min_value=1, 
                            max_value=50, 
                            value=int(db.get_setting(conn, user_id, "parallel_batch_size", "10")),
                            help="Number of emails to process in each batch"
                        )
                    
                    with col2:
                        max_workers = st.number_input(
                            "Max Workers", 
                            min_value=1, 
                            max_value=8, 
                            value=int(db.get_setting(conn, user_id, "parallel_max_workers", "4")),
                            help="Maximum number of parallel workers for extraction"
                        )
                    
                    # Add new row for retry configuration
                    col1, col2 = st.columns(2)
                    with col1:
                        max_retries = st.number_input(
                            "Message Retries",
                            min_value=0,
                            max_value=5,
                            value=int(db.get_setting(conn, user_id, "max_retries", "3")),
                            help="Number of times to retry processing a message that failed"
                        )
                    
                    with col2:
                        field_retries = st.number_input(
                            "Field Retries",
                            min_value=0,
                            max_value=5,
                            value=int(db.get_setting(conn, user_id, "field_retries", "2")),
                            help="Number of times to retry extracting individual fields before giving up"
                        )
                
                # Information about LLM extraction methods
                if extraction_method == "Regular LLM":
                    st.info("""
                    Regular LLM extraction uses a single Ollama model to extract all transaction details at once.
                    This is more efficient than regex but less accurate than parallel extraction.
                    """)
                elif extraction_method == "Parallel LLM (Recommended)":
                    st.info("""
                    Parallel LLM extraction uses multiple specialized Ollama models to extract different 
                    transaction details in parallel. This provides the most accurate results but uses 
                    more computational resources.
                    
                    This method uses Qwen 0.5B, a lightweight but capable model that's optimized for extraction tasks.
                    """)
                else:
                    st.info("""
                    Regex extraction uses pattern matching to extract transaction details. 
                    This is the most basic method and doesn't require Ollama, but it's less accurate 
                    for complex or non-standard email formats.
                    """)
                
                if st.button("Save Extraction Settings"):
                    # Update settings based on selected method
                    if extraction_method == "Parallel LLM (Recommended)":
                        db.save_setting(conn, user_id, "use_parallel_llm_extraction", "true")
                        db.save_setting(conn, user_id, "use_llm_extraction", "false")
                        db.save_setting(conn, user_id, "parallel_batch_size", str(parallel_batch_size))
                        db.save_setting(conn, user_id, "parallel_max_workers", str(max_workers))
                        db.save_setting(conn, user_id, "max_retries", str(max_retries))
                        db.save_setting(conn, user_id, "field_retries", str(field_retries))
                        
                        # Update extractor flags
                        extractor.USE_PARALLEL_LLM_EXTRACTION = True
                        extractor.USE_LLM_EXTRACTION = False
                    elif extraction_method == "Regular LLM":
                        db.save_setting(conn, user_id, "use_parallel_llm_extraction", "false")
                        db.save_setting(conn, user_id, "use_llm_extraction", "true")
                        
                        # Update extractor flags
                        extractor.USE_PARALLEL_LLM_EXTRACTION = False
                        extractor.USE_LLM_EXTRACTION = True
                    else:  # Regex
                        db.save_setting(conn, user_id, "use_parallel_llm_extraction", "false")
                        db.save_setting(conn, user_id, "use_llm_extraction", "false")
                        
                        # Update extractor flags
                        extractor.USE_PARALLEL_LLM_EXTRACTION = False
                        extractor.USE_LLM_EXTRACTION = False
                    
                    st.success("Extraction settings saved successfully!")
                    st.info("The setting will take effect the next time you fetch transaction emails.")
                
                # Add debugging information option
                if st.button("Debug Extraction Configuration"):
                    debug_info = extractor.get_extraction_config_info()
                    
                    # Display active method
                    if debug_info["active_method"] == "parallel_llm":
                        st.success("🟢 Active method: Parallel LLM extraction")
                    elif debug_info["active_method"] == "regular_llm":
                        st.success("🟡 Active method: Regular LLM extraction")
                    else:
                        st.warning("⚠️ Active method: Regex extraction (fallback)")
                    
                    # Display configuration details in an expander
                    with st.expander("View detailed configuration"):
                        st.write("### Settings")
                        st.json({
                            "USE_PARALLEL_LLM_EXTRACTION": debug_info["USE_PARALLEL_LLM_EXTRACTION"],
                            "USE_LLM_EXTRACTION": debug_info["USE_LLM_EXTRACTION"],
                            "Retry Settings": debug_info["retry_settings"]
                        })
                        
                        st.write("### Availability")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("Parallel LLM")
                            if debug_info["parallel_available"]:
                                st.success("✅ Available")
                            else:
                                st.error("❌ Not Available")
                                if "parallel_availability_error" in debug_info:
                                    st.error(f"Error: {debug_info['parallel_availability_error']}")
                        
                        with col2:
                            st.write("Regular LLM")
                            if debug_info["regular_available"]:
                                st.success("✅ Available")
                            else:
                                st.error("❌ Not Available")
                                if "regular_availability_error" in debug_info:
                                    st.error(f"Error: {debug_info['regular_availability_error']}")
                    
                    # Provide a troubleshooting guide
                    with st.expander("Troubleshooting Guide"):
                        st.markdown("""
                        ### Common Issues
                        
                        1. **Ollama not running**
                           - Make sure Ollama is installed and running on your system
                           - Try running `ollama list` in your terminal to check
                        
                        2. **Missing models**
                           - Models are downloaded automatically when first used
                           - You can manually download: `ollama pull qwen:0.5b` or `ollama pull deepseek-r1:8b`
                        
                        3. **Network issues**
                           - Check if Ollama can connect to the internet for model downloads
                           - Ollama uses port 11434 by default, make sure it's not blocked
                        
                        4. **Missing modules**
                           - Run `pip install -r requirements.txt` to install all dependencies
                           - Specifically make sure `pip install ollama agno` is run
                        """)
                    
                    # Stats about CPU/RAM usage
                    with st.expander("System Resource Usage"):
                        import psutil
                        
                        st.write(f"CPU Usage: {psutil.cpu_percent()}%")
                        st.write(f"RAM Usage: {psutil.virtual_memory().percent}%")
                        st.write(f"Available RAM: {psutil.virtual_memory().available / (1024 * 1024 * 1024):.2f} GB")
            else:
                st.warning("""
                LLM extraction methods are not available. To enable these features:
                1. Install Ollama from https://ollama.ai
                2. Install the required Python packages: `pip install ollama`
                3. Restart the application
                
                For parallel extraction, the Qwen 0.5B model will be automatically downloaded when needed.
                """)
            
            # Export/Import Settings
            st.write("Export/Import Settings")
            
            if st.button("Export All Settings"):
                # Get all user settings
                settings = db.get_all_user_settings(conn, user_id)
                if settings:
                    # Convert to JSON and create download link
                    settings_json = pd.DataFrame(settings).to_json(orient="records")
                    b64 = base64.b64encode(settings_json.encode()).decode()
                    href = f'<a href="data:application/json;base64,{b64}" download="settings.json">Download Settings</a>'
                    st.markdown(href, unsafe_allow_html=True)
                else:
                    st.warning("No settings found to export.")
            
            # Import settings
            uploaded_file = st.file_uploader("Import Settings", type="json")
            if uploaded_file is not None:
                try:
                    settings_data = pd.read_json(uploaded_file)
                    if not settings_data.empty:
                        # Import each setting
                        for _, row in settings_data.iterrows():
                            db.save_setting(conn, user_id, row['setting_key'], row['setting_value'])
                        st.success("Settings imported successfully!")
                except Exception as e:
                    st.error(f"Error importing settings: {str(e)}")
            
            # Authentication
            st.write("Authentication")
            
            if st.button("Clear Authentication Token"):
                try:
                    if os.path.exists("token.json"):
                        os.remove("token.json")
                        st.success("Authentication token cleared. Please log out and log back in.")
                except Exception as e:
                    st.error(f"Error clearing token: {str(e)}")

def logout_user():
    """Logout the current user"""
    st.session_state['user'] = None
    st.session_state['authenticated'] = False
    if 'service' in st.session_state:
        del st.session_state['service']
    
    # Optionally remove token.json to force re-authentication
    if os.path.exists("token.json"):
        try:
            os.remove("token.json")
            print("Token file removed during logout")
        except Exception as e:
            print(f"Error removing token file: {str(e)}")

if __name__ == "__main__":
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
    
    main()
