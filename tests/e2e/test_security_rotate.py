from src.app.security.memory_encryption import get_encryption

def test_key_rotation_dry_run(client):
    """Test that key rotation without execute=True just returns a plan."""
    response = client.post('/api/admin/security/rotate', json={})
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'key_rotation_planned'
    assert 'warning' in data
    assert 'memories_to_rotate' in data

def test_key_rotation_execute_empty(client):
    """Test key rotation with execute=True when there are no encrypted memories."""
    response = client.post('/api/admin/security/rotate', json={'execute': True})
    assert response.status_code == 200
    data = response.get_json()
    # It should either rotate 0 memories, or return no_memories_to_rotate
    assert data['status'] in ['no_memories_to_rotate', 'key_rotation_completed']
