"""Tests for Graphiti with Google embeddings."""
import pytest
import os
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault('GOOGLE_API_KEY', os.environ.get('GOOGLE_API_KEY', ''))
os.environ.setdefault('OPENAI_API_KEY', os.environ.get('OPENAI_API_KEY', ''))
os.environ.setdefault('OPENAI_BASE_URL', os.environ.get('OPENAI_BASE_URL', 'https://ollama.com/v1'))


def _neo4j_reachable() -> bool:
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    parsed = urlparse(uri)
    host = parsed.hostname or 'localhost'
    port = parsed.port or 7687
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _require_graphiti_environment() -> None:
    if not os.environ.get('GOOGLE_API_KEY'):
        pytest.skip("GOOGLE_API_KEY not set")
    if not _neo4j_reachable():
        pytest.skip("Neo4j not reachable at configured NEO4J_URI")


def test_graphiti_available_returns_true():
    """Graphiti should be available with Google embeddings."""
    _require_graphiti_environment()
    
    from src.memory.semantic import SemanticMemory
    sm = SemanticMemory(tenant_id='test-tenant')
    assert sm.available() is True, "Graphiti should be available"


def test_graphiti_write_and_search():
    """Write episode then search should work."""
    _require_graphiti_environment()
    
    from src.memory.semantic import SemanticMemory
    sm = SemanticMemory(tenant_id='test-tenant')

    write_result = sm.write_episode('test-1', 'Founder prefers growth.')
    assert write_result is True

    results = sm.search('growth strategy', num_results=5)
    assert isinstance(results, list)