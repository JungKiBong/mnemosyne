import os
import logging
from app import create_app
from app.storage.neo4j_storage import Neo4jStorage
from app.services.ingestion_service import DataIngestionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ingest")

def main():
    # Use app context so config is loaded correctly
    app = create_app()
    with app.app_context():
        logger.info("Starting ingestion test for TurboQuant...")
        
        # Initialize storage
        storage = app.extensions.get('neo4j_storage')
        if not storage:
            logger.error("Storage not initialized.")
            return

        # Initialize DataIngestionService
        ingestion_service = DataIngestionService(storage=storage)
        
        # Provide path to the PDF
        source_ref = os.path.abspath("data/ingest/turboquant.pdf")
        graph_id = "turboquant"
        
        logger.info(f"Ingesting {source_ref} into graph {graph_id}...")
        
        try:
            result = ingestion_service.ingest(graph_id=graph_id, source_ref=source_ref)
            logger.info("Ingestion completed successfully.")
            logger.info(f"Result: {result}")
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")

if __name__ == "__main__":
    main()
