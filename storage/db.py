"""
Storage layer — SQLite + SQLModel

v0: 本機 SQLite
v2: 換 Postgres（只要改 DATABASE_URL）
"""

import os
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select

from core.models import Client, Project, Income, WithholdingSlip, Expense, UserSettings


# 資料夾結構
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv(
    "DIANA_TAX_DB",
    f"sqlite:///{DATA_DIR}/diana.db"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)


def init_db():
    """建表 + 塞預設 UserSettings"""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        settings = session.get(UserSettings, 1)
        if not settings:
            session.add(UserSettings(id=1))
            session.commit()


def get_session():
    return Session(engine)


# ============================================================
# CRUD helpers — 簡單的 wrapper，未來可以擴展為 repository pattern
# ============================================================

def list_incomes(tax_year: int = 114, limit: int = 500):
    with get_session() as s:
        stmt = select(Income).where(Income.tax_year == tax_year).order_by(Income.date.desc()).limit(limit)
        return list(s.exec(stmt))


def list_clients():
    with get_session() as s:
        return list(s.exec(select(Client).order_by(Client.name)))


def list_projects(archived: bool = False):
    with get_session() as s:
        stmt = select(Project).where(Project.archived == archived).order_by(Project.created_at.desc())
        return list(s.exec(stmt))


def get_settings() -> UserSettings:
    with get_session() as s:
        settings = s.get(UserSettings, 1)
        if not settings:
            settings = UserSettings(id=1)
            s.add(settings)
            s.commit()
            s.refresh(settings)
        return settings


def save_income(income: Income):
    with get_session() as s:
        s.add(income)
        s.commit()
        s.refresh(income)
        return income


def save_client(client: Client):
    with get_session() as s:
        s.add(client)
        s.commit()
        s.refresh(client)
        return client


def save_project(project: Project):
    with get_session() as s:
        s.add(project)
        s.commit()
        s.refresh(project)
        return project


def update_settings(settings: UserSettings):
    with get_session() as s:
        existing = s.get(UserSettings, 1)
        if existing:
            for k, v in settings.model_dump(exclude={'id'}).items():
                setattr(existing, k, v)
            s.add(existing)
        else:
            s.add(settings)
        s.commit()


def delete_income(income_id):
    with get_session() as s:
        inc = s.get(Income, income_id)
        if inc:
            s.delete(inc)
            s.commit()
