def test_correlation_id_in_response(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert 'X-Correlation-ID' in response.headers

def test_prometheus_metrics_endpoint(client):
    response = client.get('/metrics')
    assert response.status_code == 200
    metrics_text = response.data.decode('utf-8')
    assert 'http_requests_total' in metrics_text
    
    # Trigger a neo4j operation to ensure neo4j metrics appear
    client.get('/api/analytics/salience_trend')
    response2 = client.get('/metrics')
    metrics_text2 = response2.data.decode('utf-8')
    assert 'neo4j_query_duration_seconds' in metrics_text2
def test_salience_trend_endpoint(client):
    response = client.get('/api/analytics/salience_trend')
    assert response.status_code == 200
    data = response.get_json()
    assert 'trend_data' in data
    assert isinstance(data['trend_data'], list)
