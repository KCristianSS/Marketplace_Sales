"""Generación del comprobante de orden en PDF sin dependencias externas."""
from datetime import datetime
from typing import Any, Iterable, List


def _pdf_string(value: Any) -> bytes:
    encoded = str(value).encode("cp1252", errors="replace")
    return b"(" + encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _wrapped(value: Any, width: int = 88) -> Iterable[str]:
    words = str(value).split()
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > width and line:
            yield line
            line = word
        else:
            line = candidate
    if line:
        yield line


def generar_comprobante_pdf(orden: Any) -> bytes:
    factura = orden.factura or {}
    comprador = factura.get("datos_comprador") or {}
    lines: List[str] = [
        "MAXICONECTA - COMPROBANTE DIGITAL DE COMPRA",
        "=" * 58,
        f"Orden: {orden.codigo_orden}",
        f"Fecha: {orden.created_at.strftime('%d/%m/%Y %H:%M UTC') if orden.created_at else datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}",
        f"Estado: {orden.estado}",
        f"Cliente: {comprador.get('razon_social') or orden.cliente_id}",
        f"NIT/CI: {comprador.get('nit_ci') or 'No informado'}",
        f"Despacho: {orden.tipo_despacho}",
        "",
        "DETALLE DE PRODUCTOS",
        "-" * 58,
    ]
    for item in orden.items:
        lines.extend(_wrapped(f"{item.cantidad} x {item.nombre_producto} ({item.sku})  BOB {item.total_linea:.2f}"))
    lines.extend(["", f"Subtotal: BOB {orden.subtotal:.2f}"])
    if orden.descuento:
        lines.append(f"Descuentos: - BOB {orden.descuento:.2f}")
    if orden.costo_envio:
        lines.append(f"Envío: BOB {orden.costo_envio:.2f}")
    if orden.numero_factura:
        lines.append(f"Factura: {orden.numero_factura}")
    lines.append(f"Total pagado: BOB {orden.total:.2f}")
    for pago in orden.pagos:
        lines.extend(_wrapped(f"Pago {pago.metodo}: BOB {pago.monto:.2f} · TX {pago.transaccion_id}"))
    if orden.cuf_factura:
        lines.extend(["", f"CUF: {orden.cuf_factura}"])
        if factura.get("codigo_qr"):
            lines.extend(_wrapped(f"Consulta SIAT: {factura['codigo_qr']}"))
    lines.extend(["", "Este comprobante confirma la compra registrada en MaxiConecta."])

    pages = [lines[index:index + 50] for index in range(0, len(lines), 50)] or [[]]
    objects: dict[int, bytes] = {}
    page_ids = [3 + 2 * index for index in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = b" ".join(f"{page_id} 0 R".encode("ascii") for page_id in page_ids)
    objects[2] = b"<< /Type /Pages /Kids [" + kids + f"] /Count {len(page_ids)} >>".encode("ascii")
    for index, page_lines in enumerate(pages):
        page_id = page_ids[index]
        content_id = page_id + 1
        commands = [b"BT /F1 10 Tf 50 790 Td 14 TL"]
        commands.extend(_pdf_string(line) + b" Tj T*" for line in page_lines)
        commands.append(b"ET")
        content = b"\n".join(commands)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream"
    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"

    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, font_id + 1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode("ascii"))
        result.extend(objects[object_id])
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {font_id + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    result.extend(
        f"trailer\n<< /Size {font_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(result)
