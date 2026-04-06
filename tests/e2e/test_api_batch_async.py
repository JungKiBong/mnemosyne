import time
import pytest

class TestBatchIngestionAsyncAPI:
    """Async Batch Ingestion API endpoints tests."""

    def test_batch_async_lifecycle(self, client):
        """POST /api/ingest/batch/async returns job_id and GET /status tracks progress."""
        # 1. Start an asynchronous batch ingestion
        resp = client.post('/api/v1/ingest/batch/async', json={
            'graph_id': 'default',
            'source_refs': ['dummy_source_1.txt', 'dummy_source_2.txt'],
            'options': {}
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert 'job_id' in data
        assert data['status'] == 'queued'
        job_id = data['job_id']

        # 2. Check the status immediately
        status_resp = client.get(f'/api/v1/ingest/batch/status/{job_id}')
        assert status_resp.status_code == 200
        status_data = status_resp.get_json()
        assert status_data['job_id'] == job_id
        assert status_data['total'] == 2
        assert status_data['status'] in ('queued', 'processing', 'completed')

        # 3. Wait a moment for the threads to potentially process the items
        for _ in range(10):
            time.sleep(0.5)
            status_resp = client.get(f'/api/v1/ingest/batch/status/{job_id}')
            if status_resp.get_json()['status'] == 'completed':
                break
        
        final_data = client.get(f'/api/v1/ingest/batch/status/{job_id}').get_json()
        assert final_data['status'] == 'completed'
        assert final_data['completed'] + final_data['failed'] == 2
