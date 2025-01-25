import google.generativeai as genai
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


current_supported_intents = ["add_transaction", "get_balance", "get_statement", "general_inquiry"]
async def get_intent(text: str) -> str:
    """Extract the intent from the user's query using the Gemini API.

    Args:
        text: The user's query in natural language.

    Returns:
        A string containing the intent extracted from the user's query.
    """
    prompt = f"""
    You are a friendly AI assistant for a finance tracking application. You are tasked with extracting the intent from the user's query. The user may ask to add a transaction, get the balance, get the statement, or ask a general inquiry. You need to extract the intent from the user's query. Return the intent as a string. If the intent cannot be determined, return "general_inquiry". You need to handle the case where the user query is not valid. The user query will be provided as a string. Return only the intent as a string.
    
    Instructions:
    1. The user query will be provided as a string.
    2. Return the intent as a string.
    3. The user query can be in any language. You need to handle that and provide the response in the same language.
    4. The intent can be one of the following: "add_transaction", "get_balance", "get_statement", "general_inquiry".
    5. If the intent cannot be determined, return "general_inquiry".
    6. Don't give any irrelevant information in the response.
    7. Return get_statement only if the user asks for the statement for a specific month.
    8. Don't forget to handle the case where the user query is not valid.
    9. Just return the intent as a string.
    
    User Query: {text}
    
    Example:
    
    User Query: "I spent 500 on groceries."
    Intent: "add_transaction"
    
    User Query: "What is my current balance?"
    Intent: "get_balance"
    
    User Query: "Give me the statement for February 2025."
    Intent: "get_statement"
    
    User Query: "How much did I spend on 25 January 2025?"
    Intent: "general_inquiry"
    """
    
    response = model.generate_content(prompt)
    intent = response.text.strip()
    if intent in current_supported_intents:
        return intent
    return "general_inquiry"