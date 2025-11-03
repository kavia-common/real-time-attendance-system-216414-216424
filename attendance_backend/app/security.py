from typing import Callable
from functools import wraps

from flask import abort
from flask_jwt_extended import get_jwt, get_jwt_identity
from passlib.hash import bcrypt

from .models import UserRole


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hash(password)


# PUBLIC_INTERFACE
def verify_password(password: str, password_hash: str) -> bool:
    """Verify plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.verify(password, password_hash)
    except Exception:
        return False


# PUBLIC_INTERFACE
def require_roles(*roles: UserRole) -> Callable:
    """Decorator to ensure the current JWT identity has one of the roles."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            role = claims.get("role")
            if role is None or (roles and role not in [r.value for r in roles]):
                abort(403, description="Insufficient permissions")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# PUBLIC_INTERFACE
def current_user_identity() -> dict:
    """Return the current JWT identity payload."""
    identity = get_jwt_identity()
    claims = get_jwt()
    return {
        "id": identity,
        "role": claims.get("role"),
        "email": claims.get("email"),
        "name": claims.get("name"),
    }
