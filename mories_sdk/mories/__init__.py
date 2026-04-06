"""
Mories SDK — Python Client for the Mories Cognitive Engine.

Provides MoriesClient for direct REST API access, and MoriesRetriever
for LangChain integration (optional dependency).
"""

from .client import MoriesClient, AsyncMoriesClient

__version__ = "0.1.0"
__all__ = ["MoriesClient", "AsyncMoriesClient"]

# Lazy-import LangChain integration to avoid hard dependency
try:
    from .langchain import MoriesRetriever
    __all__.append("MoriesRetriever")
except Exception:
    pass
