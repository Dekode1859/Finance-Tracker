import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Mapping
import ollama
import logging
from agno.agent import Agent, RunResponse
from agno.models.ollama import Ollama
# from agno.models.openai import OpenAIChat
from pydantic import BaseModel, Field, constr, confloat
# from rich.pretty import pprint

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

class TransactionDetails(BaseModel):
    """Model for individual transaction details"""
    transaction_amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount as a positive number, excluding currency symbols and commas"
    )
    transaction_type: str = Field(
        ...,
        pattern="^(Credit|Debit)$",
        description="Must be exactly 'Credit' or 'Debit'"
    )
    available_balance: float = Field(
        ...,
        description="Available balance after transaction, excluding currency symbols and commas"
    )

class BatchTransactionResponse(BaseModel):
    """Model for batch processing response"""
    transactions: Dict[str, TransactionDetails] = Field(
        ...,
        description="Dictionary mapping message IDs to their extracted transaction details"
    )

# Create an Agno agent for batch transaction extraction
transaction_agent = Agent(
    model=Ollama(id="deepseek-r1:8b"),
    name="BatchTransactionExtractor",
    description="You are a specialized agent for extracting transaction details from bank email notifications.",
    instructions=[
        "Extract only the transaction amount, transaction type, and available balance from bank notifications.",
        "Handle multiple email formats from different banks.",
        "Convert all amounts to numbers by removing currency symbols and commas.",
        "Do not make assumptions or guess missing information.",
        "If critical fields are missing, exclude that transaction."
    ],
    response_model=BatchTransactionResponse
)

def test_ollama_connection() -> bool:
    """Test if Ollama is available and responding"""
    try:
        ollama.chat(model="deepseek-r1:8b", messages=[{"role": "user", "content": "test"}])
        return True
    except Exception as e:
        logger.error(f"Ollama test failed: {e}")
        return False

def process_email_messages_with_llm(message_data_list: List[Dict[str, Any]], batch_size: int = 20, max_retries: int = 3) -> List[Dict[str, Any]]:
    """Process multiple email messages in batches using the Agno agent with retry logic for failed validations
    
    Args:
        message_data_list: List of dictionaries containing email message data
        batch_size: Number of emails to process in each batch (default: 20)
        max_retries: Maximum number of retry attempts for failed validations (default: 3)
    
    Returns:
        List of successfully processed transactions
    """
    transactions = []
    all_messages = message_data_list.copy()
    total_messages = len(all_messages)
    
    logger.info(f"Processing {total_messages} emails in batches of {batch_size}")
    
    # Process emails in batches
    for batch_start in range(0, total_messages, batch_size):
        batch_end = min(batch_start + batch_size, total_messages)
        current_batch = all_messages[batch_start:batch_end]
        
        logger.info(f"Processing batch {batch_start//batch_size + 1}: emails {batch_start+1} to {batch_end} of {total_messages}")
        
        # Process the current batch with retry logic
        remaining_messages = current_batch.copy()
        retry_count = 0

        while remaining_messages and retry_count < max_retries:
            try:
                # Prepare the input for batch processing
                batch_input = {}
                for message in remaining_messages:
                    batch_input[message['id']] = message['body']
                
                # Process current batch
                logger.info(f"Sending {len(batch_input)} messages to LLM")
                response: RunResponse = transaction_agent.run(json.dumps(batch_input))
                batch_results = response.content.transactions
                
                # Track which messages need to be retried
                failed_messages = []
                
                # Process results
                for message in remaining_messages:
                    message_id = message['id']
                    try:
                        if message_id not in batch_results:
                            logger.warning(f"No results found for message {message_id}, will retry")
                            failed_messages.append(message)
                            continue

                        details = batch_results[message_id]
                        
                        # Create transaction dictionary with validated details
                        transaction = {
                            "transaction_id": message_id,
                            "transaction_date": datetime.fromtimestamp(
                                message['timestamp']
                            ).strftime("%Y-%m-%d %H:%M:%S"),
                            "email_body": message['body'],
                            "transaction_amount": details.transaction_amount,
                            "transaction_type": details.transaction_type,
                            "available_balance": details.available_balance,
                            # Set empty values for fields we're no longer extracting
                            "transaction_description": "",
                            "account_number": ""
                        }
                        
                        transactions.append(transaction)
                        logger.info(f"Successfully processed message {message_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to process result for message {message_id}: {e}")
                        failed_messages.append(message)
                
                # Update remaining messages for next iteration
                remaining_messages = failed_messages
                
                if remaining_messages:
                    retry_count += 1
                    logger.info(f"Batch {batch_start//batch_size + 1} - Retry {retry_count}/{max_retries}: {len(remaining_messages)} messages remaining")
                
            except Exception as e:
                logger.error(f"Batch processing failed on retry {retry_count}: {e}")
                retry_count += 1
                
        if remaining_messages:
            logger.warning(
                f"Batch {batch_start//batch_size + 1}: Could not process {len(remaining_messages)} messages after {max_retries} retries. "
                f"Message IDs: {[m['id'] for m in remaining_messages]}"
            )
    
    logger.info(f"Completed processing. Successfully processed {len(transactions)} out of {total_messages} emails")
    return transactions

# Add a function to inspect a single message result for debugging
def inspect_single_message(message_data: Dict[str, Any], debug: bool = True) -> Dict[str, Any]:
    """Process a single message and return detailed information about the extraction process and result.
    
    This is useful for debugging extraction issues with specific messages.
    
    Args:
        message_data: Dictionary containing email message data (id, body, timestamp)
        debug: Enable detailed debug logging (default: True)
        
    Returns:
        Dictionary with detailed information about the extraction process and result
    """
    # Set logging level based on debug parameter
    original_log_level = logger.level
    if debug:
        set_debug_mode(True)
    
    try:
        logger.info(f"Inspecting single message: {message_data['id']}")
        
        try:
            # Prepare input
            batch_input = {message_data['id']: message_data['body']}
            
            # Process message
            response: RunResponse = transaction_agent.run(json.dumps(batch_input))
            
            # Collect inspection data
            inspection_result = {
                "message_id": message_data['id'],
                "message_timestamp": datetime.fromtimestamp(message_data['timestamp']).strftime("%Y-%m-%d %H:%M:%S"),
                "message_body_preview": message_data['body'][:200] + "..." if len(message_data['body']) > 200 else message_data['body'],
                "raw_response": response.raw,
                "response_content": response.content.dict(),
                "success": message_data['id'] in response.content.transactions,
            }
            
            if inspection_result["success"]:
                inspection_result["extracted_details"] = response.content.transactions[message_data['id']].dict()
            else:
                inspection_result["extracted_details"] = None
                inspection_result["error"] = "Message ID not found in response"
                
            return inspection_result
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            
            return {
                "message_id": message_data['id'],
                "message_body_preview": message_data['body'][:200] + "..." if len(message_data['body']) > 200 else message_data['body'],
                "success": False,
                "error": str(e),
                "error_details": error_details
            }
    
    finally:
        # Restore the original logging level
        logger.setLevel(original_log_level)
