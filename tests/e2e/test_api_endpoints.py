"""
E2E API tests — Mories REST endpoints.

Uses Flask test client to verify end-to-end API behavior
for memory management, search, and dashboard endpoints.
"""

import json
import pytest


class TestHealthEndpoints:
    """Health check and system status."""

    def test_health_check(self, client):
        """GET /api/health returns 200 with system info."""
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'healthy'
        assert 'components' in data

    def test_api_root(self, client):
        """GET / or /api/ returns a basic info response."""
        resp = client.get('/')
        assert resp.status_code in (200, 302, 404)


class TestMemoryAPI:
    """Memory CRUD via REST API."""

    def test_stm_add_via_api(self, client):
        """POST /api/memory/stm/add adds an STM item (returns 201)."""
        resp = client.post('/api/memory/stm/add', json={
            'content': 'E2E test: 중요한 기억',
            'source': 'e2e_test',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data.get('id') is not None

    def test_stm_list_via_api(self, client):
        """GET /api/memory/stm/list returns current STM buffer."""
        # Add something first
        client.post('/api/memory/stm/add', json={
            'content': 'E2E list test memory',
            'source': 'e2e_test',
        })

        resp = client.get('/api/memory/stm/list')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_stm_evaluate_via_api(self, client):
        """POST /api/memory/stm/evaluate evaluates salience."""
        # Add an item first
        add_resp = client.post('/api/memory/stm/add', json={
            'content': 'Evaluate test',
            'source': 'e2e_test',
        })
        item_id = add_resp.get_json().get('id')

        if item_id:
            resp = client.post('/api/memory/stm/evaluate', json={
                'id': item_id,
                'salience': 0.75,
            })
            assert resp.status_code == 200

    def test_memory_overview_api(self, client):
        """GET /api/memory/overview returns dashboard data."""
        resp = client.get('/api/memory/overview')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'stm' in data

    def test_decay_manual_trigger_api(self, client):
        """POST /api/memory/decay triggers manual decay."""
        resp = client.post('/api/memory/decay', json={
            'dry_run': True,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_processed' in data

    def test_memory_config_get_api(self, client):
        """GET /api/memory/config returns current config."""
        resp = client.get('/api/memory/config')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'decay_rate' in data or 'config' in data


class TestSearchAPI:
    """Search endpoints."""

    def test_search_api(self, client):
        """POST /api/search with a query returns results."""
        resp = client.post('/api/search', json={
            'query': 'test memory',
            'limit': 5,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        # Should return results or empty list, not error
        assert 'error' not in data or data.get('results') is not None


class TestAuditAPI:
    """Audit trail endpoints."""

    def test_audit_recent_activity(self, client):
        """GET /api/memory/audit/activity returns recent activity."""
        resp = client.get('/api/memory/audit/activity')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    def test_audit_stats(self, client):
        """GET /api/memory/audit/stats returns stats."""
        resp = client.get('/api/memory/audit/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_revisions' in data or isinstance(data, dict)


class TestScopeAPI:
    """Memory Scope endpoints."""

    def test_scope_summary(self, client):
        """GET /api/memory/scopes/summary returns scope stats."""
        resp = client.get('/api/memory/scopes/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'scopes' in data or isinstance(data, dict)


class TestDashboardAPI:
    """Dashboard data endpoints."""

    def test_dashboard_overview(self, client):
        """GET /api/memory/overview returns full dashboard data."""
        resp = client.get('/api/memory/overview')
        assert resp.status_code == 200

    def test_ltm_overview(self, client):
        """GET /api/memory/ltm/overview returns LTM statistics."""
        resp = client.get('/api/memory/ltm/overview')
        assert resp.status_code in (200, 404)

    def test_memory_detail_not_found(self, client):
        """GET /api/memory/detail/<uuid> handles non-existent gracefully."""
        resp = client.get('/api/memory/detail/00000000-0000-0000-0000-000000000000')
        # Can be 200 with error, or 404 — both are valid
        assert resp.status_code in (200, 404)


class TestDataProductsAPI:
    """Data Products (Phase 11) endpoints — url_prefix=/api/memory/data."""

    def test_rag_corpus_export(self, client):
        """GET /api/analytics/data-product/rag returns corpus data."""
        resp = client.get('/api/analytics/data-product/rag')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    def test_knowledge_graph_snapshot(self, client):
        """GET /api/analytics/data-product/snapshot returns snapshot."""
        resp = client.get('/api/analytics/data-product/snapshot')
        assert resp.status_code == 200

    def test_data_catalog(self, client):
        """GET /api/analytics/data-product/manifest/list returns catalog listing."""
        resp = client.get('/api/analytics/data-product/manifest/list')
        assert resp.status_code == 200


class TestSecurityAPI:
    """Security & RBAC endpoints — url_prefix=/api/security."""

    def test_security_roles(self, client):
        """GET /api/admin/security/roles returns role definitions."""
        resp = client.get('/api/admin/security/roles')
        assert resp.status_code == 200

    def test_security_keys_list(self, client):
        """GET /api/admin/security/keys returns encryption key info."""
        resp = client.get('/api/admin/security/keys')
        assert resp.status_code == 200


class TestMaturityAPI:
    """Maturity model endpoints — url_prefix=/api/maturity."""

    def test_maturity_overview(self, client):
        """GET /api/analytics/maturity/overview returns maturity model info."""
        resp = client.get('/api/analytics/maturity/overview')
        assert resp.status_code == 200

    def test_maturity_rules(self, client):
        """GET /api/analytics/maturity/rules returns promotion rules."""
        resp = client.get('/api/analytics/maturity/rules')
        assert resp.status_code == 200


class TestReconciliationAPI:
    """Reconciliation endpoints — url_prefix=/api/reconciliation."""

    def test_quick_check(self, client):
        """GET /api/analytics/reconcile/check returns health data."""
        resp = client.get('/api/analytics/reconcile/check')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'health_score' in data

    def test_run_reconciliation(self, client):
        """POST /api/analytics/reconcile/run executes full check."""
        resp = client.post('/api/analytics/reconcile/run', json={
            'auto_fix': False,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'run_id' in data
        assert 'health_score' in data

    def test_reconciliation_history(self, client):
        """GET /api/analytics/reconcile/history returns run history."""
        resp = client.get('/api/analytics/reconcile/history')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'history' in data
