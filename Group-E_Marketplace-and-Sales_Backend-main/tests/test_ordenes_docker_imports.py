"""Verifica la carga del servicio sin backend.services, como en su imagen Docker."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_ordenes_carga_con_la_estructura_de_docker(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    (tmp_path / "backend").mkdir()
    shutil.copy2(backend / "__init__.py", tmp_path / "backend" / "__init__.py")
    shutil.copytree(backend / "shared", tmp_path / "backend" / "shared")
    shutil.copytree(backend / "services" / "ordenes" / "app", tmp_path / "app")
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path),
        "ENVIRONMENT": "testing",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "SUPABASE_SECRET_KEY": "",
        "GOOGLE_APPLICATION_CREDENTIALS": "",
        "DESPACHOS_WORKER_ENABLED": "false",
    }
    code = """
import importlib.util
from fastapi.testclient import TestClient
from app.main import app

assert importlib.util.find_spec('backend.services') is None
client = TestClient(app)
response = client.get('/health')
assert response.status_code == 200, response.text
assert response.json()['service'] == 'ms-ordenes'
assert '/api/v1/ordenes/{id}/despacho' in app.openapi()['paths']
"""
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
