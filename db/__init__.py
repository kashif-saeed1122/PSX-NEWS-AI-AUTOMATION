"""PSX dashboard database layer (SQLAlchemy + Alembic).

Public exports:
    Base          — declarative base; import to register models with Alembic
    engine        — sync SQLAlchemy engine
    SessionLocal  — sync session factory; use `with SessionLocal() as s:`
"""
from db.models import Base
from db.session import engine, SessionLocal

__all__ = ["Base", "engine", "SessionLocal"]
