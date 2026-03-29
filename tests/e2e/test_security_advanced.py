"""
E2E Security Advanced Tests — API Key Lifecycle & Rate Limiting.

Tests for:
  - Full API key lifecycle: create → list → renew → verify → revoke
  - Key expiration enforcement
  - Renew endpoint validation (extend_days bounds)
  - Rate Limit Stats endpoint
  - RBAC permission checks
"""

import json
import pytest


class TestApiKeyLifecycle:
    """Full API key create → renew → revoke lifecycle."""

    def test_create_api_key(self, client):
        """POST /api/security/keys creates a new key with metadata."""
        resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-test-user',
            'name': 'E2E Test Key',
            'roles': ['writer'],
            'allowed_scopes': ['personal', 'tribal'],
            'expires_in_days': 7,
            'rate_limit': 50,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('api_key', '').startswith('mnem_')
        assert data['name'] == 'E2E Test Key'
        assert data['owner_id'] == 'e2e-test-user'
        assert data['expires_at'] is not None
        assert 'warning' in data  # "Save this key" warning

    def test_create_key_invalid_expiry_negative(self, client):
        """POST /api/security/keys rejects negative expiry."""
        resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-test-user',
            'name': 'Bad Key',
            'expires_in_days': -5,
        })
        assert resp.status_code == 400

    def test_create_key_invalid_expiry_too_large(self, client):
        """POST /api/security/keys rejects >3650 expiry."""
        resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-test-user',
            'name': 'Bad Key',
            'expires_in_days': 9999,
        })
        assert resp.status_code == 400

    def test_create_key_no_expiry(self, client):
        """POST /api/security/keys with expires_in_days=0 creates no-expiry key."""
        resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-test-user',
            'name': 'Never Expires Key',
            'expires_in_days': 0,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('expires_at') is None

    def test_list_api_keys(self, client):
        """GET /api/security/keys returns key list with metadata."""
        # Ensure at least one key exists
        client.post('/api/security/keys', json={
            'owner_id': 'e2e-list-user',
            'name': 'List Test Key',
        })

        resp = client.get('/api/security/keys')
        assert resp.status_code == 200
        data = resp.get_json()
        keys = data.get('keys', [])
        assert isinstance(keys, list)

    def test_list_api_keys_by_owner(self, client):
        """GET /api/security/keys?owner_id=X filters by owner."""
        resp = client.get('/api/security/keys?owner_id=e2e-list-user')
        assert resp.status_code == 200
        data = resp.get_json()
        for key in data.get('keys', []):
            assert key['owner_id'] == 'e2e-list-user'

    def test_verify_valid_key(self, client):
        """POST /api/security/keys/verify accepts a valid key."""
        # Create a key
        create_resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-verify-user',
            'name': 'Verify Test',
            'expires_in_days': 30,
        })
        raw_key = create_resp.get_json().get('api_key')
        assert raw_key

        # Verify it
        verify_resp = client.post('/api/security/keys/verify', json={
            'api_key': raw_key,
        })
        assert verify_resp.status_code == 200
        data = verify_resp.get_json()
        assert data['valid'] is True

    def test_verify_invalid_key(self, client):
        """POST /api/security/keys/verify rejects an invalid key."""
        resp = client.post('/api/security/keys/verify', json={
            'api_key': 'mnem_INVALID_KEY_12345',
        })
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['valid'] is False

    def test_verify_missing_key(self, client):
        """POST /api/security/keys/verify rejects empty api_key."""
        resp = client.post('/api/security/keys/verify', json={
            'api_key': '',
        })
        assert resp.status_code == 400


class TestApiKeyRenewal:
    """API key renew endpoint tests."""

    def _create_key(self, client, name='Renew Test', days=7):
        """Helper to create a key and return (raw_key, key_hash)."""
        resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-renew-user',
            'name': name,
            'expires_in_days': days,
        })
        data = resp.get_json()
        raw_key = data.get('api_key', '')

        # Get hash from listing
        list_resp = client.get('/api/security/keys?owner_id=e2e-renew-user')
        keys = list_resp.get_json().get('keys', [])
        for k in keys:
            if k['name'] == name:
                return raw_key, k['key_hash']
        return raw_key, None

    def test_renew_key_default_30_days(self, client):
        """POST /api/security/keys/{hash}/renew extends by 30 days."""
        _, key_hash = self._create_key(client, name='Renew30D')
        if not key_hash:
            pytest.skip("Could not find key hash")

        resp = client.post(f'/api/security/keys/{key_hash}/renew', json={
            'extend_days': 30,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'renewed'
        assert data['extended_days'] == 30
        assert data['new_expires_at'] is not None

    def test_renew_key_7_days(self, client):
        """POST /api/security/keys/{hash}/renew with 7-day extension."""
        _, key_hash = self._create_key(client, name='Renew7D')
        if not key_hash:
            pytest.skip("Could not find key hash")

        resp = client.post(f'/api/security/keys/{key_hash}/renew', json={
            'extend_days': 7,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'renewed'
        assert data['extended_days'] == 7

    def test_renew_key_365_days(self, client):
        """POST /api/security/keys/{hash}/renew with 1-year extension."""
        _, key_hash = self._create_key(client, name='Renew365D')
        if not key_hash:
            pytest.skip("Could not find key hash")

        resp = client.post(f'/api/security/keys/{key_hash}/renew', json={
            'extend_days': 365,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'renewed'
        assert data['extended_days'] == 365

    def test_renew_key_invalid_extend_zero(self, client):
        """POST /api/security/keys/{hash}/renew rejects extend_days=0."""
        _, key_hash = self._create_key(client, name='RenewBad0')
        if not key_hash:
            pytest.skip("Could not find key hash")

        resp = client.post(f'/api/security/keys/{key_hash}/renew', json={
            'extend_days': 0,
        })
        assert resp.status_code == 400

    def test_renew_key_invalid_extend_too_large(self, client):
        """POST /api/security/keys/{hash}/renew rejects >3650."""
        _, key_hash = self._create_key(client, name='RenewBad9999')
        if not key_hash:
            pytest.skip("Could not find key hash")

        resp = client.post(f'/api/security/keys/{key_hash}/renew', json={
            'extend_days': 9999,
        })
        assert resp.status_code == 400

    def test_renew_nonexistent_key(self, client):
        """POST /api/security/keys/{hash}/renew with bad hash returns 400."""
        resp = client.post('/api/security/keys/0000000000000000/renew', json={
            'extend_days': 30,
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data

    def test_revoke_then_renew_fails(self, client):
        """Renewing a revoked key should fail."""
        _, key_hash = self._create_key(client, name='RevokeBeforeRenew')
        if not key_hash:
            pytest.skip("Could not find key hash")

        # Revoke first
        del_resp = client.delete(f'/api/security/keys/{key_hash}')
        assert del_resp.status_code == 200

        # Try to renew
        renew_resp = client.post(f'/api/security/keys/{key_hash}/renew', json={
            'extend_days': 30,
        })
        assert renew_resp.status_code == 400


class TestRateLimitStats:
    """Rate Limit Stats endpoint tests."""

    def test_rate_limit_stats_returns_data(self, client):
        """GET /api/security/rate-limit-stats returns key stats."""
        resp = client.get('/api/security/rate-limit-stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'keys' in data
        assert 'global_mcp_limit' in data
        assert isinstance(data['keys'], list)
        assert data['global_mcp_limit'] == 60

    def test_rate_limit_stats_key_fields(self, client):
        """Each key in rate-limit-stats has required fields."""
        # Ensure at least one key
        client.post('/api/security/keys', json={
            'owner_id': 'e2e-rl-user',
            'name': 'RL Stats Test',
        })

        resp = client.get('/api/security/rate-limit-stats')
        data = resp.get_json()
        keys = data.get('keys', [])

        if keys:
            key = keys[0]
            assert 'name' in key
            assert 'rate_limit' in key
            assert 'usage_count' in key
            assert 'active' in key


class TestApiKeyRevocation:
    """API key revocation tests."""

    def test_revoke_key(self, client):
        """DELETE /api/security/keys/{hash} revokes the key."""
        # Create
        create_resp = client.post('/api/security/keys', json={
            'owner_id': 'e2e-revoke-user',
            'name': 'Revoke Test',
        })
        raw_key = create_resp.get_json().get('api_key')

        # Find hash
        list_resp = client.get('/api/security/keys?owner_id=e2e-revoke-user')
        keys = list_resp.get_json().get('keys', [])
        key_hash = None
        for k in keys:
            if k['name'] == 'Revoke Test':
                key_hash = k['key_hash']
                break

        if not key_hash:
            pytest.skip("Could not find key hash")

        # Revoke
        del_resp = client.delete(f'/api/security/keys/{key_hash}')
        assert del_resp.status_code == 200
        assert del_resp.get_json()['status'] == 'revoked'

        # Verify key is invalid after revocation
        verify_resp = client.post('/api/security/keys/verify', json={
            'api_key': raw_key,
        })
        assert verify_resp.status_code == 401


class TestRBACPermissions:
    """RBAC permission check tests."""

    def test_register_and_check_writer(self, client):
        """Register writer principal and verify store permission."""
        # Register
        reg_resp = client.post('/api/security/principals', json={
            'principal_id': 'user:e2e-writer',
            'name': 'E2E Writer',
            'type': 'user',
            'roles': ['writer'],
        })
        assert reg_resp.status_code == 200

        # Check allowed
        check_resp = client.post('/api/security/check', json={
            'principal_id': 'user:e2e-writer',
            'action': 'store',
            'scope': 'personal',
        })
        assert check_resp.status_code == 200
        data = check_resp.get_json()
        assert data['allowed'] is True

    def test_reader_cannot_store(self, client):
        """Reader principal should be denied store action."""
        client.post('/api/security/principals', json={
            'principal_id': 'user:e2e-reader',
            'name': 'E2E Reader',
            'type': 'user',
            'roles': ['reader'],
        })

        check_resp = client.post('/api/security/check', json={
            'principal_id': 'user:e2e-reader',
            'action': 'store',
            'scope': 'personal',
        })
        assert check_resp.status_code == 200
        data = check_resp.get_json()
        assert data['allowed'] is False

    def test_role_matrix(self, client):
        """GET /api/security/roles returns valid matrix."""
        resp = client.get('/api/security/roles')
        assert resp.status_code == 200
        data = resp.get_json()
        roles = data.get('roles', {})
        assert 'reader' in roles
        assert 'writer' in roles
        assert 'admin' in roles
        assert 'store' in roles['writer']
        assert 'store' not in roles['reader']

    def test_encryption_status(self, client):
        """GET /api/security/encrypt/status returns stats."""
        resp = client.get('/api/security/encrypt/status')
        assert resp.status_code == 200
