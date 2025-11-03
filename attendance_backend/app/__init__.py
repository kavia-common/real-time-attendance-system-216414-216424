import os
from datetime import timedelta
from typing import Iterable

from flask import Flask, Response, stream_with_context
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_smorest import Api

from .routes.health import blp  # keep existing health blueprint
# Import db module to ensure engine/session are available to the app when needed.
# This does not establish a connection immediately; engine is created lazily.
try:
    from . import db  # noqa: F401
except Exception:
    # Avoid failing app import when DB env is not yet configured (e.g., docs gen)
    db = None  # type: ignore


def _configure_app(app: Flask) -> None:
    """Apply environment-driven configuration defaults."""
    # API docs / OpenAPI
    app.config["API_TITLE"] = os.getenv("API_TITLE", "My Flask API")
    app.config["API_VERSION"] = os.getenv("API_VERSION", "v1")
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = os.getenv("OPENAPI_URL_PREFIX", "/docs")
    app.config["OPENAPI_SWAGGER_UI_PATH"] = ""
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    # Security / JWT
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "3600"))
    )

    # CORS
    cors_origins = os.getenv("CORS_ORIGINS", "*")
    app.config["CORS_ORIGINS"] = cors_origins


def create_app() -> Flask:
    """Application factory for initializing Flask app, JWT, CORS, and API."""
    app = Flask(__name__)
    app.url_map.strict_slashes = False

    _configure_app(app)

    # CORS setup
    CORS(app, resources={r"/*": {"origins": app.config["CORS_ORIGINS"]}})

    # JWT setup
    JWTManager(app)

    # API / OpenAPI via flask-smorest
    api = Api(app)

    # Register blueprints
    api.register_blueprint(blp)

    # Attach api object to module-level for generate_openapi compatibility
    # This mirrors the previous pattern where generate_openapi imports app, api
    globals()["api"] = api
    return app


# Instantiate app for scripts that expect `from app import app, api`
app = create_app()


# PUBLIC_INTERFACE
def sse_stream(generator: Iterable[str], mimetype: str = "text/event-stream") -> Response:
    """Stream Server-Sent Events responses using Flask's native streaming.

    This utility wraps a generator and sets the correct mimetype.
    Example generator yields lines like 'data: {...}\\n\\n'
    """
    return Response(stream_with_context(generator), mimetype=mimetype)
