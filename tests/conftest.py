import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/waterwatch_test"

# Point the app at the test database & redis DB 15 (separate from dev data) before importing it.
settings.DATABASE_URL = TEST_DATABASE_URL
settings.REDIS_URL = "redis://localhost:6379/15"
settings.APP_ENV = "development"
settings.ML_MODE = "mock"

from app.database import Base  # noqa: E402
from app.database import get_db as app_get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.realtime.redis_bus import redis_bus  # noqa: E402

# NullPool: each connection is opened and closed fresh, so this engine works
# safely even though pytest-asyncio gives each test function its own event
# loop by default (no connections are cached across loops).
test_engine = create_async_engine(TEST_DATABASE_URL, future=True, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


def pytest_configure(config):
    async def _create():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())


def pytest_unconfigure(config):
    async def _drop():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await test_engine.dispose()

    asyncio.run(_drop())


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Truncate all tables between tests for isolation, keeping schema."""
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "spatial_ref_sys":
                await conn.execute(table.delete())


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[app_get_db] = _override_get_db


@pytest_asyncio.fixture
async def client():
    from app.services.environmental_pipeline import environmental_pipeline_registry
    from app.services.prediction import prediction_registry

    await prediction_registry.startup()
    app.state.prediction_registry = prediction_registry
    await environmental_pipeline_registry.startup()
    app.state.environmental_pipeline = environmental_pipeline_registry.pipeline

    # Fresh redis connection tied to this test's event loop.
    await redis_bus.connect()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await redis_bus.disconnect()
    await prediction_registry.shutdown()
    await environmental_pipeline_registry.shutdown()


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


class ws_app_client:
    """Async context manager (not a pytest fixture) providing a WebSocket-
    capable test client with the redis pub/sub -> websocket listener
    running. Implemented as a plain context manager rather than a fixture
    because httpx_ws's ASGIWebSocketTransport uses anyio cancel scopes that
    must be entered/exited in the *same* asyncio task -- pytest-asyncio runs
    async-generator-fixture teardown in a separate finalizer task, which
    trips that constraint. Using it directly inside a test function keeps
    enter/exit in one task.
    """

    async def __aenter__(self):
        from app.services.environmental_pipeline import environmental_pipeline_registry
        from app.services.prediction import prediction_registry
        from app.realtime.websocket import manager
        from httpx_ws.transport import ASGIWebSocketTransport

        self._prediction_registry = prediction_registry
        self._environmental_pipeline_registry = environmental_pipeline_registry
        self._manager = manager

        await prediction_registry.startup()
        app.state.prediction_registry = prediction_registry
        await environmental_pipeline_registry.startup()
        app.state.environmental_pipeline = environmental_pipeline_registry.pipeline

        await redis_bus.connect()
        await manager.start_redis_listener()

        transport = ASGIWebSocketTransport(app=app)
        self._client = AsyncClient(transport=transport, base_url="http://test")
        return await self._client.__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        await self._client.__aexit__(exc_type, exc, tb)
        await self._manager.stop_redis_listener()
        await redis_bus.disconnect()
        await self._prediction_registry.shutdown()
        await self._environmental_pipeline_registry.shutdown()
