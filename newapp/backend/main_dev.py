import os, uuid
from typing import AsyncGenerator, Optional, List, Dict
from datetime import datetime

from fastapi import (
    FastAPI, Depends, Request, HTTPException, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from pydantic import BaseModel
from openai import OpenAI

# --- FastAPI-Users & Auth ---------------------------------------------------
from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users import schemas as fa_schemas
from fastapi_users.authentication import (
    CookieTransport, JWTStrategy, AuthenticationBackend
)
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase

# --- SQLAlchemy -------------------------------------------------------------
from sqlalchemy import String, Text, Integer, ForeignKey, select
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)
from sqlalchemy.orm import (
    DeclarativeBase, relationship, selectinload,
    Mapped, mapped_column
)

# ---------------------------------------------------------------------------

DATABASE_URL = "mysql+asyncmy://mike:mitadp560@localhost/elect_app"  # CHANGE ME
SECRET        = "SUPERSECRET"                                       # CHANGE ME

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status


# === Base & User ============================================================
class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Inherits the default table name 'user' from FastAPI-Users."""


# === NEW PROFILE TABLES =====================================================
class ParentProfile(Base):
    __tablename__ = "parent_profiles"

    id:        Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id:   Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), unique=True
    )
    name:       Mapped[str] = mapped_column(String(255))
    preferences:Mapped[str] = mapped_column(Text, default="")

    children:   Mapped[List["ChildProfile"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


async def get_parent_profile_by_user(
    session: AsyncSession,
    user_id: int,
) -> ParentProfile:
    result = await session.execute(
        select(ParentProfile)
        .filter_by(user_id=user_id)
        .options(selectinload(ParentProfile.children))
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return parent




class ChildProfile(Base):
    __tablename__ = "child_profiles"

    id:        Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parent_profiles.id")
    )
    name:       Mapped[str] = mapped_column(String(255))
    age_years:  Mapped[int] = mapped_column(Integer, default=0)
    age_months: Mapped[int] = mapped_column(Integer, default=0)
    preferences:Mapped[str] = mapped_column(Text, default="")

    parent:     Mapped["ParentProfile"] = relationship(back_populates="children")

async def get_child_by_id(session: AsyncSession, child_id: uuid.UUID):
    result = await session.execute(select(ChildProfile).where(ChildProfile.id == child_id))
    return result.scalar_one_or_none()

# === Pydantic Schemas =======================================================
class ChildBase(BaseModel):
    name: str
    age_years: int = 0
    age_months: int = 0
    preferences: str = ""



class ChildRead(ChildBase):
    id: uuid.UUID
    class Config:
        orm_mode = True


class ChildCreate(ChildBase):
    pass


class ChildUpdate(ChildBase):
    pass


class ParentBase(BaseModel):
    name: str
    preferences: str = ""


class ParentRead(ParentBase):
    id: uuid.UUID
    children: List[ChildRead] = []

    class Config:
        orm_mode = True


class ParentCreate(ParentBase):
    pass


class ParentUpdate(ParentBase):
    pass


# === User Manager / Sessions ===============================================
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret   = SECRET

    def parse_id(self, value: str) -> uuid.UUID:  # needed by async-my
        return uuid.UUID(value)

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ):
        print(f">>> user {user.email} registered (id={user.id})")


engine = create_async_engine(DATABASE_URL, echo=True, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


cookie_transport = CookieTransport(
    cookie_name="auth", cookie_max_age=3600, cookie_secure=False
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt", transport=cookie_transport, get_strategy=get_jwt_strategy
)


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)

# === FastAPI App ============================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static / HTML ----------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "../frontend")
if not os.path.isdir(FRONTEND_DIR):
    raise RuntimeError(f"Frontend directory missing: {FRONTEND_DIR}")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index_dev.html"))


@app.get("/chat_redirect", include_in_schema=False)
async def serve_chat_ui(user: User = Depends(current_active_user)):
    return FileResponse(os.path.join(FRONTEND_DIR, "index_chat_dev.html"))


@app.get("/auth", include_in_schema=False)
async def serve_auth_ui(request: Request):
    try:
        user = await current_active_user(request)
    except Exception:
        user = None
    if user:
        return RedirectResponse("/chat_redirect")
    return FileResponse(os.path.join(FRONTEND_DIR, "index_dev.html"))


@app.get("/profiles", include_in_schema=False)
async def serve_profiles(user: User = Depends(current_active_user)):
    return FileResponse(os.path.join(FRONTEND_DIR, "profiles.html"))

# --- Auth Routers -----------------------------------------------------------
app.include_router(
    fastapi_users.get_auth_router(auth_backend, requires_verification=False),
    prefix="/auth/jwt",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_register_router(
        fa_schemas.BaseUser[uuid.UUID], fa_schemas.BaseUserCreate
    ),
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_users_router(
        fa_schemas.BaseUser[uuid.UUID], fa_schemas.BaseUserUpdate
    ),
    prefix="/users",
    tags=["users"],
)

# --- Utility ----------------------------------------------------------------
@app.get("/whoami", tags=["users"])
async def whoami(user: User = Depends(current_active_user)):
    return {"email": user.email}

# === PROFILES REST API ======================================================
# -- Parent -------------------------------------------------
@app.get("/api/parent", response_model=ParentRead, tags=["profiles"])
async def get_parent_profile(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(
        select(ParentProfile)
        .filter_by(user_id=user.id)
        .options(selectinload(ParentProfile.children))
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Profile not found")
    return parent


@app.post("/api/parent", response_model=ParentRead, tags=["profiles"])
async def create_or_update_parent(
    payload: ParentCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(
        select(ParentProfile).filter_by(user_id=user.id)
    )
    parent = result.scalar_one_or_none()
    if parent:
        parent.name = payload.name
        parent.preferences = payload.preferences
    else:
        parent = ParentProfile(
            user_id=user.id,
            name=payload.name,
            preferences=payload.preferences,
        )
        session.add(parent)
    await session.commit()
    await session.refresh(parent, ["children"])
    return parent


# -- Children ------------------------------------------------
@app.post("/api/children", response_model=ChildRead, tags=["profiles"])
async def add_child(
    child: ChildCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(
        select(ParentProfile).filter_by(user_id=user.id)
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Create parent profile first")
    new_child = ChildProfile(
        parent_id=parent.id,
        name=child.name,
        age_years=child.age_years,
        age_months=child.age_months,
        preferences=child.preferences,
    )
    session.add(new_child)
    await session.commit()
    await session.refresh(new_child)
    return new_child


@app.put("/api/children/{child_id}", response_model=ChildRead, tags=["profiles"])
async def update_child(
    child_id: uuid.UUID,
    payload: ChildUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(
        select(ChildProfile)
        .join(ParentProfile)
        .filter(ChildProfile.id == child_id, ParentProfile.user_id == user.id)
    )
    
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    child.name = payload.name
    child.age_years = payload.age_years
    child.age_months = payload.age_months
    child.preferences = payload.preferences
    await session.commit()
    await session.refresh(child)
    return child



@app.delete("/api/children/{child_id}", status_code=204, tags=["profiles"])
async def delete_child(
    child_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    result = await session.execute(
        select(ChildProfile)
        .join(ParentProfile)
        .filter(ChildProfile.id == child_id, ParentProfile.user_id == user.id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    await session.delete(child)
    await session.commit()
    return None


# --- Chat API ---
client = OpenAI()

def make_prompt(age_years,age_months,name,preferences):
    total_months = age_years * 12 + age_months
    
    age_group = "infant"
    
    if total_months > 14 and total_months < 36:
        age_group = "toddler"
    if total_months >= 36 and total_months < 72:
        age_group = "preschool"
    if total_months > 72:
        age_group = "school age"
    
    prompt = f"""You are an expert early childhood educator, helping parents to explore the learning of their children. The child is in the {age_group} age group, about {age_years} years and {age_months} months old. The child's name is {name} and they like {preferences}. 
    
    The first thing you always ask is what the child did today. Then you ask questions one at a time to guide the parent through describing the learning. Once you feel that there is enough information (maybe 3-5 questions maximum) you ask if the parent wants a summary of the learning episode or to keep exploring. If they want a summary, provide a summary of the learning episode, linking it to child development indicators in a way the parents, who are experts on their children but not necessarily child development, can understand. You must start your summary with the exact string: "## Summary:". Once you output the summary, never output another summary unless you are explicitly asked. Then, you provide a deepening activity that is age appropriate that can give the parent some ideas of how to keep the learning going."""
    
    elect_path = "elect_documents"
    elect_doc = f"{elect_path}/infant.txt"
    if age_group == "toddler":
        elect_doc = f"{elect_path}/toddler.txt"
    if age_group == "preschool":
        elect_doc = f"{elect_path}/preschool.txt"
    if age_group == "school age":
        elect_doc = f"{elect_path}/schoolage.txt"
    
    return [prompt,elect_doc]

class ChatHistoryRequest(BaseModel):
    history: List[Dict[str, str]]
    child_id: Optional[str] = None  # Add this field!



@app.post("/chat", tags=["chat"])
async def chat(request: ChatHistoryRequest, user: User = Depends(current_active_user),session: AsyncSession = Depends(get_async_session)):
    print("PARENT: ")
    parent_data = await get_parent_profile_by_user(session, user.id)
    print(parent_data.name)
    print(parent_data.preferences)
    child_data = None
    if request.child_id:
        child_uuid = uuid.UUID(str(request.child_id))  # Explicit conversion
        child_data = await get_child_by_id(session, child_uuid)
        if child_data:
            print("CHILD:")
            print(child_data.name)
            print(child_data.age_years)
            print(child_data.age_months)
            print(child_data.preferences)
        else:
            print("Child not found.")

    try:
        history = request.history
        if child_data is not None:
            [SYSTEM_PROMPT,elect_doc] = make_prompt(child_data.age_years,child_data.age_months,child_data.name,child_data.preferences)
            print("Loaded it up")
        else:
            #default to toddler
            [SYSTEM_PROMPT,elect_doc] = make_prompt(1,0,"","normal toddler things")
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
            elect_info = analyze_elect(chat_text,elect_doc)
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
def analyze_elect(chat_history,BACKGROUND_FILE_PATH = "elect_documents/toddler.txt"):

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
