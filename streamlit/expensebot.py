import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import google.generativeai as genai
import pandas as pd
import json
import os
import dotenv

dotenv.load_dotenv()

# --- Gemini API Setup ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("Please set the GOOGLE_API_KEY environment variable.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- Google Sheets Setup ---
CREDENTIALS_FILE = 'sheets_key.json'

if not os.path.exists(CREDENTIALS_FILE):
    st.error("Credential file not found. Please provide a valid JSON keyfile.")
    st.stop()

SCOPE = ['https://spreadsheets.google.com/feeds', 
         'https://www.googleapis.com/auth/drive', 
         'https://www.googleapis.com/auth/spreadsheets']
CREDS = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
CLIENT = gspread.authorize(CREDS)
SHEET = CLIENT.open('Expense Sheet').sheet1

# --- Streamlit UI ---
st.title('Expense and Income Tracker Bot (Gemini Powered)')

user_input = st.text_input("Enter your expense/income (e.g., 'Spent 500 on groceries'):")

if st.button('Process'):
    if user_input:
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

            Text: Received 1000 salary
            Output: {{"amount": 1000, "account": "Salary", "transaction_type": "Income"}}

            Text: Petrol 200
            Output: {{"amount": 200, "account": "Other", "transaction_type": "Expense"}}
            """

            response = model.generate_content(prompt)

            gemini_output = response.text.strip()
            cleaned_output = gemini_output.strip("```json").strip()
            print("Gemini Output:", cleaned_output)
            gemini_output = json.loads(cleaned_output)
            amount = gemini_output.get("amount")
            account = gemini_output.get("account", "Other")
            transaction_type = gemini_output.get("transaction_type", "Expense")

            if amount is None:
                raise ValueError("Could not extract amount from the input")

            date_str = datetime.now().strftime('%Y-%m-%d')
            income = float(amount) if transaction_type == "Income" else 0
            expenditure = float(amount) if transaction_type == "Expense" else 0
            remarks = user_input

            row = [date_str, account, income, expenditure, remarks]
            SHEET.append_row(row)
            st.success('Entry added successfully!')

            # Calculate available balance
            all_data = SHEET.get_all_values()
            df = pd.DataFrame(all_data[1:], columns=all_data[0])
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df['Income'] = pd.to_numeric(df['Income'], errors='coerce').fillna(0)
            df['Expenditure'] = pd.to_numeric(df['Expenditure'], errors='coerce').fillna(0)
            balance = df['Income'].sum() - df['Expenditure'].sum()
            st.write(f"**Current Available Balance: {balance}**")

        except json.JSONDecodeError:
            st.error("Gemini returned invalid JSON. Please rephrase your input.")
        except ValueError as ve:
            st.error(f"Error processing Gemini's output: {ve}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")

# --- Statement and Balance at a Point in Time ---
st.subheader("Get Statement or Balance")

statement_date = st.date_input("Select a date for statement/balance:", datetime.today())
get_statement = st.checkbox("Get Statement")
get_balance = st.checkbox("Get Balance")

if st.button("Get Data"):
    if get_statement or get_balance:
        try:
            all_data = SHEET.get_all_values()
            df = pd.DataFrame(all_data[1:], columns=all_data[0])

            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df['Income'] = pd.to_numeric(df['Income'], errors='coerce').fillna(0)
            df['Expenditure'] = pd.to_numeric(df['Expenditure'], errors='coerce').fillna(0)
            
            statement_date = datetime.combine(statement_date, datetime.min.time())
            
            filtered_df = df[df['Date'] <= statement_date]

            if get_statement:
                st.write(f"**Statement as of {statement_date.strftime('%Y-%m-%d')}:**")
                st.dataframe(filtered_df)

            if get_balance:
                balance = filtered_df['Income'].sum() - filtered_df['Expenditure'].sum()
                st.write(f"**Balance as of {statement_date.strftime('%Y-%m-%d')}: {balance}**")

        except Exception as e:
            st.error(f"Error getting statement/balance: {e}")

# --- Monthly Statement ---
st.subheader("Get Monthly Statement")
month_input = st.date_input("Select month for statement", datetime.today())
if st.button("Get Monthly Statement"):
    try:
        all_data = SHEET.get_all_values()
        df = pd.DataFrame(all_data[1:], columns=all_data[0])

        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Income'] = pd.to_numeric(df['Income'], errors='coerce').fillna(0)
        df['Expenditure'] = pd.to_numeric(df['Expenditure'], errors='coerce').fillna(0)

        start_of_month = datetime(month_input.year, month_input.month, 1)
        end_of_month = (start_of_month + pd.offsets.MonthEnd(1)).to_pydatetime()

        filtered_df = df[(df['Date'] >= start_of_month) & (df['Date'] <= end_of_month)]

        st.write(f"**Statement for {start_of_month.strftime('%B %Y')}:**")
        st.dataframe(filtered_df)
    except Exception as e:
        st.error(f"Error getting monthly statement: {e}")
