import subprocess
import time
from typing import AsyncGenerator, Generator

import pytest
import httpx


@pytest.fixture(scope="session")
def mockoon_server() -> Generator[str, None, None]:
    process = None
    try:
        process = subprocess.Popen(
            ["mockoon-cli", "start", "--data", "tests/mocks/trackguard-mocks.json", "--port", "3333"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(2)
        yield "http://localhost:3333"
    except FileNotFoundError:
        pytest.skip("mockoon-cli is not installed")
    except Exception as e:
        pytest.skip(f"Failed to start mockoon-cli: {e}")
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture
async def httpx_client(mockoon_server: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=mockoon_server) as client:
        yield client