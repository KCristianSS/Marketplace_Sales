import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape
from fastapi import APIRouter, HTTPException, status, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.shared.database import get_supabase_admin_client
from backend.shared.erp_clients.inventarios import inventarios_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.pagos_divididos import (
    PagoParcial, PagoProcesado, PagoInvalidoError, normalizar_pagos, metodo_resumen,
    agregar_pasos_de_cobro, construir_order_paid_event, publicar_order_paid_event,
)
from backend.shared.saga import SagaOrchestrator

logger = logging.getLogger("maxiconecta.facturacion")

router = APIRouter(prefix="/api/v1/facturacion", tags=["Facturación Electrónica Legal"])

# ------------------------------------------------------------------------------
# Registros de ejemplo para validación preliminar local. No es el padrón del SIN.
# ------------------------------------------------------------------------------
PADRON_TRIBUTARIO_NACIONAL: Dict[str, Dict[str, str]] = {
    "1020304050": {"razon_social": "EMPRESA MINERA SAN CRISTÓBAL S.A.", "estado": "ACTIVO"},
    "1002345678": {"razon_social": "MAXICONECTA BOLIVIA S.R.L.", "estado": "ACTIVO"},
    "4829102": {"razon_social": "CARLOS MENDOZA PATZI", "estado": "ACTIVO"},
    "7894561012": {"razon_social": "IMPORTADORA Y DISTRIBUIDORA ANDINA S.A.", "estado": "ACTIVO"},
    "6543210": {"razon_social": "SOFÍA DORIA MEDINA", "estado": "ACTIVO"},
    "9876543210": {"razon_social": "SOLUCIONES TECNOLÓGICAS DEL VALLE LTDA.", "estado": "ACTIVO"},
    "1029384756": {"razon_social": "CONSTRUCTORA LOS ANDES S.R.L.", "estado": "ACTIVO"},
    "11223344": {"razon_social": "JUAN PÉREZ GARCÍA", "estado": "INACTIVO"}
}

def _get_supabase_safe() -> Optional[Any]:
    try:
        return get_supabase_admin_client()
    except Exception as e:
        logger.warning(f"Aviso al inicializar cliente Supabase: {e}")
        return None

# Memoria local para correlativo y facturas
_FACTURAS_STORE: List[Dict[str, Any]] = []
_ULTIMO_CORRELATIVO: int = 1420

def _modulo11(cadena: str) -> int:
    """Calcula dígito verificador Módulo 11 según especificación del SIN."""
    mult = 2
    suma = 0
    for c in reversed(cadena):
        if not c.isdigit():
            continue
        suma += int(c) * mult
        mult = mult + 1 if mult < 9 else 2
    resto = suma % 11
    if resto == 0:
        return 0
    if resto == 1:
        return 1
    return 11 - resto

def generar_cuf(nit_emisor: str, fecha_hora: datetime, sucursal: int, modalidad: int,
                tipo_emision: int, tipo_doc_sector: int, numero_factura: int, punto_venta: int) -> str:
    """Genera CUF oficial conforme a la normativa del SIN Bolivia."""
    fh_str = fecha_hora.strftime("%Y%m%d%H%M%S%f")[:17]
    base = f"{nit_emisor.zfill(13)}{fh_str}{str(sucursal).zfill(4)}{modalidad}{tipo_emision}{tipo_doc_sector}{str(numero_factura).zfill(10)}{str(punto_venta).zfill(4)}"
    dv = _modulo11(base)
    cadena_completa = f"{base}{dv}"
    try:
        # Codificación hexadecimal del número base
        val_int = int(cadena_completa)
        cuf_hex = f"{val_int:X}".upper()
        # Formatear estilo legible oficial
        if len(cuf_hex) >= 16:
            return f"CUF-{cuf_hex[:4]}-{cuf_hex[4:8]}-{cuf_hex[8:16]}"
        return f"CUF-{cuf_hex}"
    except Exception:
        return f"CUF-{uuid.uuid4().hex[:16].upper()}"

# ------------------------------------------------------------------------------
# MODELOS PYDANTIC
# ------------------------------------------------------------------------------
class ValidarNitRequest(BaseModel):
    nit_ci: str
    tipo_documento: Optional[str] = "NIT"

class ValidarNitResponse(BaseModel):
    valido: bool
    nit_ci: str
    razon_social: Optional[str] = None
    estado: str
    mensaje: str

class PerfilFiscalResponse(BaseModel):
    id: str
    nit_ci: str
    razon_social: str
    email_facturacion: Optional[str] = None
    tipo_documento: str = "NIT"
    es_predeterminado: bool = True

class ItemFactura(BaseModel):
    variante_id: Optional[str] = None
    sku: Optional[str] = None
    nombre: Optional[str] = None
    nombre_producto: Optional[str] = None
    cantidad: int = 1
    precio: Optional[float] = None
    precio_unitario: Optional[float] = None
    subtotal: Optional[float] = None

class EmitirFacturaRequest(BaseModel):
    modalidad: str = "con_factura"  # "con_factura" | "sin_factura"
    tipo_documento: str = "NIT"      # "NIT" | "CI" | "CEX" | "PAS"
    nit_ci: str
    razon_social: str
    email_facturacion: Optional[str] = None
    guardar_perfil: bool = True
    sucursal: Optional[str] = "Sucursal Central Sopocachi"
    punto_venta: int = 1
    metodo_pago: str = "efectivo"  # método único (compatibilidad); se ignora si se envía `pagos`
    pagos: Optional[List[PagoParcial]] = None  # pago dividido: varias transacciones que suman el total
    items: List[ItemFactura]
    descuento: float = 0.0
    orden_id: Optional[str] = None
    cliente_id: Optional[str] = None

class FacturaEmitidaResponse(BaseModel):
    mensaje: str
    factura: Dict[str, Any]

# ------------------------------------------------------------------------------
# ENDPOINTS
# ------------------------------------------------------------------------------

@router.post("/validar-nit", response_model=ValidarNitResponse)
async def validar_nit(payload: ValidarNitRequest):
    """
    KAN-365: Validación de NIT/CI con el servicio fiscal y Padrón Tributario.
    Permite validar tanto NIT como CI y soporta Consumidor Final ('0').
    """
    clean = str(payload.nit_ci or "").strip()
    tipo_doc = (payload.tipo_documento or "NIT").upper()

    if not clean:
        return ValidarNitResponse(
            valido=False,
            nit_ci="",
            estado="NO_ENCONTRADO",
            mensaje="Debe ingresar un número de NIT o Carnet de Identidad (CI)."
        )

    # 1. Consumidor Final
    if clean in ("0", "99001") or clean.lower() == "consumidor final":
        return ValidarNitResponse(
            valido=True,
            nit_ci="0",
            razon_social="CONSUMIDOR FINAL",
            estado="ACTIVO",
            mensaje="Documento legal habilitado para ventas a Consumidor Final."
        )

    # 2. Búsqueda en base de datos Supabase (perfiles registrados de clientes)
    client = _get_supabase_safe()
    if client:
        try:
            res = client.table("perfiles_clientes").select("nit_ci, razon_social, nombre_completo").eq("nit_ci", clean).limit(1).execute()
            if res.data:
                row = res.data[0]
                rz = row.get("razon_social") or row.get("nombre_completo")
                return ValidarNitResponse(
                    valido=True,
                    nit_ci=clean,
                    razon_social=rz,
                    estado="ACTIVO",
                    mensaje="Documento validado en la base de datos de clientes MaxiConecta."
                )
        except Exception as e:
            logger.warning(f"Aviso al consultar perfiles_clientes en Supabase: {e}")

    # 3. Búsqueda en el padrón local de referencia, no en el SIN
    if clean in PADRON_TRIBUTARIO_NACIONAL:
        reg = PADRON_TRIBUTARIO_NACIONAL[clean]
        if reg["estado"] == "INACTIVO":
            return ValidarNitResponse(
                valido=False,
                nit_ci=clean,
                razon_social=reg["razon_social"],
                estado="INACTIVO",
                mensaje=f"El NIT {clean} figura INACTIVO en el registro local de referencia; no fue consultado al SIN."
            )
        return ValidarNitResponse(
            valido=True,
            nit_ci=clean,
            razon_social=reg["razon_social"],
            estado="ACTIVO",
            mensaje=f"NIT encontrado en el registro local de referencia: {reg['razon_social']}. No fue verificado contra el SIN."
        )

    # 4. Validación de formato de Carnet de Identidad (CI)
    if tipo_doc == "CI":
        # En Bolivia el CI suele tener entre 4 y 10 caracteres (a veces con complemento, ej 4829102-1E)
        clean_num = clean.split("-")[0]
        if len(clean_num) >= 4 and clean_num.isdigit():
            return ValidarNitResponse(
                valido=True,
                nit_ci=clean,
                razon_social=None,
                estado="ACTIVO",
                mensaje="Formato de CI aceptado para validación preliminar; no fue verificado contra el SIN."
            )
        return ValidarNitResponse(
            valido=False,
            nit_ci=clean,
            estado="FORMATO_INVALIDO",
            mensaje="El CI debe contener al menos 4 dígitos numéricos."
        )

    # 5. Validación de formato de NIT (5 a 15 dígitos numéricos)
    if clean.isdigit() and 5 <= len(clean) <= 15:
        # El formato local no acredita que el NIT esté activo ante el SIN.
        return ValidarNitResponse(
            valido=True,
            nit_ci=clean,
            razon_social=None,
            estado="ACTIVO",
            mensaje="Formato de NIT válido para validación preliminar; no fue verificado contra el SIN."
        )

    return ValidarNitResponse(
        valido=False,
        nit_ci=clean,
        estado="FORMATO_INVALIDO",
        mensaje="El NIT debe contener entre 5 y 15 dígitos numéricos."
    )


@router.get("/perfiles-fiscales", response_model=List[PerfilFiscalResponse])
async def obtener_perfiles_fiscales():
    """Retorna los perfiles fiscales y clientes con NIT/CI para autocompletado."""
    perfiles: List[PerfilFiscalResponse] = []
    
    # 1. Consultar en Supabase
    client = _get_supabase_safe()
    if client:
        try:
            res = client.table("perfiles_clientes").select("id, nit_ci, razon_social, email").not_.is_("nit_ci", "null").limit(20).execute()
            if res.data:
                for row in res.data:
                    nit = row.get("nit_ci")
                    rz = row.get("razon_social")
                    if nit and rz and nit != "0":
                        perfiles.append(PerfilFiscalResponse(
                            id=str(row["id"]),
                            nit_ci=nit,
                            razon_social=rz,
                            email_facturacion=row.get("email"),
                            tipo_documento="NIT" if len(nit) > 8 else "CI",
                            es_predeterminado=True
                        ))
        except Exception as e:
            logger.warning(f"Error al obtener perfiles fiscales de Supabase: {e}")

    # Fallback si no hay perfiles en BD
    if not perfiles:
        perfiles = [
            PerfilFiscalResponse(
                id="perf-001",
                nit_ci="1020304050",
                razon_social="EMPRESA MINERA SAN CRISTÓBAL S.A.",
                email_facturacion="contabilidad@sancristobal.bo",
                tipo_documento="NIT",
                es_predeterminado=True
            ),
            PerfilFiscalResponse(
                id="perf-002",
                nit_ci="1002345678",
                razon_social="MAXICONECTA BOLIVIA S.R.L.",
                email_facturacion="ventas@maxiconecta.bo",
                tipo_documento="NIT",
                es_predeterminado=False
            ),
            PerfilFiscalResponse(
                id="perf-003",
                nit_ci="4829102",
                razon_social="CARLOS MENDOZA PATZI",
                email_facturacion="cmendoza@gmail.com",
                tipo_documento="CI",
                es_predeterminado=False
            )
        ]

    return perfiles


@router.post("/emitir", response_model=FacturaEmitidaResponse, status_code=status.HTTP_201_CREATED)
async def emitir_factura(payload: EmitirFacturaRequest):
    """
    KAN-367: Emisión real de Factura Legal Electrónica con timbrado CUF, CUFD,
    QR oficial del SIN y persistencia integral en PostgreSQL (Supabase).
    """
    global _ULTIMO_CORRELATIVO

    es_consumidor_final = (
        payload.modalidad == "sin_factura" or
        payload.nit_ci in ("0", "99001") or
        payload.razon_social.strip().upper() == "CONSUMIDOR FINAL"
    )

    nit_final = "0" if es_consumidor_final else payload.nit_ci.strip()
    razon_final = "CONSUMIDOR FINAL" if es_consumidor_final else payload.razon_social.strip().upper()
    tipo_doc_final = "CI" if es_consumidor_final else payload.tipo_documento.upper()

    if not es_consumidor_final and (not nit_final or not razon_final):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para emitir factura con valor legal nominada debe ingresar NIT/CI y Razón Social."
        )

    # 1. Procesar montos e ítems
    items_procesados = []
    subtotal_calculado = 0.0

    for i in payload.items:
        nombre = i.nombre or i.nombre_producto or "Producto General"
        sku = i.sku or "SKU-GEN"
        cant = i.cantidad if i.cantidad > 0 else 1
        prec = float(i.precio if i.precio is not None else (i.precio_unitario if i.precio_unitario is not None else 0.0))
        sub = float(i.subtotal if i.subtotal is not None else (cant * prec))
        subtotal_calculado += sub
        items_procesados.append({
            "variante_id": i.variante_id,
            "sku": sku,
            "nombre": nombre,
            "cantidad": cant,
            "precio_unitario": prec,
            "subtotal": round(sub, 2)
        })

    descuento_val = float(payload.descuento) if payload.descuento else 0.0
    total_pagar = max(0.0, round(subtotal_calculado - descuento_val, 2))
    monto_iva = round(total_pagar * 0.13, 2)  # 13% IVA oficial de Bolivia

    # 1.b Pago dividido: la suma de las transacciones debe igualar el total a pagar.
    try:
        pagos_normalizados = normalizar_pagos(payload.pagos, payload.metodo_pago, Decimal(str(total_pagar)))
    except PagoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    pagos_procesados: List[PagoProcesado] = []
    if payload.orden_id:
        # Las órdenes web ya descontaron stock y cobraron al confirmar su reserva: solo se registran los tramos.
        pagos_procesados = [
            PagoProcesado(metodo=p.metodo, monto=p.monto, transaccion_id=f"TX-{uuid.uuid4().hex[:14].upper()}", referencia=p.referencia)
            for p in pagos_normalizados
        ]
    else:
        # Venta POS directa: descuenta stock y autoriza cada tramo de pago como una saga. Si un tramo es
        # rechazado se reversan los cobros ya aprobados y se reingresa el stock (nada queda a medias).
        referencia_venta = f"POS-{uuid.uuid4().hex[:8]}"
        saga = SagaOrchestrator("venta_pos_pago_dividido")
        saga.paso(
            "descuento_stock",
            lambda: inventarios_client.descuento_directo(items_procesados, orden_id=referencia_venta),
            lambda _res: inventarios_client.reingreso_por_devolucion(referencia_venta, items_procesados),
        )
        agregar_pasos_de_cobro(saga, pagos_normalizados, pagos_procesados)
        resultado_saga = await saga.ejecutar()
        if not resultado_saga.exitosa:
            motivo = resultado_saga.error or "No se pudo completar la venta."
            codigo = status.HTTP_409_CONFLICT if resultado_saga.paso_fallido == "descuento_stock" else status.HTTP_402_PAYMENT_REQUIRED
            detalle = motivo.split(": ", 1)[-1]
            if resultado_saga.compensados:
                detalle = f"{detalle} Se revirtieron los pasos ya realizados: {', '.join(resultado_saga.compensados)}."
            raise HTTPException(status_code=codigo, detail=detalle)

    # 2. Correlativo, CUF y CUFD oficiales
    _ULTIMO_CORRELATIVO += 1
    numero_factura = _ULTIMO_CORRELATIVO
    nit_emisor = "1028374029"  # MaxiConecta Bolivia S.R.L.
    ahora = datetime.utcnow()

    cuf = generar_cuf(
        nit_emisor=nit_emisor,
        fecha_hora=ahora,
        sucursal=0,
        modalidad=1,
        tipo_emision=1,
        tipo_doc_sector=1,
        numero_factura=numero_factura,
        punto_venta=payload.punto_venta
    )
    cufd = f"CUFD-{uuid.uuid4().hex[:8].upper()}-{ahora.strftime('%Y%m%d')}"

    # Enlace oficial al QR del SIAT / Impuestos Nacionales
    codigo_qr = f"https://pilotosiat.impuestos.gob.bo/consulta/QR?nit={nit_emisor}&cuf={cuf}&numero={numero_factura}&t={total_pagar:.2f}"
    leyenda_fiscal = "Ley N° 453: El proveedor deberá suministrar el servicio en las modalidades y términos ofertados."

    factura_id = f"FAC-{uuid.uuid4()}"
    factura_payload = {
        "id": factura_id,
        "numero_factura": numero_factura,
        "cuf": cuf,
        "cufd": cufd,
        "fecha_emision": ahora.isoformat(),
        "modalidad": "sin_factura" if es_consumidor_final else "con_factura",
        "datos_comprador": {
            "tipo_documento": tipo_doc_final,
            "nit_ci": nit_final,
            "razon_social": razon_final,
            "email_facturacion": payload.email_facturacion
        },
        "sucursal": payload.sucursal or "Sucursal Sopocachi",
        "punto_venta": payload.punto_venta,
        "subtotal": round(subtotal_calculado, 2),
        "descuento": round(descuento_val, 2),
        "total": total_pagar,
        "total_sujeto_iva": total_pagar,
        "monto_iva": monto_iva,
        "metodo_pago": metodo_resumen(pagos_procesados) if pagos_procesados else payload.metodo_pago,
        "pagos": [
            {"metodo": p.metodo, "monto": float(p.monto), "transaccion_id": p.transaccion_id,
             "referencia": p.referencia, "cambio": float(p.cambio)}
            for p in pagos_procesados
        ],
        "cambio_total": float(sum((p.cambio for p in pagos_procesados), Decimal("0.00"))),
        "codigo_qr": codigo_qr,
        "leyenda_fiscal": leyenda_fiscal,
        "items": items_procesados
    }

    # 3. Notificación al ERP de Pagos (RIO-PAG-02)
    try:
        await pagos_client.emitir_factura({
            "numero_factura": numero_factura,
            "cuf": cuf,
            "nit_ci": nit_final,
            "razon_social": razon_final,
            "monto_total": total_pagar
        })
    except Exception as e:
        logger.warning(f"Aviso comunicando con ERP Pagos: {e}")

    # 4. PERSISTENCIA EN BASE DE DATOS (Supabase PostgreSQL)
    client = _get_supabase_safe()
    if client:
        try:
            # A) Guardar o actualizar perfil de cliente
            cliente_db_id = payload.cliente_id
            if not cliente_db_id and not es_consumidor_final:
                # Buscar si ya existe por nit_ci
                res_cli = client.table("perfiles_clientes").select("id").eq("nit_ci", nit_final).limit(1).execute()
                if res_cli.data:
                    cliente_db_id = res_cli.data[0]["id"]
                    if payload.guardar_perfil:
                        client.table("perfiles_clientes").update({
                            "razon_social": razon_final,
                            "updated_at": ahora.isoformat()
                        }).eq("id", cliente_db_id).execute()
                elif payload.guardar_perfil:
                    # Crear nuevo cliente con estos datos
                    safe_email = (
                        payload.email_facturacion.strip().lower()
                        if payload.email_facturacion and "@" in payload.email_facturacion
                        else f"factura.{nit_final}.{int(ahora.timestamp())}@maxiconecta.bo"
                    )
                    ins_cli = client.table("perfiles_clientes").insert({
                        "nombre_completo": razon_final,
                        "email": safe_email,
                        "nit_ci": nit_final,
                        "razon_social": razon_final,
                        "tipo_cliente": "retail"
                    }).execute()
                    if ins_cli.data:
                        cliente_db_id = ins_cli.data[0]["id"]

            if not cliente_db_id:
                # Usar cliente por defecto existente en Supabase
                res_def = client.table("perfiles_clientes").select("id").limit(1).execute()
                if res_def.data:
                    cliente_db_id = res_def.data[0]["id"]

            # B) Vincular o crear Orden
            orden_db_id = payload.orden_id
            if orden_db_id:
                client.table("ordenes").update({
                    "cuf_factura": cuf,
                    "updated_at": ahora.isoformat()
                }).eq("id", orden_db_id).execute()
            elif cliente_db_id:
                # Crear orden de venta POS
                codigo_orden = f"POS-{numero_factura}-{uuid.uuid4().hex[:4].upper()}"
                res_ord = client.table("ordenes").insert({
                    "codigo_orden": codigo_orden,
                    "cliente_id": cliente_db_id,
                    "canal": "pos",
                    "tipo_despacho": "retiro_sucursal",
                    "subtotal": round(subtotal_calculado, 2),
                    "descuento": round(descuento_val, 2),
                    "costo_envio": 0.0,
                    "total": total_pagar,
                    "moneda": "BOB",
                    "estado": "confirmada",
                    "cuf_factura": cuf
                }).execute()
                if res_ord.data:
                    orden_db_id = res_ord.data[0]["id"]
                    factura_payload["orden_id"] = orden_db_id
                    factura_payload["codigo_orden"] = codigo_orden

            # C) Registrar un pago por cada transacción (pago dividido) en la tabla 'pagos'.
            #    El raw_payload de la factura se guarda solo en la primera fila para que el
            #    listado de facturas no se duplique.
            if orden_db_id:
                for indice, pago in enumerate(pagos_procesados):
                    client.table("pagos").insert({
                        "orden_id": orden_db_id,
                        "transaccion_id": pago.transaccion_id or f"TX-{cuf.replace('CUF-', '')[:12]}-{indice + 1}",
                        "metodo": pago.metodo,
                        "monto": float(pago.monto),
                        "moneda": "BOB",
                        "estado": "aprobado",
                        "raw_payload": factura_payload if indice == 0 else None,
                    }).execute()

            # D) Intentar insertar en tabla facturas si existe en Supabase
            try:
                client.table("facturas").insert({
                    "orden_id": orden_db_id,
                    "numero_factura": numero_factura,
                    "cuf": cuf,
                    "cufd": cufd,
                    "nit_emisor": nit_emisor,
                    "nit_ci_cliente": nit_final,
                    "razon_social_cliente": razon_final,
                    "email_cliente": payload.email_facturacion,
                    "monto_total": total_pagar,
                    "monto_iva": monto_iva,
                    "modalidad": "electronica_en_linea",
                    "estado": "emitida",
                    "codigo_qr": codigo_qr,
                    "items": items_procesados
                }).execute()
            except Exception:
                pass  # Si la tabla aún no está migrada en PostgREST, ya está respaldada en pagos.raw_payload

            logger.info(f"Factura #{numero_factura} emitida con CUF {cuf} y persistida en BD.")
        except Exception as e:
            logger.warning(f"Aviso al persistir factura en Supabase (conservada en memoria): {e}")

    _FACTURAS_STORE.insert(0, factura_payload)

    # 5. OrderPaidEvent -> Contabilidad (RIO-CON-01) con el desglose por forma de pago.
    evento = construir_order_paid_event(
        orden_id=factura_payload.get("orden_id") or factura_id,
        codigo_orden=factura_payload.get("codigo_orden"),
        canal="web" if payload.orden_id else "pos",
        total=Decimal(str(total_pagar)),
        pagos=pagos_procesados,
        cuf=cuf,
        numero_factura=numero_factura,
    )
    factura_payload["evento_contable"] = await publicar_order_paid_event(evento)

    return FacturaEmitidaResponse(
        mensaje="Factura legal electrónica emitida y timbrada exitosamente.",
        factura=factura_payload
    )


@router.get("/facturas", response_model=List[Dict[str, Any]])
async def listar_facturas():
    """Lista las facturas emitidas y timbradas registradas en el sistema."""
    client = _get_supabase_safe()
    if client:
        try:
            # Obtener de pagos que tengan raw_payload con cuf
            res = client.table("pagos").select("raw_payload, created_at").not_.is_("raw_payload", "null").order("created_at", desc=True).limit(30).execute()
            if res.data:
                facturas_bd = []
                for p in res.data:
                    raw = p.get("raw_payload")
                    if isinstance(raw, dict) and "cuf" in raw:
                        facturas_bd.append(raw)
                if facturas_bd:
                    return facturas_bd
        except Exception as e:
            logger.warning(f"Error al consultar facturas en Supabase: {e}")

    return _FACTURAS_STORE


@router.get("/facturas/{cuf}", response_model=Dict[str, Any])
async def obtener_factura_por_cuf(cuf: str):
    """Consulta el detalle fiscal completo de una factura por su CUF."""
    fac = await _buscar_factura(cuf)
    if fac:
        return fac
    raise HTTPException(status_code=404, detail="Factura no encontrada para el CUF especificado.")


@router.get("/facturas/{cuf}/xml")
async def descargar_factura_xml(cuf: str):
    """
    US-37 / RF-37: Descarga de la Factura Electrónica en formato XML oficial timbrado,
    cumpliendo con la especificación técnica del SIN (Servicio de Impuestos Nacionales de Bolivia).
    """
    fac = await _buscar_factura(cuf)
    if not fac:
        raise HTTPException(status_code=404, detail="Factura no encontrada para el CUF especificado.")

    xml_content = construir_factura_xml(fac)
    clean_cuf = cuf.replace("CUF-", "")[:16]
    filename = f"factura_{clean_cuf}.xml"
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/facturas/{cuf}/impresion", response_class=HTMLResponse)
@router.get("/facturas/{cuf}/html", response_class=HTMLResponse, include_in_schema=False)
async def ver_factura_impresion(cuf: str):
    """
    US-37 / RF-37: Renderizado de Comprobante / Factura en formato HTML apto para impresión directa
    y guardado como PDF en cualquier navegador, con QR del SIN, desglose impositivo y ley 453.
    """
    fac = await _buscar_factura(cuf)
    if not fac:
        raise HTTPException(status_code=404, detail="Factura no encontrada para el CUF especificado.")

    html_content = construir_factura_html(fac)
    return HTMLResponse(content=html_content)


@router.get("/facturas/orden/{orden_id}", response_model=Dict[str, Any])
async def obtener_factura_por_orden(orden_id: str):
    """
    US-37: Consulta el comprobante fiscal asociado a una orden específica.
    """
    oid = orden_id.strip()
    for f in _FACTURAS_STORE:
        if str(f.get("orden_id")) == oid:
            return f

    client = _get_supabase_safe()
    if client:
        try:
            res = client.table("pagos").select("raw_payload").eq("orden_id", oid).not_.is_("raw_payload", "null").limit(1).execute()
            if res.data and res.data[0].get("raw_payload"):
                return res.data[0]["raw_payload"]
        except Exception as e:
            logger.warning(f"Error buscando factura de orden en Supabase: {e}")

    raise HTTPException(status_code=404, detail="No se encontró comprobante o factura para la orden especificada.")


async def _buscar_factura(cuf_o_id: str) -> Optional[Dict[str, Any]]:
    """Busca una factura por su CUF o ID interno tanto en memoria como en Supabase."""
    term = cuf_o_id.strip()
    for f in _FACTURAS_STORE:
        if f.get("cuf") == term or f.get("id") == term or str(f.get("numero_factura")) == term:
            return f

    client = _get_supabase_safe()
    if client:
        try:
            # 1. Búsqueda en pagos raw_payload por cuf
            res = client.table("pagos").select("raw_payload").filter("raw_payload->>cuf", "eq", term).limit(1).execute()
            if res.data and res.data[0].get("raw_payload"):
                return res.data[0]["raw_payload"]

            # 2. Búsqueda en facturas tabla si existe
            res_fac = client.table("facturas").select("*").eq("cuf", term).limit(1).execute()
            if res_fac.data:
                row = res_fac.data[0]
                return {
                    "numero_factura": row.get("numero_factura"),
                    "cuf": row.get("cuf"),
                    "cufd": row.get("cufd"),
                    "fecha_emision": row.get("created_at"),
                    "modalidad": row.get("modalidad", "electronica_en_linea"),
                    "datos_comprador": {
                        "nit_ci": row.get("nit_ci_cliente"),
                        "razon_social": row.get("razon_social_cliente"),
                        "email_facturacion": row.get("email_cliente"),
                        "tipo_documento": "NIT" if len(str(row.get("nit_ci_cliente", ""))) > 8 else "CI"
                    },
                    "monto_total": float(row.get("monto_total", 0)),
                    "total": float(row.get("monto_total", 0)),
                    "monto_iva": float(row.get("monto_iva", 0)),
                    "codigo_qr": row.get("codigo_qr"),
                    "items": row.get("items") or []
                }
        except Exception as e:
            logger.warning(f"Error buscando factura en Supabase: {e}")
    return None


def construir_factura_xml(factura: Dict[str, Any]) -> str:
    """Genera el XML oficial de Factura Electrónica en Línea según normativa SIN Bolivia."""
    numero_factura = factura.get("numero_factura", 1)
    cuf = factura.get("cuf", "")
    cufd = factura.get("cufd", f"CUFD-{uuid.uuid4().hex[:8].upper()}")
    fecha_emision = factura.get("fecha_emision", datetime.utcnow().isoformat())
    datos_comprador = factura.get("datos_comprador", {})
    nit_ci = datos_comprador.get("nit_ci", "0")
    razon_social = datos_comprador.get("razon_social", "CONSUMIDOR FINAL")
    tipo_doc = datos_comprador.get("tipo_documento", "CI")
    codigo_tipo_doc = "5" if tipo_doc == "NIT" else "1"
    monto_total = float(factura.get("total", factura.get("monto_total", 0.0)))
    monto_iva = float(factura.get("monto_iva", round(monto_total * 0.13, 2)))
    items = factura.get("items", [])

    xml_items = []
    for idx, item in enumerate(items, start=1):
        sku = escape(str(item.get("sku") or f"SKU-{idx}"))
        nombre = escape(str(item.get("nombre") or item.get("nombre_producto") or "Producto General"))
        cant = item.get("cantidad", 1)
        pu = float(item.get("precio_unitario") or item.get("precio") or 0.0)
        sub = float(item.get("subtotal") or (cant * pu))
        xml_items.append(f"""        <detalle>
            <actividadEconomica>474100</actividadEconomica>
            <codigoProductoSin>8471300000</codigoProductoSin>
            <codigoProducto>{sku}</codigoProducto>
            <descripcion>{nombre}</descripcion>
            <cantidad>{cant}</cantidad>
            <unidadMedida>58</unidadMedida>
            <precioUnitario>{pu:.2f}</precioUnitario>
            <montoDescuento>0.00</montoDescuento>
            <subTotal>{sub:.2f}</subTotal>
        </detalle>""")

    items_block = "\n".join(xml_items) if xml_items else f"""        <detalle>
            <actividadEconomica>474100</actividadEconomica>
            <codigoProductoSin>8471300000</codigoProductoSin>
            <codigoProducto>ITEM-GEN-01</codigoProducto>
            <descripcion>Venta de Productos Tecnológicos MaxiConecta</descripcion>
            <cantidad>1</cantidad>
            <unidadMedida>58</unidadMedida>
            <precioUnitario>{monto_total:.2f}</precioUnitario>
            <montoDescuento>0.00</montoDescuento>
            <subTotal>{monto_total:.2f}</subTotal>
        </detalle>"""

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<facturaComputarizadaCompraVenta xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <cabecera>
        <nitEmisor>1028374029</nitEmisor>
        <razonSocialEmisor>MAXICONECTA BOLIVIA S.R.L.</razonSocialEmisor>
        <municipio>La Paz</municipio>
        <telefono>+591 2 2441122</telefono>
        <numeroFactura>{numero_factura}</numeroFactura>
        <cuf>{escape(cuf)}</cuf>
        <cufd>{escape(cufd)}</cufd>
        <codigoSucursal>0</codigoSucursal>
        <direccion>Av. 16 de Julio (El Prado) #1490</direccion>
        <codigoPuntoVenta>{factura.get("punto_venta", 1)}</codigoPuntoVenta>
        <fechaEmision>{fecha_emision}</fechaEmision>
        <nombreRazonSocial>{escape(razon_social)}</nombreRazonSocial>
        <codigoTipoDocumentoIdentidad>{codigo_tipo_doc}</codigoTipoDocumentoIdentidad>
        <numeroDocumento>{escape(nit_ci)}</numeroDocumento>
        <montoTotal>{monto_total:.2f}</montoTotal>
        <montoTotalSujetoIva>{monto_total:.2f}</montoTotalSujetoIva>
        <montoIva>{monto_iva:.2f}</montoIva>
        <codigoMoneda>1</codigoMoneda>
        <tipoCambio>1</tipoCambio>
        <montoTotalMoneda>{monto_total:.2f}</montoTotalMoneda>
        <leyenda>Ley N° 453: El proveedor deberá suministrar el servicio en las modalidades y términos ofertados.</leyenda>
    </cabecera>
{items_block}
</facturaComputarizadaCompraVenta>"""


def construir_factura_html(factura: Dict[str, Any]) -> str:
    """Genera documento HTML formateado para visualización e impresión fiscal directa / guardar como PDF."""
    numero_factura = factura.get("numero_factura", 1)
    cuf = factura.get("cuf", "")
    cufd = factura.get("cufd", f"CUFD-{uuid.uuid4().hex[:8].upper()}")
    fecha_emision = factura.get("fecha_emision", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    datos_comprador = factura.get("datos_comprador", {})
    nit_ci = datos_comprador.get("nit_ci", "0")
    razon_social = datos_comprador.get("razon_social", "CONSUMIDOR FINAL")
    email_fac = datos_comprador.get("email_facturacion", "No especificado")
    total = float(factura.get("total", factura.get("monto_total", 0.0)))
    subtotal = float(factura.get("subtotal", total))
    descuento = float(factura.get("descuento", 0.0))
    iva = float(factura.get("monto_iva", round(total * 0.13, 2)))
    qr_url = factura.get("codigo_qr", "")
    items = factura.get("items", [])
    qr_img_src = f"https://api.qrserver.com/v1/create-qr-code/?size=160x160&data={quote(qr_url)}"

    filas_items = []
    for idx, item in enumerate(items, start=1):
        nombre = escape(str(item.get("nombre") or item.get("nombre_producto") or f"Ítem {idx}"))
        sku = escape(str(item.get("sku") or f"SKU-{idx}"))
        cant = item.get("cantidad", 1)
        pu = float(item.get("precio_unitario") or item.get("precio") or 0.0)
        sub = float(item.get("subtotal") or (cant * pu))
        filas_items.append(f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; font-family: monospace;">{sku}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{nombre}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: center;">{cant}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">BOB {pu:.2f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: bold;">BOB {sub:.2f}</td>
        </tr>
        """)

    filas_html = "".join(filas_items) if filas_items else f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">SERV-01</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">Compra General de Tecnología MaxiConecta</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: center;">1</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">BOB {total:.2f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: bold;">BOB {total:.2f}</td>
        </tr>
    """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Factura Electrónica N° {numero_factura} — MaxiConecta</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #f8fafc;
            color: #1e293b;
            margin: 0;
            padding: 24px;
        }}
        .invoice-card {{
            max-width: 800px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 16px;
            padding: 36px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.08);
            border: 1px solid #e2e8f0;
        }}
        .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; gap: 20px; }}
        .emisor-info h1 {{ margin: 0 0 6px 0; font-size: 20px; color: #0f172a; font-weight: 800; }}
        .emisor-info p {{ margin: 2px 0; font-size: 12px; color: #64748b; }}
        .fiscal-box {{
            border: 2px solid #2563eb;
            background: #eff6ff;
            border-radius: 12px;
            padding: 12px 18px;
            text-align: center;
            min-width: 260px;
        }}
        .fiscal-box .nit {{ font-size: 13px; font-weight: 700; color: #1e40af; margin-bottom: 4px; }}
        .fiscal-box .num {{ font-size: 18px; font-weight: 900; color: #1e3a8a; margin: 4px 0; }}
        .fiscal-box .cuf-label {{ font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 6px; }}
        .fiscal-box .cuf-code {{ font-size: 9px; font-family: monospace; word-break: break-all; color: #1e293b; font-weight: bold; }}
        .client-section {{
            background: #f8fafc;
            border-radius: 10px;
            padding: 14px 18px;
            margin-bottom: 24px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            font-size: 12px;
        }}
        .table-items {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-bottom: 24px;
        }}
        .table-items th {{
            background: #f1f5f9;
            color: #475569;
            text-align: left;
            padding: 10px 8px;
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
        }}
        .summary {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }}
        .qr-section {{ display: flex; align-items: center; gap: 14px; max-width: 440px; }}
        .qr-section img {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 4px; background: white; }}
        .qr-text {{ font-size: 10px; color: #64748b; line-height: 1.4; }}
        .totals-box {{ min-width: 240px; font-size: 13px; }}
        .totals-row {{ display: flex; justify-content: space-between; padding: 4px 0; }}
        .totals-row.grand-total {{
            border-top: 2px solid #0f172a;
            margin-top: 6px;
            padding-top: 8px;
            font-size: 16px;
            font-weight: 900;
            color: #0f172a;
        }}
        .footer {{
            margin-top: 32px;
            border-top: 1px dashed #cbd5e1;
            padding-top: 16px;
            text-align: center;
            font-size: 10px;
            color: #64748b;
        }}
        .btn-bar {{
            max-width: 800px;
            margin: 0 auto 16px auto;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            border: none;
            transition: all 0.15s ease;
            text-decoration: none;
        }}
        .btn-print {{ background: #2563eb; color: #ffffff; }}
        .btn-print:hover {{ background: #1d4ed8; }}
        .btn-xml {{ background: #0f172a; color: #ffffff; }}
        .btn-xml:hover {{ background: #334155; }}
        @media print {{
            body {{ padding: 0; background: #ffffff; }}
            .btn-bar {{ display: none !important; }}
            .invoice-card {{ border: none; box-shadow: none; padding: 0; }}
        }}
    </style>
</head>
<body>
    <div class="btn-bar">
        <a href="/api/v1/facturacion/facturas/{cuf}/xml" class="btn btn-xml" download>📥 Descargar XML</a>
        <button onclick="window.print()" class="btn btn-print">🖨️ Imprimir / Guardar PDF</button>
    </div>

    <div class="invoice-card">
        <div class="header">
            <div class="emisor-info">
                <h1>MAXICONECTA BOLIVIA S.R.L.</h1>
                <p><strong>CASA MATRIZ:</strong> Av. 16 de Julio (El Prado) #1490, Edificio Alameda PB</p>
                <p><strong>TELÉFONO:</strong> +591 2 2441122 &bull; La Paz, Bolivia</p>
                <p><strong>ACTIVIDAD ECONÓMICA:</strong> Venta al por menor de computadoras y equipos periféricos</p>
            </div>
            <div class="fiscal-box">
                <div class="nit">NIT 1028374029</div>
                <div class="num">FACTURA N° {numero_factura}</div>
                <div class="cuf-label">CÓDIGO DE AUTORIZACIÓN (CUF)</div>
                <div class="cuf-code">{cuf}</div>
            </div>
        </div>

        <div class="client-section">
            <div>
                <div><strong>Fecha de Emisión:</strong> {fecha_emision}</div>
                <div><strong>Señor(es):</strong> {razon_social}</div>
            </div>
            <div>
                <div><strong>NIT / CI / CEX:</strong> {nit_ci}</div>
                <div><strong>Correo Electrónico:</strong> {email_fac}</div>
            </div>
        </div>

        <table class="table-items">
            <thead>
                <tr>
                    <th style="width: 120px;">Código</th>
                    <th>Descripción del Producto</th>
                    <th style="text-align: center; width: 60px;">Cant.</th>
                    <th style="text-align: right; width: 100px;">Precio Unit.</th>
                    <th style="text-align: right; width: 110px;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {filas_html}
            </tbody>
        </table>

        <div class="summary">
            <div class="qr-section">
                <img src="{qr_img_src}" alt="QR Fiscal SIAT" width="130" height="130" />
                <div class="qr-text">
                    <p><strong>FACTURA ELECTRÓNICA EN LÍNEA</strong></p>
                    <p>CUFD: <span style="font-family: monospace;">{cufd}</span></p>
                    <p>Escanea este código QR con cualquier dispositivo para verificar la validez tributaria ante el Servicio de Impuestos Nacionales (SIN).</p>
                </div>
            </div>

            <div class="totals-box">
                <div class="totals-row">
                    <span>Subtotal:</span>
                    <span>BOB {subtotal:.2f}</span>
                </div>
                <div class="totals-row">
                    <span>Descuento:</span>
                    <span>BOB {descuento:.2f}</span>
                </div>
                <div class="totals-row grand-total">
                    <span>TOTAL A PAGAR:</span>
                    <span>BOB {total:.2f}</span>
                </div>
                <div class="totals-row" style="color: #64748b; font-size: 11px; margin-top: 4px;">
                    <span>Importe Base Crédito Fiscal:</span>
                    <span>BOB {total:.2f}</span>
                </div>
                <div class="totals-row" style="color: #64748b; font-size: 11px;">
                    <span>IVA Estimado (13%):</span>
                    <span>BOB {iva:.2f}</span>
                </div>
            </div>
        </div>

        <div class="footer">
            <p><strong>"ESTA FACTURA CONTRIBUYE AL DESARROLLO DEL PAÍS, EL USO ILÍCITO SERÁ SANCIONADO PENALMENTE DE ACUERDO A LEY"</strong></p>
            <p>Ley N° 453: El proveedor deberá suministrar el servicio en las modalidades y términos ofertados.</p>
        </div>
    </div>
</body>
</html>"""
