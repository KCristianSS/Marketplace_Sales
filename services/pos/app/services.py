"""
Capa de servicios de negocio para el módulo POS — Gestión de Caja por Turno (RF-09).

Encapsula toda la lógica transaccional de apertura, control y cierre de caja,
delegando la persistencia a Supabase (tabla ``caja_turnos``) y al almacén en
memoria como fallback de desarrollo.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

# Cash-shift writes are server-side and RBAC-guarded at the gateway; the anon key is blocked by RLS on caja_turnos.
from backend.shared.database import get_supabase_admin_client as get_supabase_client

logger = logging.getLogger("maxiconecta.pos.services")

# ---------------------------------------------------------------------------
# Fallback en memoria para desarrollo local sin Supabase
# ---------------------------------------------------------------------------
# Almacén compartido con Órdenes (pago en efectivo, KAN-54) para que ambos vean el mismo turno.
from backend.shared.caja_store import CAJAS_EN_MEMORIA as _CAJAS_EN_MEMORIA
from backend.shared.caja_store import MOVIMIENTOS_EN_MEMORIA as _MOVIMIENTOS_EN_MEMORIA


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any) -> Decimal:
    """Convierte a Decimal de forma segura."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


# =====================================================================
# APERTURA DE CAJA
# =====================================================================

async def abrir_turno(
    sucursal_id: str,
    cajero_id: str,
    fondo_inicial: Decimal,
) -> Dict[str, Any]:
    """
    Abre un nuevo turno de caja.

    Reglas de negocio:
    - Un cajero no puede tener dos cajas abiertas al mismo tiempo.
    - El fondo inicial debe ser >= 0.

    Returns:
        Diccionario con los datos de la caja recién creada.

    Raises:
        ValueError si el cajero ya tiene una caja abierta.
    """
    supabase = get_supabase_client()

    if supabase:
        # Verificar caja abierta existente del cajero
        existing = (
            supabase.table("caja_turnos")
            .select("id")
            .eq("cajero_id", cajero_id)
            .eq("estado", "abierta")
            .execute()
        )
        if existing.data:
            raise ValueError(
                f"El cajero ya tiene una caja abierta (ID: {existing.data[0]['id']}). "
                "Debe cerrarla antes de aperturar una nueva."
            )

        caja_id = str(uuid.uuid4())
        row = {
            "id": caja_id,
            "sucursal_id": sucursal_id,
            "cajero_id": cajero_id,
            "fondo_inicial": float(fondo_inicial),
            "total_efectivo": 0,
            "total_tarjeta": 0,
            "total_qr": 0,
            "estado": "abierta",
        }
        result = supabase.table("caja_turnos").insert(row).execute()
        return result.data[0]
    else:
        # Fallback en memoria
        for caja in _CAJAS_EN_MEMORIA.values():
            if caja["cajero_id"] == cajero_id and caja["estado"] == "abierta":
                raise ValueError(
                    f"El cajero ya tiene una caja abierta (ID: {caja['id']}). "
                    "Debe cerrarla antes de aperturar una nueva."
                )

        caja_id = str(uuid.uuid4())
        caja = {
            "id": caja_id,
            "sucursal_id": sucursal_id,
            "cajero_id": cajero_id,
            "fondo_inicial": float(fondo_inicial),
            "total_efectivo": 0,
            "total_tarjeta": 0,
            "total_qr": 0,
            "estado": "abierta",
            "monto_cierre_real": None,
            "diferencia": None,
            "observaciones": None,
            "opened_at": _now_iso(),
            "closed_at": None,
        }
        _CAJAS_EN_MEMORIA[caja_id] = caja
        _MOVIMIENTOS_EN_MEMORIA[caja_id] = []
        return caja


# =====================================================================
# OBTENER CAJA
# =====================================================================

async def obtener_caja(caja_id: str) -> Optional[Dict[str, Any]]:
    """Retorna la caja por su ID, o None si no existe."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("caja_turnos")
            .select("*")
            .eq("id", caja_id)
            .execute()
        )
        return result.data[0] if result.data else None
    else:
        return _CAJAS_EN_MEMORIA.get(caja_id)


async def obtener_caja_activa(cajero_id: str) -> Optional[Dict[str, Any]]:
    """Retorna la caja abierta del cajero, o None si no tiene."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("caja_turnos")
            .select("*")
            .eq("cajero_id", cajero_id)
            .eq("estado", "abierta")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    else:
        for caja in _CAJAS_EN_MEMORIA.values():
            if caja["cajero_id"] == cajero_id and caja["estado"] == "abierta":
                return caja
        return None


# =====================================================================
# ACUMULAR TOTALES POR MÉTODO DE PAGO
# =====================================================================

async def acumular_venta(caja_id: str, metodo_pago: str, monto: Decimal) -> None:
    """
    Incrementa el acumulado del método de pago correspondiente en la caja.
    Llamado después de procesar cada venta POS.
    """
    campo_map = {
        "efectivo": "total_efectivo",
        "tarjeta": "total_tarjeta",
        "qr": "total_qr",
    }
    campo = campo_map.get(metodo_pago, "total_qr")

    supabase = get_supabase_client()
    if supabase:
        caja = await obtener_caja(caja_id)
        if not caja:
            return
        nuevo_total = _decimal(caja[campo]) + monto
        supabase.table("caja_turnos").update(
            {campo: float(nuevo_total)}
        ).eq("id", caja_id).execute()
    else:
        caja = _CAJAS_EN_MEMORIA.get(caja_id)
        if caja:
            caja[campo] = float(_decimal(caja[campo]) + monto)


# =====================================================================
# MOVIMIENTOS MANUALES (INGRESO / EGRESO)
# =====================================================================

async def registrar_movimiento(
    caja_id: str,
    tipo: str,
    monto: Decimal,
    descripcion: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persiste un movimiento de efectivo en ``caja_movimientos`` (KAN-342).

    ``tipo`` canónico: ``entrada`` | ``retiro`` (se aceptan los alias heredados ``ingreso``/``egreso``).
    ``extra`` agrega columnas (motivo, comprobante, supervisor, etc.).
    """
    tipo = {"ingreso": "entrada", "egreso": "retiro"}.get(tipo, tipo)
    supabase = get_supabase_client()
    mov = {
        "id": str(uuid.uuid4()),
        "caja_turno_id": caja_id,
        "tipo": tipo,
        "monto": float(monto),
        "motivo": descripcion,
        "descripcion": descripcion,
        **(extra or {}),
    }
    if supabase:
        fila = {k: v for k, v in mov.items() if k != "descripcion"}
        return supabase.table("caja_movimientos").insert(fila).execute().data[0]
    mov["created_at"] = _now_iso()
    _MOVIMIENTOS_EN_MEMORIA.setdefault(caja_id, []).append(mov)
    return mov


async def listar_movimientos(caja_id: str) -> List[Dict[str, Any]]:
    """Retorna los movimientos de efectivo de una caja (orden cronológico)."""
    supabase = get_supabase_client()
    if supabase:
        data = (
            supabase.table("caja_movimientos").select("*").eq("caja_turno_id", caja_id).order("created_at").execute().data
        )
    else:
        data = list(_MOVIMIENTOS_EN_MEMORIA.get(caja_id, []))
    for m in data:
        m.setdefault("descripcion", m.get("motivo"))
    return data


def calcular_movimientos_netos(movimientos: List[Dict[str, Any]]) -> Dict[str, Decimal]:
    """Totales de entradas (+) y retiros (−) y su neto."""
    entradas = sum((_decimal(m["monto"]) for m in movimientos if m["tipo"] == "entrada"), Decimal("0.00"))
    retiros = sum((_decimal(m["monto"]) for m in movimientos if m["tipo"] == "retiro"), Decimal("0.00"))
    return {"entradas": entradas, "retiros": retiros, "neto": entradas - retiros}


async def movimientos_netos(caja_id: str) -> Dict[str, Decimal]:
    """Cálculo de movimientos netos consumible por otras historias (arqueo, KAN-341)."""
    return calcular_movimientos_netos(await listar_movimientos(caja_id))


# =====================================================================
# CIERRE DE CAJA Y ARQUEO
# =====================================================================

async def cerrar_turno(
    caja_id: str,
    monto_cierre_real: Decimal,
    observaciones: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cierra el turno de caja y calcula la diferencia del arqueo.

    Fórmula:
        total_esperado = fondo_inicial + total_efectivo + ingresos_manuales - egresos_manuales
        diferencia     = monto_cierre_real - total_esperado

    Returns:
        Diccionario con el resumen completo del arqueo.

    Raises:
        ValueError si la caja no existe o no está abierta.
    """
    caja = await obtener_caja(caja_id)
    if not caja:
        raise ValueError("Caja no encontrada")
    if caja["estado"] != "abierta":
        raise ValueError(
            f"La caja no está abierta (estado actual: {caja['estado']}). "
            "Solo se puede cerrar una caja en estado 'abierta'."
        )

    # Calcular totales de movimientos manuales
    movimientos = await listar_movimientos(caja_id)
    netos = calcular_movimientos_netos(movimientos)
    total_ingresos, total_egresos = netos["entradas"], netos["retiros"]

    total_esperado = (
        _decimal(caja["fondo_inicial"])
        + _decimal(caja["total_efectivo"])
        + total_ingresos
        - total_egresos
    )
    diferencia = monto_cierre_real - total_esperado
    closed_at = _now_iso()

    supabase = get_supabase_client()
    if supabase:
        supabase.table("caja_turnos").update({
            "estado": "cerrada",
            "monto_cierre_real": float(monto_cierre_real),
            "diferencia": float(diferencia),
            "observaciones": observaciones,
            "closed_at": closed_at,
        }).eq("id", caja_id).execute()
    else:
        caja_mem = _CAJAS_EN_MEMORIA.get(caja_id)
        if caja_mem:
            caja_mem["estado"] = "cerrada"
            caja_mem["monto_cierre_real"] = float(monto_cierre_real)
            caja_mem["diferencia"] = float(diferencia)
            caja_mem["observaciones"] = observaciones
            caja_mem["closed_at"] = closed_at

    return {
        "caja_turno_id": caja_id,
        "cajero_id": caja["cajero_id"],
        "sucursal_id": caja["sucursal_id"],
        "fondo_inicial": caja["fondo_inicial"],
        "total_efectivo": caja["total_efectivo"],
        "total_tarjeta": caja["total_tarjeta"],
        "total_qr": caja["total_qr"],
        "total_ingresos_manuales": float(total_ingresos),
        "total_egresos_manuales": float(total_egresos),
        "total_esperado": float(total_esperado),
        "monto_cierre_real": float(monto_cierre_real),
        "diferencia": float(diferencia),
        "estado": "cerrada",
        "observaciones": observaciones,
        "opened_at": caja.get("opened_at"),
        "closed_at": closed_at,
    }


# =====================================================================
# HISTORIAL DE CAJAS
# =====================================================================

async def obtener_historial(
    cajero_id: str,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Retorna el historial de cajas de un cajero, ordenado por fecha desc."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("caja_turnos")
            .select("*")
            .eq("cajero_id", cajero_id)
            .order("opened_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data
    else:
        cajas = [
            c for c in _CAJAS_EN_MEMORIA.values()
            if c["cajero_id"] == cajero_id
        ]
        cajas.sort(key=lambda c: c.get("opened_at", ""), reverse=True)
        return cajas[offset:offset + limit]


# =====================================================================
# HISTORIA KAN-10 / KAN-345: DESCUENTO MANUAL SERVICE (KAN-360, KAN-362)
# =====================================================================

import hashlib
from datetime import timedelta

def _hash_pin(pin: str) -> str:
    return hashlib.sha256(str(pin).strip().encode("utf-8")).hexdigest()

def _verificar_pin(pin: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    # Verificación directa por SHA-256
    if _hash_pin(pin) == stored_hash:
        return True
    # Verificación por bcrypt si el hash tiene formato modular crypt
    if stored_hash.startswith("$2"):
        try:
            from backend.shared.security import verify_password
            return verify_password(pin, stored_hash)
        except Exception:
            pass
    # Compatibilidad plana de desarrollo
    return str(pin).strip() == stored_hash


# Almacén de supervisores por defecto con PIN seguro hasheado (SHA-256)
_SUPERVISOR_PINS_DEFAULT: Dict[str, Dict[str, Any]] = {
    "supervisor": {
        "supervisor_id": "a1111111-1111-1111-1111-111111111111",
        "supervisor_username": "supervisor",
        "supervisor_nombre": "Carlos Ramos (Supervisor de Turno)",
        "pin_hash": _hash_pin("1234"),
        "rol": "administrador",
        "intentos_fallidos": 0,
        "bloqueado_hasta": None,
        "activo": True,
    },
    "admin": {
        "supervisor_id": "a2222222-2222-2222-2222-222222222222",
        "supervisor_username": "admin",
        "supervisor_nombre": "Administrador Principal de Tienda",
        "pin_hash": _hash_pin("4321"),
        "rol": "administrador",
        "intentos_fallidos": 0,
        "bloqueado_hasta": None,
        "activo": True,
    },
    "gerente": {
        "supervisor_id": "a3333333-3333-3333-3333-333333333333",
        "supervisor_username": "gerente",
        "supervisor_nombre": "Mariana López (Gerente Comercial)",
        "pin_hash": _hash_pin("8888"),
        "rol": "gerente_comercial",
        "intentos_fallidos": 0,
        "bloqueado_hasta": None,
        "activo": True,
    },
}

_SUPERVISOR_PINS_MEMORIA: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in _SUPERVISOR_PINS_DEFAULT.items()}
_AUTORIZACIONES_DESCUENTO_MEMORIA: Dict[str, Dict[str, Any]] = {}
_AUDIT_LOGS_MEMORIA: List[Dict[str, Any]] = []

MAX_DESCUENTO_PORCENTAJE = Decimal("30.00")
DURACION_TOKEN_MINUTOS = 2
MINUTOS_BLOQUEO = 5
MAX_INTENTOS_FALLIDOS = 3


class DescuentoManualService:
    """
    Servicio de Autorización de Descuentos Manuales en POS (KAN-360).
    Aplica tope del 30%, bloqueo temporal por 3 intentos fallidos de PIN (5 min),
    tokens de un solo uso con expiración a los 2 minutos y trazabilidad en audit_logs.
    """

    @classmethod
    async def obtener_supervisor(cls, username: str) -> Optional[Dict[str, Any]]:
        clean_user = username.strip().lower()
        supabase = get_supabase_client()
        if supabase:
            try:
                res = (
                    supabase.table("pos_supervisor_pins")
                    .select("*")
                    .eq("supervisor_username", clean_user)
                    .eq("activo", True)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception:
                logger.warning("No se pudo consultar pos_supervisor_pins en Supabase, recurriendo a memoria.")
        return _SUPERVISOR_PINS_MEMORIA.get(clean_user)

    @classmethod
    async def actualizar_supervisor(cls, username: str, campos: Dict[str, Any]) -> None:
        clean_user = username.strip().lower()
        if clean_user in _SUPERVISOR_PINS_MEMORIA:
            _SUPERVISOR_PINS_MEMORIA[clean_user].update(campos)
        supabase = get_supabase_client()
        if supabase:
            try:
                supabase.table("pos_supervisor_pins").update(campos).eq("supervisor_username", clean_user).execute()
            except Exception:
                pass

    @classmethod
    async def registrar_audit_log(
        cls,
        user_id: Optional[str],
        user_role: str,
        action: str,
        entity: str,
        entity_id: Optional[str],
        payload: Dict[str, Any],
    ) -> None:
        from backend.shared.audit import registrar_auditoria
        log_entry = registrar_auditoria(get_supabase_client(), current_user={"user_id": user_id, "role": user_role},
            accion=action, entidad=entity, entidad_id=entity_id, despues=payload)
        _AUDIT_LOGS_MEMORIA.append(log_entry)

    @classmethod
    async def validar_supervisor_pin(cls, supervisor_username: str, pin: str) -> Dict[str, Any]:
        supervisor = await cls.obtener_supervisor(supervisor_username)
        if not supervisor:
            raise ValueError(f"Supervisor '{supervisor_username}' no registrado o inactivo.")

        rol_sup = str(supervisor.get("rol", "")).lower()
        if rol_sup not in {"administrador", "gerente_comercial", "supervisor"}:
            raise ValueError(f"El usuario '{supervisor_username}' no posee rol de supervisión autorizado.")

        # Criterio 2: Verificar si está bloqueado por intentos fallidos
        ahora = datetime.now(timezone.utc)
        bloqueado_hasta_raw = supervisor.get("bloqueado_hasta")
        if bloqueado_hasta_raw:
            if isinstance(bloqueado_hasta_raw, str):
                bloqueado_hasta = datetime.fromisoformat(bloqueado_hasta_raw.replace("Z", "+00:00"))
            else:
                bloqueado_hasta = bloqueado_hasta_raw
            if bloqueado_hasta > ahora:
                minutos_restantes = max(1, int((bloqueado_hasta - ahora).total_seconds() // 60) + 1)
                raise ValueError(
                    f"Supervisor temporalmente bloqueado por superar 3 intentos fallidos de PIN. "
                    f"Intente nuevamente en {minutos_restantes} minuto(s)."
                )

        # Validación del PIN
        stored_hash = supervisor.get("pin_hash", "")
        pin_valido = _verificar_pin(pin, stored_hash)

        if not pin_valido:
            nuevos_intentos = int(supervisor.get("intentos_fallidos", 0)) + 1
            if nuevos_intentos >= MAX_INTENTOS_FALLIDOS:
                bloqueo = ahora + timedelta(minutes=MINUTOS_BLOQUEO)
                await cls.actualizar_supervisor(supervisor_username, {
                    "intentos_fallidos": nuevos_intentos,
                    "bloqueado_hasta": bloqueo.isoformat(),
                })
                await cls.registrar_audit_log(
                    user_id=supervisor.get("supervisor_id"),
                    user_role=rol_sup,
                    action="SUPERVISOR_BLOQUEADO_PIN",
                    entity="pos_supervisor_pins",
                    entity_id=supervisor.get("supervisor_id"),
                    payload={"motivo": "3 intentos fallidos consecutivos de PIN", "bloqueado_hasta": bloqueo.isoformat()},
                )
                raise ValueError(
                    "PIN incorrecto. El supervisor ha sido bloqueado por 5 minutos tras 3 intentos fallidos seguidos."
                )
            else:
                await cls.actualizar_supervisor(supervisor_username, {"intentos_fallidos": nuevos_intentos})
                restantes = MAX_INTENTOS_FALLIDOS - nuevos_intentos
                raise ValueError(
                    f"PIN incorrecto. Le queda(n) {restantes} intento(s) antes del bloqueo temporal de 5 minutos."
                )

        # PIN Correcto -> Resetear intentos fallidos y generar token de 2 minutos
        await cls.actualizar_supervisor(supervisor_username, {
            "intentos_fallidos": 0,
            "bloqueado_hasta": None,
        })

        return supervisor

    @classmethod
    async def autorizar_descuento(
        cls,
        supervisor_username: str,
        pin: str,
        tipo: str,
        porcentaje: Decimal,
        monto_base: Decimal,
        motivo: str,
        item_sku: Optional[str] = None,
        cajero_id: Optional[str] = None,
        cajero_nombre: Optional[str] = None,
        sucursal_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Valida las credenciales del supervisor y genera un token de un solo uso.
        Criterios de Aceptación KAN-345:
        - Si el porcentaje supera el tope configurado (30%), rechaza con mensaje claro.
        - Si el supervisor está bloqueado por 3 intentos previos, rechaza indicando tiempo restante.
        - Si el PIN es incorrecto, suma intento y bloquea 5 minutos al 3er fallo consecutivo.
        - Si el PIN es correcto, resetea intentos y emite token válido por 2 minutos.
        """
        # Criterio 3: Tope máximo configurable (30%)
        if porcentaje <= 0 or porcentaje > MAX_DESCUENTO_PORCENTAJE:
            raise ValueError(
                f"El porcentaje de descuento solicitado ({porcentaje}%) supera el tope máximo permitido de {MAX_DESCUENTO_PORCENTAJE}%."
            )

        if not motivo or len(motivo.strip()) < 3:
            raise ValueError("El motivo del descuento manual es obligatorio (ej. empaque dañado, promoción excepcional).")

        supervisor = await cls.validar_supervisor_pin(supervisor_username, pin)
        rol_sup = str(supervisor.get("rol", "")).lower()
        ahora = datetime.now(timezone.utc)

        token_id = str(uuid.uuid4())
        autorizacion_token = f"AUTH-DESC-{uuid.uuid4().hex[:8].upper()}"
        expires_at = ahora + timedelta(minutes=DURACION_TOKEN_MINUTOS)
        monto_desc = (monto_base * (porcentaje / Decimal("100.00"))).quantize(Decimal("0.01"))

        registro = {
            "id": token_id,
            "autorizacion_token": autorizacion_token,
            "tipo": tipo,
            "item_sku": item_sku,
            "porcentaje_descuento": float(porcentaje),
            "monto_base": float(monto_base),
            "monto_descuento": float(monto_desc),
            "motivo": motivo.strip(),
            "supervisor_id": str(supervisor["supervisor_id"]),
            "supervisor_nombre": supervisor["supervisor_nombre"],
            "cajero_id": str(cajero_id) if cajero_id else None,
            "cajero_nombre": cajero_nombre,
            "sucursal_id": str(sucursal_id) if sucursal_id else None,
            "usado": False,
            "orden_id": None,
            "expires_at": expires_at.isoformat(),
            "created_at": ahora.isoformat(),
        }

        _AUTORIZACIONES_DESCUENTO_MEMORIA[autorizacion_token] = registro

        supabase = get_supabase_client()
        if supabase:
            try:
                supabase.table("pos_descuentos_manuales").insert(registro).execute()
            except Exception:
                logger.exception("No se pudo insertar en pos_descuentos_manuales de Supabase")

        await cls.registrar_audit_log(
            user_id=supervisor["supervisor_id"],
            user_role=rol_sup,
            action="DESCUENTO_MANUAL_AUTORIZADO",
            entity="pos_descuentos_manuales",
            entity_id=token_id,
            payload={
                "autorizacion_token": autorizacion_token,
                "tipo": tipo,
                "item_sku": item_sku,
                "porcentaje": float(porcentaje),
                "monto_descuento": float(monto_desc),
                "motivo": motivo,
                "supervisor": supervisor["supervisor_nombre"],
                "expires_at": expires_at.isoformat(),
            },
        )

        return {
            "autorizacion_id": autorizacion_token,
            "autorizado": True,
            "supervisor_id": supervisor["supervisor_id"],
            "supervisor_nombre": supervisor["supervisor_nombre"],
            "tipo": tipo,
            "item_sku": item_sku,
            "porcentaje": porcentaje,
            "monto_base": monto_base,
            "monto_descuento": monto_desc,
            "motivo": motivo,
            "expires_at": expires_at,
            "mensaje": f"Descuento de {porcentaje}% autorizado por {supervisor['supervisor_nombre']}. Vigente por 2 minutos.",
        }

    @classmethod
    async def validar_y_consumir_autorizacion(
        cls,
        autorizacion_token: str,
        orden_id: str,
        tipo_esperado: str,
        item_sku_esperado: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Criterios 1, 4 y 5 de KAN-345:
        - Si no hay autorización válida o vigente, no se aplica el descuento.
        - La autorización es de UN SOLO USO y vence a los 2 minutos.
        - Registra la aplicación en audit_logs.
        """
        clean_token = autorizacion_token.strip()
        auth_data = None
        supabase = get_supabase_client()
        if supabase:
            try:
                res = (
                    supabase.table("pos_descuentos_manuales")
                    .select("*")
                    .eq("autorizacion_token", clean_token)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    auth_data = res.data[0]
            except Exception:
                pass
        if not auth_data:
            auth_data = _AUTORIZACIONES_DESCUENTO_MEMORIA.get(clean_token)

        if not auth_data:
            raise ValueError(f"Autorización de descuento '{clean_token}' no encontrada.")

        # Criterio 5: De un solo uso
        if auth_data.get("usado"):
            raise ValueError(
                f"La autorización '{clean_token}' ya fue utilizada previamente en la orden {auth_data.get('orden_id')}."
            )

        # Criterio 5: Vence a los 2 minutos
        ahora = datetime.now(timezone.utc)
        exp_raw = auth_data["expires_at"]
        if isinstance(exp_raw, str):
            expires_at = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
        else:
            expires_at = exp_raw
        if ahora > expires_at:
            raise ValueError(
                f"La autorización de descuento '{clean_token}' ha expirado (venció a los 2 minutos de ser emitida)."
            )

        # Validar consistencia de tipo e ítem
        if auth_data["tipo"] != tipo_esperado:
            raise ValueError(
                f"El tipo de descuento de la autorización ({auth_data['tipo']}) no coincide con el solicitado ({tipo_esperado})."
            )

        if tipo_esperado == "item" and item_sku_esperado:
            if auth_data.get("item_sku") and auth_data["item_sku"].upper() != item_sku_esperado.upper():
                raise ValueError(
                    f"La autorización '{clean_token}' fue emitida para el SKU {auth_data.get('item_sku')} y no para {item_sku_esperado}."
                )

        # Consumir: marcar como usado
        auth_data["usado"] = True
        auth_data["orden_id"] = str(orden_id)
        if clean_token in _AUTORIZACIONES_DESCUENTO_MEMORIA:
            _AUTORIZACIONES_DESCUENTO_MEMORIA[clean_token]["usado"] = True
            _AUTORIZACIONES_DESCUENTO_MEMORIA[clean_token]["orden_id"] = str(orden_id)

        if supabase:
            try:
                supabase.table("pos_descuentos_manuales").update({
                    "usado": True,
                    "orden_id": str(orden_id),
                }).eq("autorizacion_token", clean_token).execute()
            except Exception:
                pass

        # Criterio 4: Registro en audit_logs
        await cls.registrar_audit_log(
            user_id=auth_data.get("supervisor_id"),
            user_role="supervisor_autorizador",
            action="DESCUENTO_MANUAL_APLICADO_TICKET",
            entity="pos_ventas",
            entity_id=str(orden_id),
            payload={
                "orden_id": str(orden_id),
                "autorizacion_token": clean_token,
                "tipo": auth_data["tipo"],
                "item_sku": auth_data.get("item_sku"),
                "monto_descuento": float(auth_data["monto_descuento"]),
                "porcentaje": float(auth_data["porcentaje_descuento"]),
                "motivo": auth_data["motivo"],
                "supervisor_nombre": auth_data["supervisor_nombre"],
            },
        )

        return auth_data

