import os
from pathlib import Path as _Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

try:
    from dotenv import load_dotenv  # type: ignore
    _env_path = (_Path(__file__).resolve().parents[2] / ".env")  # backend/.env
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path), override=False)
except Exception:
    pass

DB_URL = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Set it in your shell or put it in backend/.env. "
        "Example: postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
    )
# Render uses postgres:// which SQLAlchemy 2.x does not accept
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))
_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    pool_timeout=_POOL_TIMEOUT,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
