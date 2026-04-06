def test_rate_limit_on_batch_endpoint(client):
    """
    Test that the /api/ingest/batch/async endpoint enforces the 10 per minute rate limit.
    """
    # Send 12 requests quickly to the batch async endpoint
    responses = []
    
    # Payload for batch async
    payload = {
        "files": ["file1.txt"]  # minimal payload
    }
    
    for _ in range(12):
        resp = client.post("/api/v1/ingest/batch/async", json=payload)
        responses.append(resp.status_code)

    # The first 10 should be 202 (Accepted) or 400 (Bad Request), but anyway not 429
    # Actually, without the full file body, it returns 400, which is fine.
    # We just want to check if the 11th or 12th request hits the 429 Too Many Requests limit.
    
    # We expect at least one 429
    assert 429 in responses, f"Expected 429 Too Many Requests, got {responses}"
