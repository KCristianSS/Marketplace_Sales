import os

# Must run before any backend import: load_dotenv never overrides these, so tests never touch the real Supabase project.
os.environ["ENVIRONMENT"] = "testing"
os.environ["SUPABASE_KEY"] = "anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

import pytest

from backend.shared import stock_ledger
from backend.shared.pubsub_client import GooglePubSubClient


@pytest.fixture(autouse=True)
def inventario_simulado_en_memoria(monkeypatch):
    """Aísla las pruebas del stock real compartido en Redis."""
    monkeypatch.setattr(stock_ledger, "_redis_ok", False)
    monkeypatch.setattr(stock_ledger, "_memory", {})


@pytest.fixture(autouse=True)
def pubsub_sin_publicacion_real(monkeypatch):
    """Evita publicar eventos reales en Google Cloud Pub/Sub durante las pruebas."""
    monkeypatch.setattr(GooglePubSubClient, "_resolve_credentials_path", lambda self: None)
