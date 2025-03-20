import re
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flags to determine which extraction method to use
USE_LLM_EXTRACTION = False
USE_PARALLEL_LLM_EXTRACTION = False

# Try to import the parallel LLM extractor (preferred)
try:
    from parallel_llm_extraction import process_email_messages_with_parallel_llm, test_ollama_connection
    # Test if Ollama is available
    if test_ollama_connection():
        USE_PARALLEL_LLM_EXTRACTION = True
        logger.info("Parallel LLM extraction is available and will be used by default")
    else:
        logger.warning("Parallel LLM extraction is not available, will try regular LLM extraction")
except ImportError:
    logger.warning("parallel_llm_extraction module not found, will try regular LLM extraction")
except Exception as e:
    logger.error(f"Error initializing parallel LLM extraction: {e}")

# Try to import the regular LLM extractor (fallback)
if not USE_PARALLEL_LLM_EXTRACTION:
    try:
        from extractor_llm import process_email_messages_with_llm, test_ollama_connection
        # Test if Ollama is available
        if test_ollama_connection():
            USE_LLM_EXTRACTION = True
            logger.info("Regular LLM extraction is available and will be used")
        else:
            logger.warning("Regular LLM extraction is not available, falling back to regex extraction")
    except ImportError:
        logger.warning("extractor_llm module not found, using regex extraction only")
    except Exception as e:
        logger.error(f"Error initializing LLM extraction: {e}")

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

def process_email_messages(message_data_list, batch_size=10, max_workers=4, max_retries=3, field_retries=2):
    """Process raw email message data into transaction objects
    
    Args:
        message_data_list: List of email message data dictionaries
        batch_size: Number of messages to process in each batch (for LLM processing)
        max_workers: Maximum number of parallel workers (for parallel LLM processing)
        max_retries: Maximum number of retry attempts for failed messages (default: 3)
        field_retries: Number of retries for individual field extractions (default: 2)
    """
    # Use parallel LLM processing if available (preferred)
    if USE_PARALLEL_LLM_EXTRACTION:
        try:
            logger.info(f"Using parallel LLM extraction with {max_workers} workers, batch size {batch_size}, and retries {max_retries}/{field_retries}")
            return process_email_messages_with_parallel_llm(
                message_data_list, 
                batch_size=batch_size, 
                max_workers=max_workers,
                max_retries=max_retries,
                field_retries=field_retries
            )
        except Exception as e:
            logger.error(f"Parallel LLM processing failed, falling back to regular LLM extraction: {e}")
            
    # Use regular LLM processing if available and parallel failed
    if USE_LLM_EXTRACTION:
        try:
            logger.info(f"Using regular LLM extraction with batch size {batch_size} and retries {max_retries}")
            return process_email_messages_with_llm(message_data_list, batch_size=batch_size, max_retries=max_retries)
        except Exception as e:
            logger.error(f"Regular LLM processing failed, falling back to regex: {e}")
    
    # Fall back to regex processing
    logger.info("Using regex extraction for processing emails")
    transactions = []
    
    # Process all emails in one batch
    for message_data in message_data_list:
        try:
            transaction = extract_transaction_details(message_data['body'], message_data['id'])
            transaction['transaction_date'] = datetime.fromtimestamp(
                message_data['timestamp']
            ).strftime("%Y-%m-%d %H:%M:%S")
            transactions.append(transaction)
        except Exception as e:
            logger.error(f"Failed to process message {message_data['id']}: {e}")
            continue
    
    return transactions

# Add a function to get debug info about the current extraction configuration
def get_extraction_config_info():
    """Get information about the current extraction configuration for debugging"""
    config_info = {
        "USE_PARALLEL_LLM_EXTRACTION": USE_PARALLEL_LLM_EXTRACTION,
        "USE_LLM_EXTRACTION": USE_LLM_EXTRACTION,
        "parallel_available": False,
        "regular_available": False,
        "active_method": "regex",
        "retry_settings": {
            "max_retries": 3,  # Default values
            "field_retries": 2
        }
    }
    
    # Check parallel availability
    try:
        from parallel_llm_extraction import test_ollama_connection
        config_info["parallel_available"] = test_ollama_connection()
    except ImportError:
        config_info["parallel_availability_error"] = "Module not found"
    except Exception as e:
        config_info["parallel_availability_error"] = str(e)
    
    # Check regular availability
    try:
        from extractor_llm import test_ollama_connection
        config_info["regular_available"] = test_ollama_connection()
    except ImportError:
        config_info["regular_availability_error"] = "Module not found"
    except Exception as e:
        config_info["regular_availability_error"] = str(e)
    
    # Determine which method would be used
    if USE_PARALLEL_LLM_EXTRACTION and config_info["parallel_available"]:
        config_info["active_method"] = "parallel_llm"
    elif USE_LLM_EXTRACTION and config_info["regular_available"]:
        config_info["active_method"] = "regular_llm"
    else:
        config_info["active_method"] = "regex"
    
    return config_info 