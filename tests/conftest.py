"""
conftest.py — Unregister Prometheus collectors before tests
to avoid "Duplicated timeseries" errors from src.app.__init__.py
"""
import pytest


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
