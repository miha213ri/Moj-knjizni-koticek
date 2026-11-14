"""NeoServ/LiteSpeed Passenger entry point for the FastAPI application."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from a2wsgi import ASGIMiddleware
from app.main import application as asgi_application

# Keep one adapter per Passenger worker process.
_adapter = {"pid": None, "app": None}


def application(environ, start_response):
    process_id = os.getpid()
    if _adapter["pid"] != process_id:
        _adapter["pid"] = process_id
        _adapter["app"] = ASGIMiddleware(asgi_application)
    return _adapter["app"](environ, start_response)
