from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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


uri = "mongodb+srv://musaib:<db_password>@musaibs.i59nbcc.mongodb.net/?retryWrites=true&w=majority&appName=musaibs"

client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
    


logging.basicConfig(level=logging.INFO)


dotenv.load_dotenv()

# --- Setup Environment Variables ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "1526121885"))  # Replace with your Telegram user ID

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- Google Sheets Setup ---
CREDENTIALS_FILE = 'sheets_key.json'
if not os.path.exists(CREDENTIALS_FILE):
    raise FileNotFoundError("Credential file not found. Please provide a valid JSON keyfile.")

SCOPE = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive',
         'https://www.googleapis.com/auth/spreadsheets']
CREDS = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
CLIENT = gspread.authorize(CREDS)
SHEET = CLIENT.open('Expense Sheet').sheet1

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler."""
    print(f"User {update.effective_user.id} started the bot.")
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized access!")
        return
    await update.message.reply_text("Hey, Musaib! How are you doing today? I'm here to help you track your expenses and income. Send me a message with the details of your transaction (e.g., 'Spent 500 on groceries').")
    

async def get_balance(update: Update, context):
    """Calculate and display the current balance."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized access!")
        return

    # Fetch all data from Google Sheets
    try:
        all_data = SHEET.get_all_values()
        df = pd.DataFrame(all_data[1:], columns=all_data[0])  # Convert to DataFrame
        df['Income'] = pd.to_numeric(df['Income'], errors='coerce').fillna(0)
        df['Expenditure'] = pd.to_numeric(df['Expenditure'], errors='coerce').fillna(0)

        # Calculate balance
        balance = df['Income'].sum() - df['Expenditure'].sum()
        await update.message.reply_text(f"**Current Available Balance: {balance}**")
    except Exception as e:
        logging.error(f"Error calculating balance: {e}")
        await update.message.reply_text("Failed to fetch the balance. Please try again later.")

async def get_statement(update: Update, context):
    """Generate and send the current month's statement as a PDF."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized access!")
        return

    try:
        # Fetch all data from Google Sheets
        all_data = SHEET.get_all_values()
        df = pd.DataFrame(all_data[1:], columns=all_data[0])

        # Filter for the current month
        current_month = datetime.now().strftime('%Y-%m')
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        current_month_data = df[df['Date'].dt.strftime('%Y-%m') == current_month]

        # Check if there is data for the current month
        if not current_month_data.empty:
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
            for index, row in current_month_data.iterrows():
                c.drawString(50, y, str(row['Date'].date()))
                c.drawString(150, y, str(row['Account']))
                c.drawString(250, y, str(row['Income']))
                c.drawString(350, y, str(row['Expenditure']))
                c.drawString(450, y, str(row['Remarks']))
                y -= 20

            # Save PDF to buffer
            c.save()

            # Rewind the buffer to the beginning
            buffer.seek(0)

            # Send the PDF as a document
            await update.message.reply_document(
                document=buffer,
                filename="statement.pdf",
                caption="Here is your current month's statement."
            )
        else:
            await update.message.reply_text("No transactions found for the current month.")
    except Exception as e:
        logging.error(f"Error generating statement: {e}")
        await update.message.reply_text("Failed to generate the statement. Please try again later.")

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle messages from the user."""
    if update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("Unauthorized access!")
        return

    user_input = update.message.text
    try:
        # --- Gemini NLP ---
        prompt = f"""
        Extract the following information from the given text:
        1. Amount (numerical value)
        2. Account (one of: Home, Clothes, Trips, Labor, EMIs, Salary, Freelance, Other)
        3. Transaction Type (Income or Expense)

        Text: {user_input}

        Return the output as a JSON object with keys "amount", "account", and "transaction_type". If you cannot determine a value, set it to null.

        Example:
        Text: Spent 500 on groceries
        Output: {{"amount": 500, "account": "Home", "transaction_type": "Expense"}}
        """

        response = model.generate_content(prompt)
        gemini_output = response.text.strip()
        cleaned_output = gemini_output.strip("```json").strip()
        logging.info("Gemini Output:", cleaned_output)
        gemini_output = json.loads(cleaned_output)
        amount = gemini_output.get("amount")
        account = gemini_output.get("account", "Other")
        transaction_type = gemini_output.get("transaction_type", "Expense")

        if amount is None:
            # check if the user is asking for the balance or statement
            if "balance" in user_input.lower():
                await get_balance(update, context)
                return
            elif "statement" in user_input.lower():
                await get_statement(update, context)
                return
            raise ValueError("Could not extract amount from the input.")

        # --- Add to Google Sheets ---
        date_str = datetime.now().strftime('%Y-%m-%d')
        income = float(amount) if transaction_type == "Income" else 0
        expenditure = float(amount) if transaction_type == "Expense" else 0
        remarks = user_input

        row = [date_str, account, income, expenditure, remarks]
        SHEET.append_row(row)
        await update.message.reply_text("Entry added successfully!")

        # --- Calculate Available Balance ---
        all_data = SHEET.get_all_values()
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        df['Income'] = pd.to_numeric(df['Income'], errors='coerce').fillna(0)
        df['Expenditure'] = pd.to_numeric(df['Expenditure'], errors='coerce').fillna(0)
        balance = df['Income'].sum() - df['Expenditure'].sum()
        await update.message.reply_text(f"**Current Available Balance: {balance}**")

    except json.JSONDecodeError:
        await update.message.reply_text("Gemini returned invalid JSON. Please rephrase your input.")
    except ValueError as ve:
        await update.message.reply_text(f"Error: {ve}")
    except Exception as e:
        await update.message.reply_text(f"An unexpected error occurred: {e}")

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


if __name__ == "__main__":
    main()