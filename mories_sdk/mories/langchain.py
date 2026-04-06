"""
LangChain Retriever integration for the Mories Cognitive Engine.

Requires: langchain-core >= 0.2
"""

from __future__ import annotations

from typing import List, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import MoriesClient

try:
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.documents import Document
    from pydantic import ConfigDict

    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False


if _HAS_LANGCHAIN:

    class MoriesRetriever(BaseRetriever):
        """
        LangChain Retriever backed by Mories search API.

        Example:
            client = MoriesClient(base_url="http://localhost:5001")
            retriever = MoriesRetriever(client=client, limit=5)
            docs = retriever.invoke("harness architecture")
        """

        model_config = ConfigDict(arbitrary_types_allowed=True)

        client: Any
        limit: int = 10
        graph_id: str = ""

        def _get_relevant_documents(
            self, query: str, *, run_manager: CallbackManagerForRetrieverRun
        ) -> List[Document]:
            from .client import MoriesClient  # resolve forward ref at runtime

            response = self.client.search(
                query=query, limit=self.limit, graph_id=self.graph_id
            )

            results = response.get("results", response.get("entities", []))

            docs = []
            for res in results:
                content = res.get("content", str(res))
                metadata = {k: v for k, v in res.items() if k != "content"}
                docs.append(Document(page_content=content, metadata=metadata))

            return docs

else:
    # Provide a placeholder so `from mories.langchain import MoriesRetriever`
    # does not crash; it raises at instantiation time instead.
    class MoriesRetriever:  # type: ignore[no-redef]
        """Stub — install langchain-core to use this retriever."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "langchain-core is required for MoriesRetriever. "
                "Install with: pip install langchain-core"
            )
