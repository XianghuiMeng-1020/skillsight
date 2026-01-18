import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# --- DB URL resolution (locked) ---
import os
from pathlib import Path as _Path
try:
    # Load backend/.env if present, but do not override already-exported env vars.
    from dotenv import load_dotenv  # type: ignore
    _env_path = (_Path(__file__).resolve().parents[2] / ".env")  # backend/.env
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path), override=False)
except Exception:
    # dotenv is optional; env vars may be provided by shell/docker
    pass

DB_URL = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Set it in your shell or put it in backend/.env. "
        "Example: postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
    )
# --- end DB URL resolution ---

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://skillsight:skillsight@localhost:5432/skillsight")
engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
