"""
tests/e2e/conftest.py - E2E Testing Fixtures

Provides mocked auth dependencies and realistic Keycloak token generation for E2E scenarios.
"""
import pytest
import jwt
from unittest.mock import patch

@pytest.fixture(scope="session")
def mock_jwt_keys():
    """Generates a temporary RSA key pair for creating valid mock RS256 JWT tokens."""
    import cryptography.hazmat.primitives.asymmetric.rsa as rsa
    from cryptography.hazmat.primitives import serialization
    
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem_private, pem_public

@pytest.fixture(scope="session")
def mock_jwks_client_class(mock_jwt_keys):
    """Mocks the internal PyJWKClient to return our temporary public key."""
    _, pem_public = mock_jwt_keys
    
    class MockSigningKey:
        key = pem_public
        
    class MockJWKSClient:
        def __init__(self, *args, **kwargs):
            pass
        
        def get_signing_key_from_jwt(self, token):
            return MockSigningKey()
            
    return MockJWKSClient

@pytest.fixture
def auth_enforced_app(app, mock_jwks_client_class):
    """
    Returns an application instance where authentication is STRICTLY enforced
    (TESTING=False) but PyJWKClient is mocked to allow our locally signed tokens.
    """
    app.config["TESTING"] = False
    app.config["AUTH_DISABLED"] = False
    
    # Patch the _get_jwks_client function to return our mock
    # The application imports it as app.utils.auth
    with patch("app.utils.auth._get_jwks_client", return_value=mock_jwks_client_class()):
        yield app

@pytest.fixture
def valid_e2e_token(app, mock_jwt_keys):
    """Creates a signed JWT token that will satisfy Keycloak validations."""
    pem_private, _ = mock_jwt_keys
    client_id = app.config.get("KEYCLOAK_CLIENT_ID", "mories-client")
    
    payload = {
        "sub": "e2e-dummy-user",
        "aud": client_id,
        "realm_access": {"roles": ["admin", "user"]},
        "resource_access": {
            client_id: {"roles": ["admin"]}
        }
    }
    
    return jwt.encode(payload, pem_private, algorithm="RS256")
