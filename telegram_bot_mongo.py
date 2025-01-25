from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes
from datetime import datetime
import google.generativeai as genai
import json
import os
import dotenv
import io
import logging
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


#Import LLM helper functions
from generate_response import generate_response
from get_intent import get_intent
from summarise_data import summarise_balance_data
from get_transaction_data import get_transaction_data


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
            gemini_output = get_transaction_data(user_input)
            amount = gemini_output.get("amount")
            account = gemini_output.get("account", "Other")
            transaction_type = gemini_output.get("transaction_type", "Expense")
            date = gemini_output.get("date", None)

            if amount is None:
                if "balance" in user_input.lower():
                    await get_balance(update, context)
                    return
                elif "statement" in user_input.lower():
                    await get_statement(update, context)
                    return
                else:
                    message = "I couldn't extract the amount from your input. Please try again."
                    message = await generate_response(message)
                    await update.message.reply_text(message)
                    return

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