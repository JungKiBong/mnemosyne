"""
Keycloak JWT Authentication Utilities

Provides a Flask decorator for protecting API endpoints using Keycloak-issued JWT tokens.
Includes JWKS key caching to avoid per-request network calls.
"""

import logging
from functools import wraps

from flask import request, jsonify, g

from ..config import Config

logger = logging.getLogger(__name__)

# Lazy-initialize JWT dependencies to avoid startup failures when PyJWT is missing
_jwt = None
_PyJWKClient = None
_jwks_client_instance = None


def _ensure_jwt_deps():
    """Import jwt/PyJWKClient on first use so the server boots even without PyJWT."""
    global _jwt, _PyJWKClient
    if _jwt is None:
        try:
            import jwt as _jwt_mod
            from jwt import PyJWKClient as _PJWK
            _jwt = _jwt_mod
            _PyJWKClient = _PJWK
        except ImportError:
            raise ImportError(
                "PyJWT with cryptography extras is required for Keycloak auth. "
                "Install with: pip install 'PyJWT[crypto]'"
            )


def _get_jwks_client():
    """Return a cached PyJWKClient to avoid fetching JWKS on every request."""
    global _jwks_client_instance
    if _jwks_client_instance is None:
        _ensure_jwt_deps()
        base_url = Config.KEYCLOAK_URL.rstrip('/')
        jwks_url = f"{base_url}/realms/{Config.KEYCLOAK_REALM}/protocol/openid-connect/certs"
        _jwks_client_instance = _PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client_instance


def require_auth(roles=None):
    """
    Decorator to protect API endpoints using Keycloak JWT authentication.

    Args:
        roles (list): Optional list of required roles. If provided, the user
                      must have at least one. Roles are checked against both
                      realm-level and client-level role claims.

    Usage:
        @app.route('/api/protected')
        @require_auth(roles=['admin'])
        def protected():
            user = g.user  # verified JWT claims
            ...
    """
    if roles is None:
        roles = []

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get("Authorization", None)
            if not auth_header:
                return jsonify({"error": "Authorization header is missing"}), 401

            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return jsonify({"error": "Authorization header must be 'Bearer <token>'"}), 401

            token = parts[1]

            try:
                _ensure_jwt_deps()
                jwks_client = _get_jwks_client()
                signing_key = jwks_client.get_signing_key_from_jwt(token)

                data = _jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=Config.KEYCLOAK_CLIENT_ID,
                    options={"verify_exp": True},
                )
            except ImportError as ie:
                logger.error(f"JWT dependency missing: {ie}")
                return jsonify({"error": "Server authentication not configured"}), 500
            except Exception as e:
                # Differentiate common error types for clearer client feedback
                err_type = type(e).__name__
                if "ExpiredSignature" in err_type:
                    return jsonify({"error": "Token has expired"}), 401
                if "InvalidToken" in err_type or "DecodeError" in err_type:
                    return jsonify({"error": f"Invalid token: {e}"}), 401
                logger.error(f"Auth verification error ({err_type}): {e}")
                return jsonify({"error": "Authentication failed"}), 401

            # --- Role authorization ---
            if roles:
                user_roles = set()

                realm_access = data.get("realm_access")
                if isinstance(realm_access, dict):
                    user_roles.update(realm_access.get("roles", []))

                resource_access = data.get("resource_access")
                if isinstance(resource_access, dict):
                    client_access = resource_access.get(Config.KEYCLOAK_CLIENT_ID)
                    if isinstance(client_access, dict):
                        user_roles.update(client_access.get("roles", []))

                if not user_roles.intersection(roles):
                    return jsonify({"error": "Insufficient permissions"}), 403

            # Attach verified claims to request context
            g.user = data
            return f(*args, **kwargs)

        return decorated_function
    return decorator
