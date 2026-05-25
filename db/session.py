"""SQLAlchemy engine + session factory.

Reads DATABASE_URL from .env. Example:
    DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/psx_dashboard
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/psx_dashboard",
)

# pool_pre_ping handles dropped connections (common with Supabase/cloud Postgres).
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
