from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from typing import List, Dict
import os

app = FastAPI()

client = OpenAI()
SYSTEM_PROMPT = "You are an expert early childhood educator, helping parents to explore the learning of their children. The first thing you always ask is what the child did today. Then you ask questions one at a time to guide the parent through describing the learning. Once you feel that there is enough information (maybe after 5-6 questions) you ask if the parent wants a summary of the learning episode or to keep exploring. If they want a summary, provide a summary of the learning episode, linking it to child development indicators. The child is a toddler. Then, you suggest a deepening activity that is age appropriate that can give the parent some ideas of how to keep the learning going."

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your frontend domain in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend
frontend_dir = os.path.join(os.path.dirname(__file__), '../frontend')
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# Schema: conversation is an array of {"role": ..., "content": ...}
class ChatHistoryRequest(BaseModel):
    history: List[Dict[str, str]]

@app.post("/chat")
async def chat(request: ChatHistoryRequest):
    try:
        history = request.history

        # Basic input validation
        if not history or history[-1]['role'] != 'user':
            return {"response": "Please enter a valid message."}

        # Build the message list for OpenAI (prepend system prompt)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4.1",  # or your preferred model
            messages=messages
        )
        bot_message = response.choices[0].message.content

        return {"response": bot_message}

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"response": f"Error: {str(e)}"}
