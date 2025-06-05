from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI()

client = OpenAI()
SYSTEM_PROMPT = "You are a helpful chatbot."  # Set this to anything you want

# Enable CORS for frontend (adjust if you deploy)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve files from ../frontend (adjust path as needed)
frontend_dir = os.path.join(os.path.dirname(__file__), '../frontend')
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        user_message = request.message
        print(request.message)
        # Log the chat
        with open("chat_log.txt", "a") as f:
            f.write(f"User: {user_message}\n")

        # Chat completion
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=user_message,
        )
        bot_message = response.output_text
        print(bot_message)
        # Log bot reply
        with open("chat_log.txt", "a") as f:
            f.write(f"Bot: {bot_message}\n")

        return {"response": bot_message}
    except Exception as e:
        print(e)
        # Log the error to help you debug
        with open("chat_log.txt", "a") as f:
            f.write(f"Error: {str(e)}\n")
        # Return error message to frontend
        return {"response": f"Internal error: {str(e)}"}
    