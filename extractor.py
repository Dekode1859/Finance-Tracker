import re
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_transaction_details(body, transaction_id):
    """Extract transaction details from email body using regex, focusing only on amount, type, and balance"""
    # Default values
    transaction = {
        'transaction_id': transaction_id,
        'transaction_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'transaction_amount': 0.0,
        'transaction_type': 'Unknown',
        'transaction_description': '',  # Empty by default
        'available_balance': 0.0,
        'account_number': '',  # Empty by default
        'email_body': body
    }
    
    # Try standard transaction format first
    amount_match = re.search(r'(Debited|Credited) for INR ([\d,]+\.\d+)', body)
    if amount_match:
        transaction['transaction_type'] = 'Debit' if amount_match.group(1) == 'Debited' else 'Credit'
        transaction['transaction_amount'] = float(amount_match.group(2).replace(',', ''))
        
        # Extract available balance
        balance_match = re.search(r'balance available in your Account is INR ([\d,]+\.\d+)', body)
        if balance_match:
            transaction['available_balance'] = float(balance_match.group(1).replace(',', ''))
    else:
        # Try payroll format
        payroll_match = re.search(r'credited for INR ([\d,]+(?:\.\d+)?)', body, re.IGNORECASE)
        if payroll_match:
            transaction['transaction_type'] = 'Credit'
            transaction['transaction_amount'] = float(payroll_match.group(1).replace(',', ''))
    
    # If still no transaction amount found, try a more generic approach
    if transaction['transaction_amount'] == 0.0:
        # Check for Induslnd Bank credit format
        induslnd_credit_match = re.search(r'has been credited for INR ([\d,]+(?:\.\d+)?)', body)
        if induslnd_credit_match:
            transaction['transaction_type'] = 'Credit'
            transaction['transaction_amount'] = float(induslnd_credit_match.group(1).replace(',', ''))
        else:
            # Look for any INR amount in the email
            generic_amount_match = re.search(r'INR\s+([\d,]+(?:\.\d+)?)', body)
            if generic_amount_match:
                # Determine if credit or debit based on context
                if 'credit' in body.lower() or 'credited' in body.lower():
                    transaction['transaction_type'] = 'Credit'
                elif 'debit' in body.lower() or 'debited' in body.lower():
                    transaction['transaction_type'] = 'Debit'
                
                transaction['transaction_amount'] = float(generic_amount_match.group(1).replace(',', ''))
    
    # Look for balance information that might have been missed
    if transaction['available_balance'] == 0.0:
        balance_match = re.search(r'(?:available|current) balance[:\s]+(?:is\s+)?(?:INR\s+)?([\d,]+(?:\.\d+)?)', body, re.IGNORECASE)
        if balance_match:
            transaction['available_balance'] = float(balance_match.group(1).replace(',', ''))
    
    return transaction

def process_email_messages(message_data_list):
    """Process raw email message data into transaction objects using regex extraction"""
    logger.info(f"Processing {len(message_data_list)} emails with regex extraction")
    transactions = []
    
    # Process all emails in one batch
    for message_data in message_data_list:
        try:
            transaction = extract_transaction_details(message_data['body'], message_data['id'])
            transaction['transaction_date'] = datetime.fromtimestamp(
                message_data['timestamp']
            ).strftime("%Y-%m-%d %H:%M:%S")
            transactions.append(transaction)
            logger.info(f"Successfully processed message {message_data['id']}")
        except Exception as e:
            logger.error(f"Failed to process message {message_data['id']}: {e}")
            continue
    
    logger.info(f"Completed processing. Extracted {len(transactions)} transactions")
    return transactions 