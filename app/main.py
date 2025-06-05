"""FastAPI Learning‑Stories entry‑point with Ollama integration."""
from __future__ import annotations

import os
import re
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from html import unescape
import ollama
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import SQLModel, Field, create_engine, Session, select

# ----------------------------
# Configuration & helpers
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
USERS_FILE = BASE_DIR / "usernames.txt"
BACKGROUND_FILE = BASE_DIR / "infant_toddler_short.txt"
DB_URL = f"sqlite:///{BASE_DIR / 'learning_stories.db'}"
SECRET_KEY = secrets.token_urlsafe(32)

# Ollama configuration (override via env‑vars if desired)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ece-nebula16:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "cogito:70b")

# Load offline usernames
if not USERS_FILE.exists():
    raise RuntimeError("usernames.txt not found – create it with one username per line.")
ALLOWED_USERS = {u.strip() for u in USERS_FILE.read_text().splitlines() if u.strip()}

# Read developmental‑background file (split on ###)
if not BACKGROUND_FILE.exists():
    raise RuntimeError(
        "infant_toddler_short.txt not found – place it beside main.py or update BACKGROUND_FILE path."
    )
BACKGROUNDS = BACKGROUND_FILE.read_text(encoding="utf-8", errors="ignore").split("###")
DOMAINS = [
    "Physical Domain",
    "Social Domain",
    "Emotional Domain",
    "Communication, Language, and Literacy Domain",
    "Cognitive Domain",
]
if len(BACKGROUNDS) - 1 != len(DOMAINS):
    print(
        "⚠️  WARNING: Number of domain labels does not match BACKGROUNDS sections – output may misalign."
    )

# ----------------------------
# Database models
# ----------------------------
class Child(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner: str = Field(index=True)  # username that owns the child
    name: str
    birth_date: date


class Story(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id", index=True)
    story_text: str
    output_text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)


engine = create_engine(DB_URL, echo=False)
SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session

# ----------------------------
# FastAPI setup
# ----------------------------
app = FastAPI(title="Learning Stories Prototype")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ----------------------------
# Utility – auth helpers
# ----------------------------

def get_current_username(request: Request) -> Optional[str]:
    return request.session.get("username")


def require_login(request: Request) -> str:
    username = get_current_username(request)
    if not username:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})
    return username

# ----------------------------
# LLM helper functions
# ----------------------------

def parse_llm_output(text: str):
    """Parse the XML‑like format returned by the LLM into a list of dicts."""
    # 1) strip <think>…</think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 2) split on <indicator>
    parts = text.split("<indicator>")
    results = []
    for part in parts[1:]:
        title_match = re.match(r"(.*?)</indicator>", part, re.DOTALL)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        if "<applicable>" not in part:
            continue
        explanation_match = re.search(r"<explanation>(.*?)</explanation>", part, re.DOTALL)
        explanation = explanation_match.group(1).strip() if explanation_match else ""
        results.append({"title": title, "explanation": explanation})
    return results


def produce_output(story_text: str) -> str:
    print(f"STORY: {story_text}")
    """Send the user's point‑form story to Ollama and return formatted text."""
    client = ollama.Client(host=OLLAMA_HOST)
    blocks = []
    for i, background in enumerate(BACKGROUNDS[1:]):  # skip section before first ###
        domain = DOMAINS[i] if i < len(DOMAINS) else f"Domain {i+1}"
        system_prompt = f"""
You are helping to analyze developmental observations for a toddler, L. The toddler is 15 months old. You will be provided a point‑form set of observations and background from a document that explains various developmental indicators in various domains. You must consider **all** indicators in the background. The indicators are labeled according to the string INDICATOR, then a short description, then a colon, and then a long description.

For **each** indicator:
  1. Repeat the indicator's short description verbatim within <indicator> and </indicator> tags
  2. Output <applicable> if the indicator is applicable, otherwise <not applicable>
  3. If applicable, provide a brief explanation inside <explanation>…</explanation>
  4. If not applicable, give no explanation.

Stick strictly to observations and background. Make no unsupported guesses.

### Background
{background}

### Point‑form observations
{story_text}
"""
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                #{"role": "system", "content": "Enable deep thinking subroutine."},
                {"role": "user", "content": system_prompt},
            ],
            stream=False,
        )
        print(response["message"]["content"])
        indicators = parse_llm_output(response["message"]["content"])
        if indicators:
            formatted = "\n".join(f"- {item['title']}: {item['explanation']}" for item in indicators)
            blocks.append(f"{domain}:\n{formatted}")
    return "\n\n".join(blocks) if blocks else "No applicable indicators found."

# ----------------------------
# Routes – Auth
# ----------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...)):
    username = username.strip()
    if username not in ALLOWED_USERS:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Unknown username."},
            status_code=400,
        )
    request.session["username"] = username
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# ----------------------------
# Routes – Home / dashboard
# ----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session: Session = Depends(get_session)):
    username = require_login(request)
    children = session.exec(select(Child).where(Child.owner == username)).all()
    return templates.TemplateResponse(
        "home.html", {"request": request, "children": children, "username": username}
    )

# ----------------------------
# Routes – Children
# ----------------------------
@app.get("/child/new", response_class=HTMLResponse)
async def child_form(request: Request):
    require_login(request)
    return templates.TemplateResponse("child_form.html", {"request": request})


@app.post("/child/new")
async def child_create(
    request: Request,
    name: str = Form(...),
    birth_date: date = Form(...),
    session: Session = Depends(get_session),
):
    username = require_login(request)
    child = Child(owner=username, name=name.strip(), birth_date=birth_date)
    session.add(child)
    session.commit()
    return RedirectResponse(f"/child/{child.id}", status_code=303)


@app.get("/child/{child_id}", response_class=HTMLResponse)
async def child_detail(child_id: int, request: Request, session: Session = Depends(get_session)):
    username = require_login(request)
    child = session.get(Child, child_id)
    if not child or child.owner != username:
        raise HTTPException(404)

    stories = session.exec(
        select(Story).where(Story.child_id == child.id).order_by(Story.timestamp.desc())
    ).all()

    # Unescape output_text for display clarity
    for story in stories:
        if story.output_text:
            story.output_text = unescape(story.output_text)

    return templates.TemplateResponse(
        "child_detail.html", {"request": request, "child": child, "stories": stories}
    )

# ----------------------------
# Routes – Learning Stories
# ----------------------------
@app.get("/story/new/{child_id}", response_class=HTMLResponse)
async def story_form(child_id: int, request: Request, session: Session = Depends(get_session)):
    username = require_login(request)
    child = session.get(Child, child_id)
    if not child or child.owner != username:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "story_form.html", {"request": request, "child": child, "output": None, "story_text": ""}
    )


@app.post("/story/preview/{child_id}", response_class=HTMLResponse)
async def story_preview(
    child_id: int,
    request: Request,
    story_text: str = Form(...),
    session: Session = Depends(get_session),
):
    username = require_login(request)
    child = session.get(Child, child_id)
    if not child or child.owner != username:
        raise HTTPException(404)
    output = produce_output(story_text)
    return templates.TemplateResponse(
        "story_form.html",
        {"request": request, "child": child, "story_text": story_text, "output": output},
    )


@app.post("/story/save/{child_id}")
async def story_save(
    child_id: int,
    request: Request,
    story_text: str = Form(...),
    output_text: str = Form(...),
    session: Session = Depends(get_session),
):
    username = require_login(request)
    child = session.get(Child, child_id)
    if not child or child.owner != username:
        raise HTTPException(404)
    story = Story(child_id=child.id, story_text=story_text, output_text=output_text)
    session.add(story)
    session.commit()
    return RedirectResponse(f"/child/{child.id}", status_code=303)


@app.post("/story/delete/{story_id}")
async def story_delete(
    story_id: int,
    request: Request,
        session: Session = Depends(get_session),
    ):
        username = require_login(request)
        story = session.get(Story, story_id)
        if not story:
            raise HTTPException(404)
        child = session.get(Child, story.child_id)
        if not child or child.owner != username:
            raise HTTPException(403)
        session.delete(story)
        session.commit()
        return RedirectResponse(f"/child/{child.id}", status_code=303)

