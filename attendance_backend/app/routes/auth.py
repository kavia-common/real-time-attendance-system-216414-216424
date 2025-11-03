from flask.views import MethodView
from flask_smorest import Blueprint
from flask import abort
from flask_jwt_extended import create_access_token, jwt_required
from sqlalchemy import select

from ..db import session_scope
from ..models import User
from ..schemas import LoginInput, LoginOutput, UserOut
from ..security import verify_password, current_user_identity

blp = Blueprint(
    "Auth",
    "auth",
    url_prefix="/auth",
    description="Authentication endpoints",
)


@blp.route("/login")
class LoginEndpoint(MethodView):
    """Authenticate a user and return a JWT access token."""
    @blp.arguments(LoginInput, location="json")
    @blp.response(200, LoginOutput, description="JWT access token")
    def post(self, payload):
        email = payload["email"].lower().strip()
        password = payload["password"]
        with session_scope() as db:
            user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if user is None or not user.is_active or not verify_password(password, user.password_hash):
                abort(401, description="Invalid credentials")
            claims = {"role": user.role.value, "email": user.email, "name": user.name}
            token = create_access_token(identity=user.id, additional_claims=claims)
            return {"access_token": token, "token_type": "bearer"}


@blp.route("/me")
class MeEndpoint(MethodView):
    """Get current authenticated user details."""
    @jwt_required()
    @blp.response(200, UserOut)
    def get(self):
        ident = current_user_identity()
        with session_scope() as db:
            user = db.get(User, ident["id"])
            if not user:
                abort(404, description="User not found")
            return {"id": user.id, "email": user.email, "name": user.name, "role": user.role.value}
