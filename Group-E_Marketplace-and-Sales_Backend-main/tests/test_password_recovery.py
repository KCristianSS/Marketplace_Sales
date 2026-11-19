from fastapi.testclient import TestClient

from backend.services.clientes.app.main import app
from backend.services.clientes.app import routers
from backend.shared.config import settings


client = TestClient(app)


def test_password_reset_request_uses_frontend_recovery_url_and_generic_response(monkeypatch):
    calls = []

    class FakeAuth:
        def reset_password_email(self, email, options=None):
            calls.append((email, options))

    class FakeSupabase:
        auth = FakeAuth()

    monkeypatch.setattr(routers, "get_supabase_client", lambda: FakeSupabase())
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://shop.example/")

    existing = client.post(
        "/api/v1/clientes/auth/password-reset/request",
        json={"email": "Cliente@Example.com"},
    )
    unknown = client.post(
        "/api/v1/clientes/auth/password-reset/request",
        json={"email": "unknown@example.com"},
    )

    assert existing.status_code == unknown.status_code == 202
    assert existing.json() == unknown.json()
    assert calls == [
        ("cliente@example.com", {"redirect_to": "https://shop.example/restablecer-contrasena"}),
        ("unknown@example.com", {"redirect_to": "https://shop.example/restablecer-contrasena"}),
    ]


def test_password_reset_request_fails_when_supabase_is_unavailable(monkeypatch):
    monkeypatch.setattr(routers, "get_supabase_client", lambda: None)

    response = client.post(
        "/api/v1/clientes/auth/password-reset/request",
        json={"email": "cliente@example.com"},
    )

    assert response.status_code == 503
    assert "no está disponible" in response.json()["detail"]