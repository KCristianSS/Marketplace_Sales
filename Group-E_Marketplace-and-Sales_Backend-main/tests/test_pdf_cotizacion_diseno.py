from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.ordenes.app.pdf import generar_cotizacion_pdf

fitz = pytest.importorskip('fitz')


def test_cotizacion_multpagina_conserva_datos_y_cabeceras():
    items = [SimpleNamespace(cantidad=2, nombre_producto=f'Producto especial {i} & compañía',
                             sku=f'SKU-{i:03}', precio_unitario=Decimal('100.25'),
                             total_linea=Decimal('200.50')) for i in range(45)]
    quote = SimpleNamespace(codigo_cotizacion='COT-TEST-2026', created_at=datetime(2026, 11, 10),
                            vigencia_hasta=date(2026, 11, 25), vigencia_dias=15,
                            razon_social='Compañía Álvarez S.R.L.', nombre_cliente='Ana Pérez',
                            nit_ci='123456789', items=items, subtotal=Decimal('9022.50'),
                            descuento_porcentaje=Decimal('7.5'), descuento_monto=Decimal('676.69'),
                            total=Decimal('8345.81'))
    document = fitz.open(stream=generar_cotizacion_pdf(quote), filetype='pdf')
    assert len(document) > 1
    text = '\n'.join(page.get_text() for page in document)
    assert 'Compañía Álvarez' in text and '123456789' in text
    assert 'SKU-000' in text and 'SKU-044' in text
    assert '7.5%' in text and '8,345.81' in text
    assert all('PRODUCTO / SKU' in page.get_text() for page in document if 'SKU-' in page.get_text())
    assert all(f'Página {i + 1}' in page.get_text() for i, page in enumerate(document))
