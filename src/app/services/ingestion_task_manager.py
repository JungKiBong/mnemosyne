"""
Ingestion Task Manager

Manages background asynchronous batch tasks.
Tracks status via an in-memory dictionary.
Leverages ThreadPoolExecutor for concurrent execution of memory injections.
Emits events to the WebhookPublisher (Harness Architecture) upon start and completion.
"""
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List
from .ingestion_service import DataIngestionService
from ..utils.webhook import get_webhook

logger = logging.getLogger(__name__)

class IngestionTaskManager:
    """Manages asynchronous batch ingestion jobs."""
    _instance = None

    def __init__(self, svc: DataIngestionService, max_workers: int = 4):
        self.svc = svc
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="BatchWorker")
        # In-memory store for tracking job states
        self.jobs: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls, svc: DataIngestionService) -> 'IngestionTaskManager':
        """Singleton pattern for managing the shared thread pool and state."""
        if cls._instance is None:
            cls._instance = cls(svc)
        return cls._instance

    def submit_batch(self, graph_id: str, source_refs: List[str], options: dict) -> str:
        """Submit a batch of files/sources to be ingested asynchronously."""
        job_id = f"batch-{uuid.uuid4().hex[:12]}"
        self.jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "total": len(source_refs),
            "completed": 0,
            "failed": 0,
            "current": None
        }
        
        # Fire Harness Webhook
        get_webhook().batch_started(job_id, len(source_refs))

        # Submit task to the thread pool
        self.executor.submit(self._process_batch, job_id, graph_id, source_refs, options)
        return job_id

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """Fetch the current status of a submitted job."""
        if job_id not in self.jobs:
            return {"error": "Job not found"}
        return self.jobs[job_id]

    def _process_batch(self, job_id: str, graph_id: str, source_refs: List[str], options: dict):
        """Worker function that processes sources sequentially in its reserved thread."""
        job = self.jobs[job_id]
        job["status"] = "processing"
        
        for ref in source_refs:
            job["current"] = ref
            try:
                # Reuse the existing one-shot ingestion method
                self.svc.ingest(graph_id, ref, **options)
                job["completed"] += 1
            except Exception as e:
                logger.error("Batch %s failed on %s: %s", job_id, ref, e, exc_info=True)
                job["failed"] += 1
                
        job["status"] = "completed"
        job["current"] = None
        logger.info("Batch %s finished. Total: %d, Completed: %d, Failed: %d", 
                    job_id, job["total"], job["completed"], job["failed"])
        
        # Fire Harness Webhook
        get_webhook().batch_completed(job_id, job["completed"], job["failed"])
