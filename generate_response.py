import google.generativeai as genai
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
                     
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