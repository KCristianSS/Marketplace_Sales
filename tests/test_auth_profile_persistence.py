from types import SimpleNamespace
import uuid

from backend.services.clientes.app.routers import _ensure_cliente_persistido
from backend.services.clientes.app.schemas import PerfilResponse


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.filters = []
        self.payload = None

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.filters.append((field, str(value)))
        return self

    def limit(self, *_args):
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self.payload is not None:
            rows.append(self.payload)
            return SimpleNamespace(data=[self.payload])
        data = [row for row in rows if all(str(row.get(k)) == v for k, v in self.filters)]
        return SimpleNamespace(data=data)


class FakeSupabase:
    def __init__(self):
        self.tables = {"perfiles_clientes": [], "puntos_fidelidad": []}

    def table(self, name):
        return FakeQuery(self, name)


def test_perfil_demo_y_puntos_se_crean_idempotentemente():
    client = FakeSupabase()
    cliente_id = uuid.UUID("00000000-0000-0000-0000-000000000004")
    user = {
        "id": cliente_id,
        "user_id": cliente_id,
        "email": "cliente@maxiconecta.bo",
        "nombre_completo": "Carlos Perez (Cliente Retail)",
        "telefono": "+591 71234567",
        "tipo_cliente": "retail",
        "puntos_saldo": 120,
    }
    profile = PerfilResponse(
        id=cliente_id,
        user_id=cliente_id,
        email=user["email"],
        nombre_completo=user["nombre_completo"],
        telefono=user["telefono"],
        role="cliente",
        puntos_saldo=120,
    )

    _ensure_cliente_persistido(client, user, profile)
    _ensure_cliente_persistido(client, user, profile)

    assert len(client.tables["perfiles_clientes"]) == 1
    assert client.tables["perfiles_clientes"][0]["id"] == str(cliente_id)
    assert len(client.tables["puntos_fidelidad"]) == 1
    assert client.tables["puntos_fidelidad"][0]["puntos_saldo"] == 120