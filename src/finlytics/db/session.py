"""Async SQLAlchemy engine and session factory.

Usage
─────
    from finlytics.db.session import async_session_factory

    async with async_session_factory() as session:
        async with session.begin():
            ...
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from finlytics.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
