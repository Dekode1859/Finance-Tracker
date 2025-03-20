import json
import re
import concurrent.futures
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Mapping
import ollama
import logging
from agno.agent import Agent, RunResponse
from agno.models.ollama import Ollama
from pydantic import BaseModel, Field

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Function to set logging level based on debug mode
def set_debug_mode(debug: bool = False):
    """Set the logging level based on debug mode
    
    Args:
        debug: If True, set logging level to DEBUG, otherwise INFO
    """
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled - verbose logging activated")
    else:
        logger.setLevel(logging.INFO)

# Model for transaction amount extraction
class AmountResponse(BaseModel):
    """Model for transaction amount response"""
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount as a positive number, excluding currency symbols and commas"
    )

# Model for transaction type extraction
class TypeResponse(BaseModel):
    """Model for transaction type response"""
    transaction_type: str = Field(
        ...,
        pattern="^(Credit|Debit)$",
        description="Must be exactly 'Credit' or 'Debit'"
    )

# Model for available balance extraction
class BalanceResponse(BaseModel):
    """Model for available balance response"""
    available_balance: float = Field(
        ...,
        description="Available balance after transaction, excluding currency symbols and commas"
    )

# Create specialized agents for each extraction task
amount_agent = Agent(
    model=Ollama(id="qwen:0.5b"),
    name="AmountExtractor",
    description="You are a specialized agent for extracting transaction amounts from bank email notifications.",
    instructions=[
        "Extract ONLY the transaction amount from the bank notification.",
        "Convert amounts to numbers by removing currency symbols and commas.",
        "Return only a positive number (the amount) regardless of credit or debit.",
        "Look for phrases like 'debited for', 'credited for', 'transaction of', 'amount:' etc.",
        "If multiple amounts are present, extract the main transaction amount (not the balance).",
        "If no amount can be determined, raise an exception."
    ],
    response_model=AmountResponse
)

type_agent = Agent(
    model=Ollama(id="qwen:0.5b"),
    name="TypeExtractor",
    description="You are a specialized agent for identifying transaction types from bank email notifications.",
    instructions=[
        "Determine ONLY if this is a Credit or Debit transaction.",
        "Look for words like 'credited', 'debited', 'received', 'sent', 'payment', 'withdrawal', etc.",
        "Credit = money added to account (deposit, received payment, refund).",
        "Debit = money removed from account (withdrawal, payment sent, purchase).",
        "Return exactly 'Credit' or 'Debit' (case sensitive).",
        "If the type cannot be determined with confidence, raise an exception."
    ],
    response_model=TypeResponse
)

balance_agent = Agent(
    model=Ollama(id="qwen:0.5b"),
    name="BalanceExtractor",
    description="You are a specialized agent for extracting available balance from bank email notifications.",
    instructions=[
        "Extract ONLY the available balance amount from the bank notification.",
        "Look for phrases like 'available balance', 'current balance', 'balance is', etc.",
        "Convert balance to a number by removing currency symbols and commas.",
        "Return only the balance amount as a number.",
        "If no balance information is present, return -1 to indicate missing balance."
    ],
    response_model=BalanceResponse
)

def test_ollama_connection() -> bool:
    """Test if Ollama is available and responding"""
    try:
        ollama.chat(model="qwen:0.5b", messages=[{"role": "user", "content": "test"}])
        return True
    except Exception as e:
        logger.error(f"Ollama test failed: {e}")
        return False

def extract_transaction_amount(message_body: str, max_retries: int = 2) -> float:
    """Extract transaction amount using specialized agent with retries"""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.debug(f"Retry {attempt}/{max_retries} for amount extraction")
            response: RunResponse = amount_agent.run(message_body)
            return response.content.amount
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                # Add a small delay between retries
                import time
                time.sleep(0.5)
    
    # If we get here, all attempts failed
    logger.error(f"Failed to extract amount after {max_retries + 1} attempts: {last_error}")
    raise last_error

def extract_transaction_type(message_body: str, max_retries: int = 2) -> str:
    """Extract transaction type using specialized agent with retries"""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.debug(f"Retry {attempt}/{max_retries} for type extraction")
            response: RunResponse = type_agent.run(message_body)
            return response.content.transaction_type
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                # Add a small delay between retries
                import time
                time.sleep(0.5)
    
    # If we get here, all attempts failed
    logger.error(f"Failed to extract transaction type after {max_retries + 1} attempts: {last_error}")
    raise last_error

def extract_available_balance(message_body: str, max_retries: int = 2) -> float:
    """Extract available balance using specialized agent with retries"""
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.debug(f"Retry {attempt}/{max_retries} for balance extraction")
            response: RunResponse = balance_agent.run(message_body)
            return response.content.available_balance
        except Exception as e:
            if attempt < max_retries:
                # Add a small delay between retries
                import time
                time.sleep(0.5)
            else:
                logger.debug(f"Failed to extract balance after {max_retries + 1} attempts: {e}")
                return -1  # Indicate no balance found after all retries

def process_single_message(message_data: Dict[str, Any], field_retries: int = 2) -> Dict[str, Any]:
    """Process a single message using parallel extraction with specialized agents
    
    Args:
        message_data: Dictionary containing email message data
        field_retries: Number of retries for individual field extractions
    """
    message_id = message_data['id']
    message_body = message_data['body']
    
    logger.info(f"Processing message {message_id}")
    
    # Use ThreadPoolExecutor to run extractions in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all extraction tasks concurrently with retry capability
        amount_future = executor.submit(extract_transaction_amount, message_body, field_retries)
        type_future = executor.submit(extract_transaction_type, message_body, field_retries)
        balance_future = executor.submit(extract_available_balance, message_body, field_retries)
        
        # Initialize with default values
        transaction_amount = 0.0
        transaction_type = "Unknown"
        available_balance = 0.0
        success = False
        
        # Get amount (required)
        try:
            transaction_amount = amount_future.result()
            # Only proceed if we got a valid amount
            try:
                transaction_type = type_future.result()
                
                # Try to get balance (optional)
                try:
                    balance_result = balance_future.result()
                    if balance_result > 0:  # Valid balance found
                        available_balance = balance_result
                except Exception:
                    # Balance extraction failed, but that's okay
                    pass
                
                # If we got here, we have at least amount and type
                success = True
                
            except Exception as e:
                logger.error(f"Type extraction failed for message {message_id}: {e}")
        except Exception as e:
            logger.error(f"Amount extraction failed for message {message_id}: {e}")
    
    if success:
        # Create transaction dictionary with extracted details
        return {
            "transaction_id": message_id,
            "transaction_date": datetime.fromtimestamp(
                message_data['timestamp']
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "email_body": message_body,
            "transaction_amount": transaction_amount,
            "transaction_type": transaction_type,
            "available_balance": available_balance,
            "transaction_description": "",
            "account_number": ""
        }
    else:
        return None

def process_email_messages_with_parallel_llm(message_data_list: List[Dict[str, Any]], batch_size: int = 10, max_workers: int = 4, max_retries: int = 3, field_retries: int = 2) -> List[Dict[str, Any]]:
    """Process multiple email messages in parallel using specialized agents
    
    Args:
        message_data_list: List of dictionaries containing email message data
        batch_size: Number of emails to process in each batch (default: 10)
        max_workers: Maximum number of worker threads (default: 4)
        max_retries: Maximum number of retry attempts for failed messages (default: 3)
        field_retries: Number of retries for individual field extractions (default: 2)
    
    Returns:
        List of successfully processed transactions
    """
    transactions = []
    all_messages = message_data_list.copy()
    total_messages = len(all_messages)
    
    logger.info(f"Processing {total_messages} emails with parallel extraction (batch size: {batch_size}, workers: {max_workers}, message retries: {max_retries}, field retries: {field_retries})")
    
    # Process emails in batches
    for batch_start in range(0, total_messages, batch_size):
        batch_end = min(batch_start + batch_size, total_messages)
        initial_batch = all_messages[batch_start:batch_end]
        
        logger.info(f"Processing batch {batch_start//batch_size + 1}: emails {batch_start+1} to {batch_end} of {total_messages}")
        
        # Keep track of remaining messages for retry logic
        remaining_messages = initial_batch.copy()
        retry_count = 0
        
        # Process batch with retries
        while remaining_messages and retry_count < max_retries:
            current_batch_size = len(remaining_messages)
            
            if retry_count > 0:
                logger.info(f"Retry {retry_count}/{max_retries} for {current_batch_size} messages")
            
            # Track failed messages for next retry
            failed_messages = []
            
            # Process each message in the batch in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all message processing tasks
                future_to_message = {
                    executor.submit(process_single_message, message, field_retries): message 
                    for message in remaining_messages
                }
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_message):
                    message = future_to_message[future]
                    try:
                        result = future.result()
                        if result:
                            transactions.append(result)
                            logger.info(f"Successfully processed message {message['id']}")
                        else:
                            # Add to failed messages for retry
                            logger.warning(f"Failed to extract transaction details from message {message['id']}, will retry")
                            failed_messages.append(message)
                    except Exception as e:
                        logger.error(f"Error processing message {message['id']}: {e}")
                        # Add to failed messages for retry
                        failed_messages.append(message)
            
            # Update remaining messages for next retry
            remaining_messages = failed_messages
            
            # Increment retry count if there are messages to retry
            if remaining_messages:
                retry_count += 1
            
        # Log messages that failed after all retries
        if remaining_messages:
            logger.warning(
                f"Batch {batch_start//batch_size + 1}: Could not process {len(remaining_messages)} messages after {max_retries} retries. "
                f"Message IDs: {[m['id'] for m in remaining_messages]}"
            )
    
    logger.info(f"Completed processing. Successfully processed {len(transactions)} out of {total_messages} emails")
    return transactions 