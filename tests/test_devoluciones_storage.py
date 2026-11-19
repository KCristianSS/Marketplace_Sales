import asyncio
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from starlette.datastructures import Headers, UploadFile

from backend.services.ordenes.app import routers
from backend.shared import audit_operations


def test_solicitud_crea_bucket_con_opciones_y_guarda_evidencia(monkeypatch):
    cliente_id, orden_id, item_id, variante_id = (str(uuid4()) for _ in range(4))
    guardados = []

    class Query:
        def __init__(self, tabla):
            self.tabla = tabla
            self.fila = None

        def select(self, *_args): return self
        def eq(self, *_args): return self
        def limit(self, *_args): return self
        def insert(self, fila):
            self.fila = fila
            return self

        def execute(self):
            if self.tabla == 'ordenes':
                filas = [{'id': orden_id, 'cliente_id': cliente_id, 'estado': 'entregada',
                          'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.12345+00:00')}]
            elif self.tabla == 'orden_items':
                filas = [{'id': item_id, 'variante_id': variante_id, 'sku': 'SKU',
                          'nombre_producto': 'Producto', 'cantidad': 1, 'precio_unitario': 10}]
            elif self.fila is not None:
                guardados.append(self.fila)
                filas = [self.fila]
            else:
                filas = []
            return SimpleNamespace(data=filas)

    class Storage:
        def __init__(self):
            self.creado = None
            self.cargas = []

        def list_buckets(self): return []
        # Firma del SDK actual: el segundo parámetro es name, no options.
        def create_bucket(self, id, name=None, options=None):
            assert name is None
            assert options == {'public': True, 'file_size_limit': 5 * 1024 * 1024}
            self.creado = id

        def from_(self, _bucket): return self
        def upload(self, path, content, file_options): self.cargas.append((path, content, file_options))
        def get_public_url(self, path): return 'https://storage.example/' + path

    storage = Storage()
    client = SimpleNamespace(storage=storage, table=lambda nombre: Query(nombre))
    monkeypatch.setattr(routers, '_get_supabase_safe', lambda: client)
    monkeypatch.setattr(routers, '_perfil_cliente_id', lambda *_args: cliente_id)
    monkeypatch.setattr(audit_operations, 'get_supabase_admin_client', lambda: None)
    monkeypatch.setattr(audit_operations, 'registrar_auditoria', lambda *_args, **_kwargs: None)
    imagen = UploadFile(file=io.BytesIO(b'imagen'), filename='foto.png',
                        headers=Headers({'content-type': 'image/png'}))

    resultado = asyncio.run(routers.crear_solicitud_devolucion(
        orden_id=orden_id, motivo='Producto dañado',
        items=json.dumps([{'orden_item_id': item_id, 'cantidad': 1}]),
        evidencias=[imagen], current_user={'role': 'cliente', 'user_id': cliente_id},
    ))

    assert storage.creado == 'devoluciones-evidencia'
    assert len(storage.cargas) == 1
    assert resultado == guardados[0]
    assert resultado['items'][0]['orden_item_id'] == item_id
    assert resultado['evidencia_urls'][0].startswith('https://storage.example/')
