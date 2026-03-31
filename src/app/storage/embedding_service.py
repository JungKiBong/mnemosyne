"""
EmbeddingService — Multi-provider embedding generation.

Supports:
  - Ollama:  /api/embed  (default, local)
  - OpenAI:  /v1/embeddings  (text-embedding-3-small, ada-002)
  - vLLM:    /v1/embeddings  (vLLM OpenAI-compatible)
  - Custom:  Any OpenAI-compatible /v1/embeddings endpoint
"""

import os
import time
import logging
import threading
from typing import List, Optional
import requests

from ..config import Config

logger = logging.getLogger('mirofish.embedding')


class EmbeddingService:
    """Generate embeddings using multiple providers."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.model = model or Config.EMBEDDING_MODEL
        self.base_url = (base_url or Config.EMBEDDING_BASE_URL).rstrip('/')
        self.provider = (provider or os.environ.get('EMBEDDING_PROVIDER', 'auto')).lower()
        self.max_retries = max_retries
        self.timeout = timeout

        # Auto-detect provider from base_url if not explicitly set
        if self.provider == 'auto':
            self.provider = self._detect_provider()

        # Build endpoint URL based on provider
        if self.provider == 'ollama':
            self._embed_url = f"{self.base_url}/api/embed"
        else:
            # OpenAI-compatible: openai, vllm, azure, together, etc.
            self._embed_url = f"{self.base_url}/v1/embeddings"

        # API key (needed for non-Ollama providers)
        self._api_key = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY', '')

        # In-memory cache with thread-safety lock
        self._cache: dict[str, List[float]] = {}
        self._cache_lock = threading.Lock()
        self._cache_max_size = 2000

    def _detect_provider(self) -> str:
        """Auto-detect provider from base_url."""
        url = self.base_url.lower()
        if '11434' in url or 'ollama' in url:
            return 'ollama'
        elif 'openai.com' in url:
            return 'openai'
        else:
            # Default: OpenAI-compatible for any other URL (vLLM, LM Studio, etc.)
            return 'openai'

    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        text = text.strip()

        # Check cache (thread-safe)
        with self._cache_lock:
            cached = self._cache.get(text)
        if cached is not None:
            return cached

        vectors = self._request_embeddings([text])
        vector = vectors[0]
        self._cache_put(text, vector)
        return vector

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for i, text in enumerate(texts):
            text = text.strip() if text else ""
            with self._cache_lock:
                cached = self._cache.get(text)
            if cached is not None:
                results[i] = cached
            elif text:
                uncached_indices.append(i)
                uncached_texts.append(text)
            else:
                results[i] = [0.0] * self._default_dim()

        if uncached_texts:
            all_vectors: List[List[float]] = []
            for start in range(0, len(uncached_texts), batch_size):
                batch = uncached_texts[start:start + batch_size]
                vectors = self._request_embeddings(batch)
                all_vectors.extend(vectors)

            for idx, vec, text in zip(uncached_indices, all_vectors, uncached_texts):
                results[idx] = vec
                self._cache_put(text, vec)

        return results  # type: ignore

    def _default_dim(self) -> int:
        """Default embedding dimension based on model."""
        model_lower = self.model.lower()
        if 'nomic' in model_lower:
            return 768
        elif 'minilm' in model_lower:
            return 384
        elif 'bge-m3' in model_lower:
            return 1024
        elif 'bge-large' in model_lower:
            return 1024
        elif 'text-embedding-3-small' in model_lower:
            return 1536
        elif 'text-embedding-3-large' in model_lower:
            return 3072
        elif 'ada' in model_lower:
            return 1536
        return 768

    def _request_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Route to the correct provider implementation."""
        if self.provider == 'ollama':
            return self._request_ollama(texts)
        else:
            return self._request_openai_compat(texts)

    def _request_ollama(self, texts: List[str]) -> List[List[float]]:
        """Ollama /api/embed endpoint."""
        payload = {"model": self.model, "input": texts}

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self._embed_url, json=payload, timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                embeddings = data.get("embeddings", [])
                if len(embeddings) != len(texts):
                    raise EmbeddingError(
                        f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                    )
                return embeddings

            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"Ollama connection failed (attempt {attempt + 1}/{self.max_retries}): {e}")
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"Ollama request timed out (attempt {attempt + 1}/{self.max_retries})")
            except requests.exceptions.HTTPError as e:
                last_error = e
                logger.error(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")
                if e.response.status_code < 500:
                    raise EmbeddingError(f"Ollama embedding failed: {e}") from e
            except (KeyError, ValueError) as e:
                raise EmbeddingError(f"Invalid Ollama response: {e}") from e

            if attempt < self.max_retries - 1:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise EmbeddingError(f"Ollama embedding failed after {self.max_retries} retries: {last_error}")

    def _request_openai_compat(self, texts: List[str]) -> List[List[float]]:
        """OpenAI-compatible /v1/embeddings endpoint (OpenAI, vLLM, Azure, etc.)."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {"model": self.model, "input": texts}

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self._embed_url, json=payload, headers=headers, timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

                # OpenAI format: {"data": [{"embedding": [...], "index": 0}, ...]}
                embedding_data = data.get("data", [])
                if len(embedding_data) != len(texts):
                    raise EmbeddingError(
                        f"Expected {len(texts)} embeddings, got {len(embedding_data)}"
                    )

                # Sort by index to ensure correct order
                sorted_data = sorted(embedding_data, key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in sorted_data]

            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"Embedding connection failed (attempt {attempt + 1}/{self.max_retries}): {e}")
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"Embedding request timed out (attempt {attempt + 1}/{self.max_retries})")
            except requests.exceptions.HTTPError as e:
                last_error = e
                logger.error(f"Embedding HTTP error: {e.response.status_code} - {e.response.text}")
                if e.response.status_code < 500:
                    raise EmbeddingError(f"Embedding failed: {e}") from e
            except (KeyError, ValueError) as e:
                raise EmbeddingError(f"Invalid embedding response: {e}") from e

            if attempt < self.max_retries - 1:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise EmbeddingError(f"Embedding failed after {self.max_retries} retries: {last_error}")

    def _cache_put(self, text: str, vector: List[float]) -> None:
        """Add to cache, evicting oldest entries if full (thread-safe)."""
        with self._cache_lock:
            if len(self._cache) >= self._cache_max_size:
                keys_to_remove = list(self._cache.keys())[:self._cache_max_size // 10]
                for key in keys_to_remove:
                    del self._cache[key]
            self._cache[text] = vector

    def health_check(self) -> bool:
        """Check if embedding endpoint is reachable."""
        try:
            vec = self.embed("health check")
            return len(vec) > 0
        except Exception:
            return False


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass
