"""Database session factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openclaw.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    """Yield a database session, auto-closing on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
