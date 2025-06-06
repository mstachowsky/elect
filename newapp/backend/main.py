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

age_group = "toddler"
age = 18
age_unit = "months"

SYSTEM_PROMPT = f"""You are an expert early childhood educator, helping parents to explore the learning of their children. The child is a {age_group}, about {age} {age_unit} old.  The first thing you always ask is what the child did today. Then you ask questions one at a time to guide the parent through describing the learning. Once you feel that there is enough information (maybe 3-5 questions maximum) you ask if the parent wants a summary of the learning episode or to keep exploring. If they want a summary, provide a summary of the learning episode, linking it to child development indicators in a way the parents, who are experts on their children but not necessarily child development, can understand. You must start your summary with the exact string: "## Summary:". Once you output the summary, never output another summary unless you are explicitly asked. Then, you suggest a deepening activity that is age appropriate that can give the parent some ideas of how to keep the learning going."""

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
            model="gpt-4.1",
            messages=messages
        )
        bot_message = response.choices[0].message.content
        
        if "## Summary:" in bot_message:
            # Format chat as text
            print(bot_message)
            chat_lines = []
            for msg in history:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")
                chat_lines.append(f"{role}: {content}\n")
            chat_text = "".join(chat_lines)
            elect_info = analyze_elect(chat_text)
            elect_summary = summarize_elect(bot_message.split("## Summary:")[1],elect_info)
            bot_message = bot_message + "\n\n" + "Here's some information for you about how this interaction lines up with child development indicators: \n" + elect_summary
            
            cleanup_prompt = f"""
                The following text contains a summary, some deepening questions/activities, and information about how the interaction lines up with child development. Rewrite it without changing any words so that the text starts with the summary, then the child development information, and finally deepening questions/activities are at the end. The text is:
                    
                    {bot_message}
            """
            
            cleanup_messages = [{"role": "user", "content": cleanup_prompt}]
            response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=cleanup_messages
                )
            content = response.choices[0].message.content.strip()
            bot_message = content
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
                    1. Output the string "INDICATOR" followed by the indicator name (the text following the word INDICATOR between the two colons in the document. Don't output the indicator description after that)
                    2. Output a very brief (1 sentence) explanation of how that indicator was observed

                The document is: {bk}

                And the chat history is: {chat_history}

                If there is no clear observations for a given indicator, don't output anything for that indicator.
                                """
                messages = [{"role": "user", "content": extract_summary_prompt}]
                response = client.chat.completions.create(
                    model="gpt-4.1",
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

def summarize_elect(summary,elect_analysis):
    prompt = f"""
        Here's a summary of a conversation you had with a parent:
            
            {summary}
        
        And here is how you linked it to a child development document:
            
            {elect_analysis}
            
        Summarize the three most important indicators from the document given the interaction, and present them to the parent in an easy to understand way. Output only your summary, no extra text.
    """
    messages = [{"role": "user", "content": prompt}]
    response = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=messages
                )
    content = response.choices[0].message.content.strip()
    return content
    

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
