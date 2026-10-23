"""Vercel ASGI entrypoint for the DocuSentra FastAPI application.

Keeping a conventional index.py entrypoint lets Vercel identify the exported
`app` as an ASGI application. The application implementation lives in app/main.py.
"""
from app.main import app

__all__ = ["app"]
