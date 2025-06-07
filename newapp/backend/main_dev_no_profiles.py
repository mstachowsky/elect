import os
import uuid
from typing import AsyncGenerator, Optional, List, Dict
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from datetime import datetime

# --- FastAPI Users & Auth Setup ---
from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users import schemas as fa_schemas
from fastapi_users.authentication import (
    CookieTransport, JWTStrategy, AuthenticationBackend
)
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "mysql+asyncmy://mike:mitadp560@localhost/elect_app"  # CHANGE ME!
SECRET = "SUPERSECRET"  # CHANGE ME!

# --- SQLAlchemy models ---
class Base(DeclarativeBase):
    pass

class User(SQLAlchemyBaseUserTableUUID, Base):
    pass

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret   = SECRET
    def parse_id(self, value: str) -> uuid.UUID:
        return uuid.UUID(value)
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f">>> user {user.email} registered (id={user.id})")

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)

class UserRead(fa_schemas.BaseUser[uuid.UUID]): pass
class UserCreate(fa_schemas.BaseUserCreate): pass
class UserUpdate(fa_schemas.BaseUserUpdate): pass

cookie_transport = CookieTransport(cookie_name="auth", cookie_max_age=3600, cookie_secure=False)
def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)
auth_backend = AuthenticationBackend(
    name="jwt", transport=cookie_transport, get_strategy=get_jwt_strategy,
)
async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)

# --- FastAPI App & Middleware ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Serve Static and HTML ---
frontend_dir = os.path.join(os.path.dirname(__file__), '../frontend')
if not os.path.isdir(frontend_dir):
    raise RuntimeError(f"Frontend directory missing: {frontend_dir}")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
from fastapi.responses import RedirectResponse
from fastapi import Request

@app.get("/", include_in_schema=False)
async def root():
    #return FileResponse(os.path.join(frontend_dir, "index_chat_dev.html"))
    return FileResponse(os.path.join(frontend_dir, "index_dev.html"))

@app.get("/chat_redirect", include_in_schema=False)
async def serve_chat_ui(user: User = Depends(current_active_user)):
    return FileResponse(os.path.join(frontend_dir, "index_chat_dev.html"))

@app.get("/auth", include_in_schema=False)
async def serve_auth_ui(request: Request):
    try:
        user = await current_active_user(request)
    except Exception:
        user = None
    if user:
        return RedirectResponse("/chat_redirect")
    return FileResponse(os.path.join(frontend_dir, "index_dev.html"))

"""
@app.get("/auth/", include_in_schema=False)
async def serve_auth_ui():
    return FileResponse(os.path.join(frontend_dir, "index_dev.html"))
"""
# --- Auth Routers ---
app.include_router(
    fastapi_users.get_auth_router(auth_backend, requires_verification=False),
    prefix="/auth/jwt",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# --- Protected Endpoints ---

@app.get("/whoami", tags=["users"])
async def whoami(user: User = Depends(current_active_user)):
    return {"email": user.email}

# --- Chat API ---
client = OpenAI()

age_group = "toddler"
age = 18
age_unit = "months"
SYSTEM_PROMPT = f"""You are an expert early childhood educator, helping parents to explore the learning of their children. The child is a {age_group}, about {age} {age_unit} old.  The first thing you always ask is what the child did today. Then you ask questions one at a time to guide the parent through describing the learning. Once you feel that there is enough information (maybe 3-5 questions maximum) you ask if the parent wants a summary of the learning episode or to keep exploring. If they want a summary, provide a summary of the learning episode, linking it to child development indicators in a way the parents, who are experts on their children but not necessarily child development, can understand. You must start your summary with the exact string: "## Summary:". Once you output the summary, never output another summary unless you are explicitly asked. Then, you provide a deepening activity that is age appropriate that can give the parent some ideas of how to keep the learning going."""

class ChatHistoryRequest(BaseModel):
    history: List[Dict[str, str]]

@app.post("/chat", tags=["chat"])
async def chat(request: ChatHistoryRequest, user: User = Depends(current_active_user)):
    print(request)
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
            chat_lines = []
            for msg in history:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")
                chat_lines.append(f"{role}: {content}\n")
            chat_text = "".join(chat_lines)
            elect_info = analyze_elect(chat_text)
            elect_summary = summarize_elect(bot_message.split("## Summary:")[1], elect_info)
            bot_message = bot_message + "\n\n" + "Here's some information for you about how this interaction lines up with child development indicators: \n" + elect_summary
            print(bot_message)
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
            
            #add the last message and elect summary
            chat_text = "## Chat:\n" + chat_text + "\n" + bot_message + "\n\n## ELECT_ANALYSIS:\n"+elect_info

            # Save file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(chat_text)

        return {"response": bot_message}

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"response": f"Error: {str(e)}"}

@app.post("/save_chat", tags=["chat"])
async def save_chat(request: ChatHistoryRequest, user: User = Depends(current_active_user)):
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

        # now perform the analysis
        elect_analysis = analyze_elect(chat_text)
        elect_analysis_filepath = os.path.join(saved_dir, f"elect_analysis_{timestamp}.txt")
        with open(elect_analysis_filepath, 'w', encoding='utf-8', errors='ignore') as r:
            r.write(elect_analysis)

        return {
            "success": True,
            "filename": f"chat_{timestamp}.txt",
            "elect_analysis": elect_analysis
        }

    except Exception as e:
        print(f"Save chat error: {str(e)}")
        return {"success": False, "error": str(e)}

# --- Analysis Helpers ---
def analyze_elect(chat_history):
    BACKGROUND_FILE_PATH = "elect_documents/toddler.txt"
    try:
        with open(BACKGROUND_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as reader:
            BACKGROUNDS = reader.read().split("###")
    except Exception as e:
        print("Failed to open elect document:", e)
        return ""
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

def summarize_elect(summary, elect_analysis):
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

# --- Create tables at startup (replace with Alembic migrations in prod) ---
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
