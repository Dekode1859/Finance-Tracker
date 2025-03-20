# This file is no longer needed as the functionality is integrated into app.py
# Keeping this file for reference or if you want to separate the Google API functionality

import os
import base64
from datetime import date
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Updated scopes to match the new required scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

def create_service():
    """Creates and returns an authenticated Gmail API service"""
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            # Handle scope changes gracefully
            flow.oauth2session.scope = SCOPES
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # Call the Gmail API
        service = build("gmail", "v1", credentials=creds)
        return service
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def get_user_info(service):
    """Get user information from Gmail API"""
    try:
        # Get user profile
        profile = service.users().getProfile(userId='me').execute()
        
        # Create user info dictionary
        user_info = {
            'user_id': profile['emailAddress'],  # Use email as user_id for simplicity
            'email': profile['emailAddress'],
            'name': None  # Gmail API doesn't provide name, we could use Google People API for that
        }
        
        return user_info
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def get_date_range_query(base_query, start_date=None, end_date=None):
    """Add date range to Gmail query"""
    if not start_date and not end_date:
        return base_query
    
    query_parts = [base_query]
    
    if start_date:
        # Format: YYYY/MM/DD
        formatted_start = start_date.strftime("%Y/%m/%d")
        query_parts.append(f"after:{formatted_start}")
    
    if end_date:
        # Format: YYYY/MM/DD
        formatted_end = end_date.strftime("%Y/%m/%d")
        query_parts.append(f"before:{formatted_end}")
    
    return " ".join(query_parts)

def fetch_transaction_emails(service, query='subject:"transaction alert"', start_date=None, end_date=None):
    """Fetch transaction emails from Gmail"""
    try:
        # Add date range to query
        full_query = get_date_range_query(query, start_date, end_date)
        print(f"Searching with query: {full_query}")
        
        results = service.users().messages().list(userId='me', q=full_query).execute()
        messages = results.get('messages', [])
        
        if not messages:
            print("No transaction emails found.")
            return []
        
        print(f"Found {len(messages)} transaction emails. Processing...")
        
        transactions = []
        
        for i, message in enumerate(messages):
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            
            # Get email body
            if 'parts' in msg['payload']:
                body = msg['payload']['parts'][0]['body'].get('data', '')
            else:
                body = msg['payload']['body'].get('data', '')
            
            if body:
                # Decode the body from base64
                body = base64.urlsafe_b64decode(body).decode('utf-8')
                
                # We'll import the extractor module in app.py to avoid circular imports
                # Just return the raw message data here
                message_data = {
                    'id': msg['id'],
                    'body': body,
                    'timestamp': int(msg['internalDate'])/1000
                }
                
                transactions.append(message_data)
        
        return transactions
    
    except HttpError as error:
        print(f"An error occurred: {error}")
        return []
