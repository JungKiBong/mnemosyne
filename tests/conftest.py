"""
conftest.py — Unregister Prometheus collectors before tests
to avoid "Duplicated timeseries" errors from src.app.__init__.py
"""
import pytest
from src.app import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture(autouse=True, scope="session")
def clear_prometheus_registry():
    """Clear Prometheus CollectorRegistry to avoid duplicated metrics errors."""
    try:
        from prometheus_client import REGISTRY
        collectors = list(REGISTRY._names_to_collectors.values())
        for collector in set(collectors):
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except ImportError:
        pass
    yield
