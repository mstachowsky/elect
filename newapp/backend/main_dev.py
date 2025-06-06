# main.py
import os
import uuid
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users import schemas as fa_schemas
from fastapi_users.authentication import (
    CookieTransport,
    JWTStrategy,
    AuthenticationBackend,
)
from fastapi_users.db import (
    SQLAlchemyBaseUserTableUUID,
    SQLAlchemyUserDatabase,
)

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# ───────────── CONFIG ──────────────
DATABASE_URL = "mysql+asyncmy://mike:mitadp560@localhost/elect_app"  # ← adjust!
SECRET       = "SUPERSECRET"  # ← change for production


# ───────────── DATABASE LAYER ──────
class Base(DeclarativeBase):  # SQLAlchemy 2.0 style
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    """DB model. Inherit from SQLAlchemyBaseUserTableUUID to get id,
    email, hashed_password, is_active, is_superuser, is_verified."""
    # Add extra columns here if you like (e.g., first_name = Column(String))
    pass

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):     # 👈 add it FIRST
    reset_password_token_secret = SECRET
    verification_token_secret   = SECRET
    def parse_id(self, value: str) -> uuid.UUID:
        return uuid.UUID(value)

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ):
        print(f">>> user {user.email} registered (id={user.id})")
engine               = create_async_engine(DATABASE_URL, echo=True)
async_session_maker  = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


# ───────────── Pydantic Schemas ─────
class UserRead(fa_schemas.BaseUser[uuid.UUID]):   # what the API returns
    pass


class UserCreate(fa_schemas.BaseUserCreate):      # payload for /auth/register
    pass


class UserUpdate(fa_schemas.BaseUserUpdate):      # PATCH /users/{id}
    pass


# ───────────── AUTHENTICATION ───────
cookie_transport = CookieTransport(cookie_name="auth", cookie_max_age=3600,cookie_secure=False)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

"""
class UserManager(BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret   = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f">>> user {user.email} registered (id={user.id})")
"""

async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)


# ───────────── FASTAPI APP ───────────
app = FastAPI()

# (Optional) serve a pre-built frontend if the folder exists
frontend_dir = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index_dev.html"))
else:

    @app.get("/", tags=["health"])
    async def root():
        return {"msg": "API is running"}


# Routers ─────────────────────────────
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


# Protected example route
@app.get("/whoami")
async def whoami(user: User = Depends(current_active_user)):
    print(repr(user))
    print(user.email)
    return {"email": user.email}


# Create tables at startup (replace with Alembic migrations in prod)
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
