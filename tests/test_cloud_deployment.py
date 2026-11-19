import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_render_private_urls_and_production_demo_accounts():
    env = {
        **os.environ,
        "ENVIRONMENT": "production",
        "MS_CATALOGO_URL": "",
        "MS_CLIENTES_URL": "",
        "MS_CATALOGO_HOSTPORT": "catalogo-interno:8001",
        "MS_CLIENTES_HOSTPORT": "clientes-interno:8004",
    }
    code = (
        "import pathlib,sys,types; "
        "backend=types.ModuleType('backend'); "
        "backend.__path__=[str(pathlib.Path.cwd())]; "
        "sys.modules['backend']=backend; "
        "from backend.shared.config import settings; "
        "assert settings.MS_CATALOGO_URL=='http://catalogo-interno:8001'; "
        "assert settings.MS_CLIENTES_URL=='http://clientes-interno:8004'; "
        "from backend.services.clientes.app.routers import _USERS_DB; "
        "assert not _USERS_DB"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_explicit_microservice_urls_take_precedence():
    env = {
        **os.environ,
        "MS_CATALOGO_URL": "http://ms-catalogo:8001",
        "MS_CLIENTES_URL": "http://ms-clientes:8004",
        "MS_CATALOGO_HOSTPORT": "other-host:10000",
        "MS_CLIENTES_HOSTPORT": "other-host:10000",
    }
    result = subprocess.run(
        [sys.executable, "-c", (
            "from shared.config import settings; "
            "assert settings.MS_CATALOGO_URL=='http://ms-catalogo:8001'; "
            "assert settings.MS_CLIENTES_URL=='http://ms-clientes:8004'"
        )], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_gateway_production_cors():
    env = {**os.environ, "CORS_ORIGINS": "https://frontend.example"}
    code = (
        "import pathlib,sys,types; "
        "backend=types.ModuleType('backend'); "
        "backend.__path__=[str(pathlib.Path.cwd())]; "
        "sys.modules['backend']=backend; "
        "from fastapi.testclient import TestClient; "
        "from backend.gateway.app.main import app; "
        "client=TestClient(app); "
        "assert client.get('/health').status_code==200; "
        "headers={'Origin':'https://frontend.example','Access-Control-Request-Method':'GET'}; "
        "allowed=client.options('/api/v1/catalogo/productos',headers=headers); "
        "assert allowed.status_code==200; "
        "assert allowed.headers['access-control-allow-origin']=='https://frontend.example'; "
        "headers['Origin']='https://other.example'; "
        "blocked=client.options('/api/v1/catalogo/productos',headers=headers); "
        "assert blocked.status_code==400; "
        "assert 'access-control-allow-origin' not in blocked.headers"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr