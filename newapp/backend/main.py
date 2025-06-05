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
SYSTEM_PROMPT = "You are an expert early childhood educator, helping parents to explore the learning of their children. The first thing you always ask is what the child did today. Then you ask questions one at a time to guide the parent through describing the learning. Once you feel that there is enough information (we are developing the process, so please just ask exactly one question then move on to summary) you ask if the parent wants a summary of the learning episode or to keep exploring. If they want a summary, provide a summary of the learning episode, linking it to child development indicators. The child is a toddler. Then, you suggest a deepening activity that is age appropriate that can give the parent some ideas of how to keep the learning going."

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

        # If no history, let the LLM begin!
        if not history:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages
            )
            bot_message = response.choices[0].message.content
            return {"response": bot_message}

        # Normal flow for user-initiated messages
        if history[-1]['role'] != 'user':
            return {"response": "Please enter a valid message."}

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )
        bot_message = response.choices[0].message.content
        return {"response": bot_message}

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"response": f"Error: {str(e)}"}


from datetime import datetime

def analyze_elect(chat_history):
    BACKGROUND_FILE_PATH = "elect_documents/toddler.txt"
    with open(BACKGROUND_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as reader:
        BACKGROUNDS = reader.read().split("###")
    DOMAINS = [
        "Physical Domain",
        "Social Domain",
        "Emotional Domain",
        "Communication, Language, and Literacy Domain",
        "Cognitive Domain",
    ]
    bot_message = ""
    for i, bk in enumerate(BACKGROUNDS[1:]):  # skip the empty string
        if bk.strip() != "":
            try:
                extract_summary_prompt = f"""
                You are an expert early childhood educator. You've just spoken with a parent about a learning episode that they saw their toddler experience. You will now go through a document of indicators of toddler development. For each indicator, determine if it was clearly observed in the learning episode. If so:
                    1. Output the indicator name (the text following the word INDICATOR in the document)
                    2. Output a very brief (1 sentence) explanation of how that indicator was observed

                The document is: {bk}

                And the chat history is: {chat_history}

                If there is no clear observations for a given indicator, don't output anything for that indicator.
                                """
                messages = [{"role": "user", "content": extract_summary_prompt}]
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=messages
                )
                content = response.choices[0].message.content.strip()
                if content:
                    if bot_message != "":
                        bot_message += "\n\n"
                    bot_message += f"{DOMAINS[i]}\n{content}"
            except Exception as e:
                print(f"an error: {e}")
    return bot_message

@app.post("/save_chat")
async def save_chat(request: ChatHistoryRequest):

    try:
        # Create saved directory if it doesn't exist
        saved_dir = os.path.join(os.path.dirname(__file__), 'saved')
        os.makedirs(saved_dir, exist_ok=True)

        # Timestamp for filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(saved_dir, f"chat_{timestamp}.txt")

        # Format chat as text
        chat_lines = []
        for msg in request.history:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            chat_lines.append(f"{role}: {content}\n")
        chat_text = "".join(chat_lines)

        # Save file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(chat_text)
            
        #now perform the analysis
        elect_analysis = analyze_elect(chat_text)
        elect_analysis_filepath = os.path.join(saved_dir,f"elect_analysis_{timestamp}.txt")
        with open(elect_analysis_filepath,'w',encoding='utf-8',errors='ignore') as r:
            r.write(elect_analysis)
        #return {"success": True, "filename": f"chat_{timestamp}.txt"}
        return {
            "success": True,
            "filename": f"chat_{timestamp}.txt",
            "elect_analysis": elect_analysis
        }

    except Exception as e:
        print(f"Save chat error: {str(e)}")
        return {"success": False, "error": str(e)}
