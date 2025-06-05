from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from typing import List, Dict
import os

# Initialize FastAPI app
app = FastAPI()

# Set up OpenAI client
client = OpenAI()

# Set the system prompt
SYSTEM_PROMPT = "You are a helpful chatbot."

# Initialize in-memory chat history (shared across all users for now)
chat_history: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend files
frontend_dir = os.path.join(os.path.dirname(__file__), '../frontend')
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# Define request body schema
class ChatRequest(BaseModel):
    message: str

# Chat endpoint
@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        user_message = request.message.strip()
        if not user_message:
            return {"response": "Please enter a valid message."}

        # Append user's message to the conversation
        chat_history.append({"role": "user", "content": user_message})

        # Call OpenAI chat completion API
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # Or your desired model
            messages=chat_history
        )

        # Extract assistant's reply
        bot_message = response.choices[0].message.content
        chat_history.append({"role": "assistant", "content": bot_message})

        return {"response": bot_message}

    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        return {"response": error_message}
