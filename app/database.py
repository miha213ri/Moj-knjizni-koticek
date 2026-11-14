from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DATABASE_URL

is_sqlite = DATABASE_URL.startswith("sqlite")
if is_sqlite:
    connect_args = {"check_same_thread": False}
else:
    # Force the client connection encoding, even when DATABASE_URL came
    # directly from cPanel and did not contain a charset query parameter.
    connect_args = {"connect_timeout": 10, "charset": "utf8mb4"}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=1200,
    pool_size=2 if not is_sqlite else 5,
    max_overflow=1 if not is_sqlite else 5,
    pool_timeout=20,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
