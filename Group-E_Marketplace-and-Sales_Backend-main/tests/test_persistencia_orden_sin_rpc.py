"""Persistencia de órdenes cuando el RPC confirmar_orden_atomica no está desplegado en Supabase."""
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.ordenes.app import routers as ordenes_routers
from backend.services.ordenes.app.schemas import ItemOrdenResponse, OrdenCreate, OrdenResponse
from backend.shared.pagos_divididos import PagoProcesado

RPC_FALTANTE = (
    "{'message': 'Could not find the function public.confirmar_orden_atomica(p_items, p_orden, p_pagos) "
    "in the schema cache', 'code': 'PGRST202'}"
)


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op, self.payload = db, table, [], "select", None

    def select(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, field, value):
        self.filters.append((field, str(value)))
        return self

    def in_(self, field, values):
        self.filters.append((field, {str(v) for v in values}))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def _match(self, row):
        for field, value in self.filters:
            cell = str(row.get(field))
            if (cell not in value) if isinstance(value, set) else (cell != value):
                return False
        return True

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            if self.table in self.db.fail_on_insert:
                raise RuntimeError(f"insert en {self.table} falló")
            nuevos = self.payload if isinstance(self.payload, list) else [self.payload]
            for fila in nuevos:
                for columna in self.db.columnas_faltantes.get(self.table, ()):
                    if columna in fila:
                        raise RuntimeError(
                            f"{{'message': 'column {self.table}.{columna} does not exist', 'code': '42703'}}"
                        )
            rows.extend(dict(r) for r in nuevos)
            return SimpleNamespace(data=nuevos)
        if self.op == "delete":
            borrados = [r for r in rows if self._match(r)]
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
            return SimpleNamespace(data=borrados)
        return SimpleNamespace(data=[r for r in rows if self._match(r)])


class FakeSupabase:
    def __init__(self, variante_id, fail_on_insert=(), columnas_faltantes=None):
        self.tables = {"variantes": [{"id": variante_id, "producto_id": str(uuid.uuid4())}]}
        self.fail_on_insert = set(fail_on_insert)
        self.columnas_faltantes = columnas_faltantes or {}

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, *_args, **_kwargs):
        raise RuntimeError(RPC_FALTANTE)


def _orden(variante_id: str, transaccion_id: str):
    item = ItemOrdenResponse(
        id=uuid.uuid4(), variante_id=uuid.UUID(variante_id), sku="SKU-1", nombre_producto="Monitor",
        cantidad=1, precio_unitario=Decimal("2450"), total_linea=Decimal("2450"),
    )
    orden = OrdenResponse(
        id=uuid.uuid4(), codigo_orden="ORD-2026-TEST", cliente_id=str(uuid.uuid4()), canal="web",
        tipo_despacho="domicilio", subtotal=Decimal("2450"), total=Decimal("2450"), estado="confirmada",
        created_at=datetime.utcnow(), items=[item],
        pagos=[PagoProcesado(metodo="qr", monto=Decimal("2450"), transaccion_id=transaccion_id)],
    )
    payload = OrdenCreate(
        cliente_id=orden.cliente_id, subtotal=Decimal("2450"), total=Decimal("2450"), metodo_pago="qr",
        items=[{"variante_id": variante_id, "sku": "SKU-1", "nombre_producto": "Monitor",
                "cantidad": 1, "precio_unitario": 2450}],
    )
    return orden, payload


def test_guarda_la_orden_aunque_el_rpc_no_este_desplegado():
    variante_id = str(uuid.uuid4())
    client = FakeSupabase(variante_id)
    orden, payload = _orden(variante_id, "TX-RPC-FALTANTE")

    resultado = ordenes_routers._persistir_orden_atomica(client, orden, payload, {"cuf": None}, str(uuid.uuid4()))

    assert resultado["id"] == str(orden.id) and resultado["existente"] is False
    assert [r["id"] for r in client.tables["ordenes"]] == [str(orden.id)]
    assert client.tables["orden_items"][0]["orden_id"] == str(orden.id)
    assert client.tables["pagos"][0]["transaccion_id"] == "TX-RPC-FALTANTE"


def test_reintento_del_mismo_cobro_no_duplica_la_orden():
    variante_id = str(uuid.uuid4())
    client = FakeSupabase(variante_id)
    orden, payload = _orden(variante_id, "TX-REINTENTO")
    ordenes_routers._persistir_orden_atomica(client, orden, payload, {}, str(uuid.uuid4()))

    resultado = ordenes_routers._persistir_orden_atomica(client, orden, payload, {}, str(uuid.uuid4()))

    assert resultado["existente"] is True
    assert len(client.tables["ordenes"]) == 1


def test_si_falla_un_paso_deshace_la_orden_parcial():
    variante_id = str(uuid.uuid4())
    client = FakeSupabase(variante_id, fail_on_insert={"pagos"})
    orden, payload = _orden(variante_id, "TX-FALLA")

    with pytest.raises(RuntimeError):
        ordenes_routers._persistir_orden_atomica(client, orden, payload, {}, str(uuid.uuid4()))

    assert client.tables["ordenes"] == []


def test_guarda_la_orden_si_la_base_desplegada_no_tiene_columnas_opcionales():
    variante_id = str(uuid.uuid4())
    client = FakeSupabase(variante_id, columnas_faltantes={"ordenes": ("reserva_id", "numero_factura")})
    orden, payload = _orden(variante_id, "TX-ESQUEMA-VIEJO")
    orden.reserva_id, orden.numero_factura = "RES-1", 1234
    payload.reserva_id = "RES-1"

    resultado = ordenes_routers._persistir_orden_atomica(client, orden, payload, {}, str(uuid.uuid4()))

    assert resultado["existente"] is False
    guardada = client.tables["ordenes"][0]
    assert guardada["id"] == str(orden.id)
    assert "reserva_id" not in guardada and "numero_factura" not in guardada
