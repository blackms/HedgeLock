"""Shared pytest fixtures and configuration."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
from httpx import AsyncClient


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        yield client
