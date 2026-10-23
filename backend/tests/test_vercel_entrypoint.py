import json
from pathlib import Path

import app.main as main
from index import app as vercel_app


def test_vercel_entrypoint_exports_the_fastapi_asgi_app():
    assert vercel_app is main.app
    assert callable(vercel_app)
    assert getattr(vercel_app, "openapi_url", None) == "/openapi.json"


def test_combined_vercel_config_uses_conventional_asgi_entrypoint():
    project_root = Path(__file__).resolve().parents[2]
    config = json.loads((project_root / "vercel.json").read_text(encoding="utf-8"))
    backend = config["services"]["backend"]
    assert backend["root"] == "backend/"
    assert backend["framework"] == "fastapi"
    assert backend["entrypoint"] == "index:app"
    assert config["rewrites"][0]["source"] == "/api/(.*)"
    assert config["rewrites"][0]["destination"] == {"service": "backend"}


def test_backend_installs_the_official_vercel_python_sdk_for_blob():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "vercel>=0.5.0,<1.0" in requirements
    assert "vercel-blob" not in requirements
