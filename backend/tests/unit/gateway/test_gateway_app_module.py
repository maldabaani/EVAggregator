"""evagg.gateway_app builds its FastAPI app at import time, conditioned on
app_mode — these tests reload the module under both settings to prove the
dev-mode forwarder is actually absent in app_mode=production, not just
that the source code says so.
"""

from __future__ import annotations

import importlib

from starlette.testclient import TestClient

from evagg.core.config import settings


def _reload_gateway_app():
    import evagg.gateway_app as gateway_app_module

    return importlib.reload(gateway_app_module)


def test_dev_forwarder_is_mounted_in_testing_mode():
    original_mode = settings.app_mode
    settings.app_mode = "testing"
    try:
        module = _reload_gateway_app()
        client = TestClient(module.app)

        response = client.post("/admin/tariffs", json={"name": "x"})

        # No X-Dev-Tenant-Id header -> the forwarder's own 400, not FastAPI's
        # 404 -- proves the route is mounted at all, not merely how it fails.
        assert response.status_code == 400
    finally:
        settings.app_mode = original_mode
        _reload_gateway_app()


def test_dev_forwarder_is_absent_in_production_mode():
    original_mode = settings.app_mode
    settings.app_mode = "production"
    try:
        module = _reload_gateway_app()
        client = TestClient(module.app)

        response = client.post("/admin/tariffs", json={"name": "x"})

        # Route genuinely doesn't exist here -- FastAPI's 404, not the
        # forwarder's own 400.
        assert response.status_code == 404
    finally:
        settings.app_mode = original_mode
        _reload_gateway_app()


def test_oauth_endpoints_still_work_regardless_of_app_mode():
    original_mode = settings.app_mode
    settings.app_mode = "production"
    try:
        module = _reload_gateway_app()
        client = TestClient(module.app)

        response = client.get("/healthz")

        assert response.status_code == 200
    finally:
        settings.app_mode = original_mode
        _reload_gateway_app()
