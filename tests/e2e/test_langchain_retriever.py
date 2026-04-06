import pytest
from unittest.mock import MagicMock

try:
    from langchain_core.documents import Document
    from mories.langchain import MoriesRetriever, _HAS_LANGCHAIN
except ImportError:
    _HAS_LANGCHAIN = False

@pytest.mark.skipif(not _HAS_LANGCHAIN, reason="langchain-core not installed")
class TestMoriesRetriever:
    
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.search.return_value = {
            "results": [
                {"content": "First result body", "uuid": "u1", "score": 0.9},
                {"content": "Second result body", "uuid": "u2", "score": 0.5}
            ]
        }
        return client

    def test_retriever_initialization(self, mock_client):
        retriever = MoriesRetriever(client=mock_client, limit=5, graph_id="g1")
        assert retriever.limit == 5
        assert retriever.graph_id == "g1"

    def test_get_relevant_documents(self, mock_client):
        retriever = MoriesRetriever(client=mock_client, limit=2)
        
        # Test document conversion
        docs = retriever.invoke("test query")
        assert len(docs) == 2
        assert isinstance(docs[0], Document)
        assert docs[0].page_content == "First result body"
        assert docs[0].metadata["uuid"] == "u1"
        assert docs[0].metadata["score"] == 0.9

        # Verify client params
        mock_client.search.assert_called_once_with(query="test query", limit=2, graph_id="")

    def test_empty_results(self, mock_client):
        mock_client.search.return_value = {"results": []}
        retriever = MoriesRetriever(client=mock_client)
        
        docs = retriever.invoke("empty query")
        assert len(docs) == 0

    def test_fallback_entities_key(self, mock_client):
        # Mories sometimes returns "entities" instead of "results"
        mock_client.search.return_value = {
            "entities": [
                {"content": "entity 1", "type": "Person"}
            ]
        }
        retriever = MoriesRetriever(client=mock_client)
        docs = retriever.invoke("entity query")
        
        assert len(docs) == 1
        assert docs[0].page_content == "entity 1"
        assert docs[0].metadata["type"] == "Person"

    def test_missing_content(self, mock_client):
        # Result dict doesn't have 'content', should fallback to str representation
        mock_client.search.return_value = {
            "results": [
                {"uuid": "u3", "fact": "Something happened"}
            ]
        }
        retriever = MoriesRetriever(client=mock_client)
        docs = retriever.invoke("missing content")
        
        assert len(docs) == 1
        # The fallback is str(res), which will be the string dict
        assert "Something happened" in docs[0].page_content
        assert docs[0].metadata["uuid"] == "u3"
