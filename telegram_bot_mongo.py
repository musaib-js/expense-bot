from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes
from datetime import datetime
import google.generativeai as genai
import pandas as pd
import json
import os
import dotenv
import io
import logging
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
# from flask import Flask, request, jsonify


dotenv.load_dotenv()
# app = Flask(__name__)

# MongoDB setup
uri = os.getenv("MONGO_URI")
print("here", uri)
client = MongoClient(uri, server_api=ServerApi('1'))

db = client['FinancesDB']
finances_collection = db['finances']

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

logging.basicConfig(level=logging.INFO)


# --- Setup Environment Variables ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "1234567890"))  # Replace with your Telegram user ID

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


# ---------- Helper Functions ----------

async def generate_response(system_response: str) -> str:
    # Generate a human response using the Gemini API. The response should be in the same language as the input. Write a function that takes the system response as input and returns the human response. Generate a prompt that asks the model to generate a human response to the system response.
    prompt = f"""
    You are a very friendly agent who is responding to a user's query. You are tasked with generating a human-like response to the system response. The response has to be in the same language as the input. It should be polite, informative, and helpful. Return only the response text. If the model fails to generate a response, return a default response. If the balance is less than 20000, encourage the user to save more. If the balance is greater than 20000, congratulate the user on saving. If the balance is 0, ask the user to track their expenses. If the balance is negative, ask the user to be careful with their expenses. Don't mention any currency symbols in the response. The system response will be provided as a string. Return only the response text.
    
    System Response: {system_response}
    
    Example:
    System Response: "I'm sorry, I cannot provide that information."
    Human Response: "I apologize for the inconvenience. Looks like something is wrong. Is there anything else I can help you with?"
    
    System Response: "Current Available Balance: 167800"
    Human Response: "You have a balance of $167,800. That's great! Keep up the good work. Good job on saving!"
    
    """
    response = model.generate_content(prompt)
    return response.text.strip()

async def summarise_balance_data(text: str, json_data: dict) -> str:
    """Analyzes JSON data using Gemini LLM based on a user's natural language query.

    Args:
        json_data: A JSON string or a Python dictionary representing the data.
        user_query: The user's query in natural language.

    Returns:
        A string containing the response to the user's query, or an error message.
    """
    
    try:
        if isinstance(json_data, str):
            data = json.loads(json_data)
        elif isinstance(json_data, dict):
            data = json_data
        else:
            return "Error: Invalid JSON data provided."
        
        prompt =prompt = f"""
        You are a friendly AI assistant for a finances tracking application. You are tasked with analyzing the user's finance data and providing a response based on the user's query. The user may ask for balance, spend history, or anything related to finance. You need to analyze the data and provide a response. The data will be provided in JSON format. You need to extract the relevant information and provide a response. If the user asks for the balance, you need to calculate the balance and provide a response. If the user asks for the spend history, you need to provide the spend history. If the user asks for any other information, you need to provide a relevant response. Return the response as a string. If the money is less than 20000, encourage the user to save more. If the money is greater than 20000, congratulate the user on saving. If the money is 0, ask the user to track their expenses. If the money is negative, ask the user to be careful with their expenses. If the user is just greeting, respond with a polite greeting saying you are the expense tracking bot. You need to handle the case where the data is empty or the user query is not valid. The user query will be provided as a string. Return only the response text.

        Instructions:
        1. Please note that the data may contain multiple records for the same user. You need to consider all the records while calculating the balance or spend history.
        2. The user query will be provided as a string.
        3. You need to return the response as a string.
        4. Don't forget to handle the case where the data is empty or the user query is not valid.
        5. You can assume that the data will always contain the keys: "date", "account", "income", "expenditure", "remarks", "user_id".
        6. You can assume that the user query will always be a string.
        7. The user query can be in any language. You need to handle that and provide the response in the same language. The amount numbers will always be in English.
        8. The number of records in the data can vary.
        9. The data will be provided as a JSON object.
        10. Return only the response text.
        11. Don't give any irrelevant information in the response.
        12. If the query is in Hinglish, respond in Hinglish.
        13. Don't mention any currency symbols in the response.

        Here is the JSON data:
        {data}
        and the user query is:
        {text}

        Example:
        
        Data: []
        User Query: "Hello"
        Output: "Hello! I am your expense tracking bot. How can I help you today?"
        
        Data: []
        User Query: "What is my current balance?"
        Output: "Your current balance is 0. Track your expenses regularly. It seems you haven't added any transactions yet."
        
        Data: []
        User Query: "How are you doing?"
        Output: "I am doing well. Thank you for asking. How can I help you today?"
        
        Data: []
        User Query: "Who created you?"
        Output: "I was created by Musaib Altaf. You can visit him on https://www.linkedin.com/in/musaibaltaf.  How can I assist you today?"
        
        Data: [],
        User Query: "Bhai tujhe kisne banaya?"
        Output: "Bhai, mujhe Musaib Altaf ne banaya hai. Aap unki profile https://www.linkedin.com/in/musaibaltaf pe dekh sakte hn. Mai aapki kya madad kar sakta hoon?"

        Data: [
            {{'date': '2024-01-25', 'account': 'Salary', 'income': 167800, 'expenditure': 0, 'remarks': 'Salary aagayi bro 167800', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 5000, 'remarks': 'Groceries', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 2000, 'remarks': 'Electricity bill', 'user_id': 1526121885}}
            ]
        User Query: 'What is my current balance?'
        Output: 'Your current balance is 160,800. Great job on saving!'

        Data: [
            {{'date': '2024-01-25', 'account': 'Salary', 'income': 167800, 'expenditure': 0, 'remarks': 'Salary aagayi bro 167800', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 5000, 'remarks': 'Groceries', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 2000, 'remarks': 'Electricity bill', 'user_id': 1526121885}}
            ]
        User Query: 'Where did I spend the most?'
        Output: 'You spent the most on groceries. Be careful with your expenses. Track your expenses regularly.'

        Data: [
            {{'date': '2024-01-25', 'account': 'Salary', 'income': 167800, 'expenditure': 0, 'remarks': 'Salary aagayi bro 167800', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 5000, 'remarks': 'Groceries', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 2000, 'remarks': 'Electricity bill', 'user_id': 1526121885}}
            ]
        User Query: 'How much did I spend on 25 January 2024?'
        Output: 'You spent a total of 7,000 on 25 January 2024. Be careful with your expenses. Track your expenses regularly.'

        Data: [
            {{'date': '2025-01-25', 'account': 'Salary', 'income': 167800, 'expenditure': 0, 'remarks': 'Salary aagayi bro 167800', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 5000, 'remarks': 'Groceries', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 2000, 'remarks': 'Electricity bill', 'user_id': 1526121885}}
            ]
        User Query: 'Give me the statement for Feb 2025.'
        Output: 'No transactions found for February 2025. Looks like you’ve added transactions for January 2025. Would you like to see the statement for January 2025?'

        Data: [
            {{'date': '2025-01-25', 'account': 'Salary', 'income': 167800, 'expenditure': 0, 'remarks': 'Salary aagayi bro 167800', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 5000, 'remarks': 'Groceries', 'user_id': 1526121885}}, 
            {{'date': '2024-01-25', 'account': 'Home', 'income': 0, 'expenditure': 2000, 'remarks': 'Electricity bill', 'user_id': 1526121885}}
            ]
        User Query: 'Give me the statement for Jan 2025.'
        Output: 'Here is your statement for January 2025. You received 167800 from salary. No more transactions found for January 2025.'
        """
        
        response = model.generate_content(prompt)
        message = response.text.strip()
        return message
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        message = f"An error occurred: {e}"
        message = await generate_response(message)
        return message
    
    
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


# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler."""
    print(f"User {update.effective_user} started the bot.")
    if update.effective_user.id != AUTHORIZED_USER_ID:
        message = "Unauthorized access!"
        message = await generate_response(message)
        await update.message.reply_text(message)
        return
    message = f"Hey, {update.effective_user.first_name}! How are you doing today? I'm here to help you track your expenses and income. Send me a message with the details of your transaction (e.g., 'Spent 500 on groceries')."
    message = await generate_response(message)
    await update.message.reply_text(message)

async def get_balance(update: Update, context):
    """Calculate and display the current balance."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized access!")
        return

    try:
        pipeline = [
            {
                "$match": {
                    "user_id": update.effective_user.id
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_income": {"$sum": {"$ifNull": ["$income", 0]}},
                    "total_expenditure": {"$sum": {"$ifNull": ["$expenditure", 0]}}
                }
            }
        ]
        result = list(finances_collection.aggregate(pipeline))
        if result:
            total_income = result[0]['total_income']
            total_expenditure = result[0]['total_expenditure']
            balance = total_income - total_expenditure
        else:
            balance = 0
        
        message = f"Current Available Balance: {balance}"
        message = await generate_response(message)
        await update.message.reply_text(message)
    except Exception as e:
        logging.error(f"Error calculating balance: {e}")
        message = "Failed to fetch the balance. Please try again later."
        message = await generate_response(message)
        await update.message.reply_text(message)

async def get_statement(update: Update, context):
    """Generate and send the current month's statement as a PDF."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        message = "Unauthorized access!"
        message = await generate_response(message)
        await update.message.reply_text(message)
        return

    try:
        # Filter for the current month's transactions in MongoDB
        current_month = datetime.now().strftime('%Y-%m')
        transactions = list(finances_collection.find({
            "date": {"$regex": f"^{current_month}"},
            "user_id": update.effective_user.id
        }))

        if transactions:
            # Create a PDF buffer
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)

            # Set title
            c.setFont("Helvetica-Bold", 16)
            c.drawString(200, 750, "Current Month Statement")

            # Add a space
            c.setFont("Helvetica", 12)
            c.drawString(50, 720, f"Date: {datetime.now().strftime('%Y-%m-%d')}")

            # Draw table header
            y = 700
            c.drawString(50, y, "Date")
            c.drawString(150, y, "Account")
            c.drawString(250, y, "Income")
            c.drawString(350, y, "Expenditure")
            c.drawString(450, y, "Remarks")

            # Draw table content
            y -= 20
            for transaction in transactions:
                c.drawString(50, y, transaction['date'])
                c.drawString(150, y, transaction['account'])
                c.drawString(250, y, str(transaction['income']))
                c.drawString(350, y, str(transaction['expenditure']))
                c.drawString(450, y, transaction['remarks'])
                y -= 20

            # Save PDF to buffer
            c.save()

            # Rewind the buffer to the beginning
            buffer.seek(0)
            
            caption = "Here is your current month's statement."
            message = await generate_response(caption)

            # Send the PDF as a document
            await update.message.reply_document(
                document=buffer,
                filename="statement.pdf",
                caption=message
            )
        else:
            message = "No transactions found for the current month."
            message = await generate_response(message)
            await update.message.reply_text(message)
    except Exception as e:
        logging.error(f"Error generating statement: {e}")
        message = "Failed to generate the statement. Please try again later."
        message = await generate_response(message)
        await update.message.reply_text(message)
        
async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle messages from the user."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized access!")
        return

    user_input = update.message.text
    try:
        # --- Extract Intent ---
        intent = await get_intent(user_input)
        logging.info("User Intent: %s", intent)
        
        if intent == "add_transaction":
            # --- Gemini NLP ---
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
            
            amount = gemini_output.get("amount")
            account = gemini_output.get("account", "Other")
            transaction_type = gemini_output.get("transaction_type", "Expense")
            date = gemini_output.get("date", None)

            if amount is None:
                # check if the user is asking for the balance or statement
                if "balance" in user_input.lower():
                    await get_balance(update, context)
                    return
                elif "statement" in user_input.lower():
                    await get_statement(update, context)
                    return

            # --- Add to MongoDB ---
            date = datetime.strptime(date, '%Y-%m-%d') if date else datetime.now()
            date_str = date.strftime('%Y-%m-%d')
            income = float(amount) if transaction_type == "Income" else 0
            expenditure = float(amount) if transaction_type == "Expense" else 0
            remarks = user_input

            finance_data = {
                "date": date_str,
                "account": account,
                "income": income,
                "expenditure": expenditure,
                "remarks": remarks,
                "user_id": update.effective_user.id
            }

            db = client.get_database("FinancesDB")  
            finances_collection = db.get_collection("finances") 
            finances_collection.insert_one(finance_data)
            
            message = "Entry added successfully!"
            message = await generate_response(message)
            await update.message.reply_text(message)

            # --- Calculate Available Balance ---
            cursor = finances_collection.find({"user_id": update.effective_user.id})
            records = list(cursor)
            total_income = sum(record.get("income", 0) for record in records)
            total_expenditure = sum(record.get("expenditure", 0) for record in records)
            balance = total_income - total_expenditure
            
            message = f"Current Available Balance: {balance}"
            message = await generate_response(message)
            await update.message.reply_text(message)
            
        elif intent == "get_balance":
            await get_balance(update, context)
        elif intent == "get_statement":
            await get_statement(update, context)
        else:
            logging.info("User Query: %s", user_input)
            # get all the transactions for the user
            db = client.get_database("FinancesDB")  
            finances_collection = db.get_collection("finances") 
            cursor = finances_collection.find({"user_id": update.effective_user.id})
            records = list(cursor)
            for record in records:
                record.pop("_id")
            json_data = json.dumps(records)
            logging.info("Finance Data: %s", json_data)
            message = await summarise_balance_data(user_input, json_data)  
            logging.info("Response: %s", message) 
            await update.message.reply_text(message)
    except json.JSONDecodeError:
        logging.error("Gemini returned invalid JSON. Please rephrase your input.")
        message = "Gemini returned invalid JSON. Please rephrase your input."
        message = await generate_response(message)
        await update.message.reply_text(message)
    except ValueError as ve:
        logging.error(f"Error in handle_message: {ve}")
        message = f"Error: {ve}"
        message = await generate_response(message)
        await update.message.reply_text(message)
    except Exception as e:
        logging.error(f"Error in handle_message: {e}")
        message = f"An unexpected error occurred: {e}"
        message = await generate_response(message)
        await update.message.reply_text(message)


def main():
    # Get Telegram token from environment variables
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        raise ValueError("Please set the TELEGRAM_TOKEN environment variable.")

    # Create Application instance using the builder
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("getstatement", get_statement))
    application.add_handler(CommandHandler("getbalance", get_balance))
    application.add_handler(MessageHandler(filters.ALL, handle_message))

    # Start the bot
    print("Starting the bot...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


# @app.route('/health', methods=['GET'])
# def health():
#     return jsonify({"status": "ok"})

# start = False
# @app.route('/start', methods=['GET'])
# def start_bot():
#     global start
#     if start:
#         return jsonify({"status": "Bot already started"})
#     start = True
#     while start:
#         main()
        
# @app.route('/stop', methods=['GET'])
# def stop_bot():
#     global start
#     start = False
#     return jsonify({"status": "ok"})

if __name__ == "__main__":
    while True:
        main()