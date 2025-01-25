import google.generativeai as genai
import os
import logging
import json

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


async def get_transaction_data(user_input: str) -> str:
    
    """
    Extracts transaction data from the user's input using the Gemini API.
    
    Args:
        user_input: The user's input text containing transaction details.
    
    Returns:
        A JSON object containing the extracted transaction data.
    """
    
    prompt = f"""
    Extract the following information from the given text:
    1. Amount (numerical value)
    2. Account (one of: Home, Clothes, Trips, Labor, EMIs, Salary, Freelance, Other)
    3. Transaction Type (Income or Expense)
    4. Date: If not provided, return null
    Text: {user_input}

    Return the output as a JSON object with keys "amount", "account", "transaction_type" and date. If you cannot determine a value, set it to null.

    Example:
    Text: Spent 500 on groceries
    Output: {{"amount": 500, "account": "Home", "transaction_type": "Expense", "date": None}}
    
    Text: Received 1000 from freelance work on 2025/01/01
    Output: {{"amount": 1000, "account": "Freelance", "transaction_type": "Income", "date": "2025-01-01"}}
    
    Text: Spent 200 on clothes on 20th January 2025
    Output: {{"amount": 200, "account": "Clothes", "transaction_type": "Expense", "date": "2025-01-20"}}
    
    Text: Received 500 from salary
    Output: {{"amount": 500, "account": "Salary", "transaction_type": "Income", "date": None}}
    """

    response = model.generate_content(prompt)
    gemini_output = response.text.strip()
    cleaned_output = gemini_output.strip("```json").strip()
    logging.info("Gemini Output: %s", cleaned_output)
    gemini_output = json.loads(cleaned_output)