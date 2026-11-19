"""
Orquestador de transacciones compensatorias (patrón Saga).

Coordina flujos que tocan varios sistemas del ERP (Inventarios, Contabilidad,
Pagos…) y que no pueden compartir una transacción ACID: cada paso externo
declara cómo deshacerse (``undo``). Si un paso falla —por excepción o porque el
sistema externo responde con un estado de rechazo— se ejecutan, en orden
inverso, las compensaciones de los pasos que ya se habían completado, de modo
que ningún sistema quede en un estado inconsistente respecto a los demás.

Toda integración es simulada por el momento: los clientes ERP degradan a
respuestas ``mock_fallback`` cuando el sistema real no está disponible.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("maxiconecta.saga")

Accion = Callable[[], Awaitable[Dict[str, Any]]]
Compensacion = Callable[[Dict[str, Any]], Awaitable[Any]]

# Estados de negocio que, aunque la llamada de red haya "funcionado", son un
# rechazo funcional del sistema externo y deben disparar la compensación.
ESTADOS_DE_FALLO = frozenset({
    "RECHAZADA", "RECHAZADO", "ERROR", "FALLIDA", "FALLIDO", "DENEGADA", "DENEGADO",
})


@dataclass
class ResultadoPaso:
    nombre: str
    ok: bool
    resultado: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    compensado: bool = False
    error_compensacion: Optional[str] = None


@dataclass
class ResultadoSaga:
    transaccion: str
    exitosa: bool
    pasos: List[ResultadoPaso] = field(default_factory=list)
    paso_fallido: Optional[str] = None
    error: Optional[str] = None
    compensados: List[str] = field(default_factory=list)
    compensaciones_fallidas: List[str] = field(default_factory=list)

    @property
    def requiere_intervencion_manual(self) -> bool:
        """True si alguna compensación no pudo ejecutarse (estado potencialmente inconsistente)."""
        return bool(self.compensaciones_fallidas)

    def a_dict(self) -> Dict[str, Any]:
        return {
            "transaccion": self.transaccion,
            "exitosa": self.exitosa,
            "paso_fallido": self.paso_fallido,
            "error": self.error,
            "compensados": list(self.compensados),
            "compensaciones_fallidas": list(self.compensaciones_fallidas),
            "requiere_intervencion_manual": self.requiere_intervencion_manual,
            "pasos": [
                {
                    "nombre": p.nombre,
                    "ok": p.ok,
                    "compensado": p.compensado,
                    "error": p.error,
                }
                for p in self.pasos
            ],
        }


def _mensaje_de_fallo(resultado: Dict[str, Any]) -> Optional[str]:
    """Devuelve el motivo si ``resultado`` es un rechazo funcional; None si fue exitoso."""
    if not isinstance(resultado, dict):
        return None
    estado = str(resultado.get("status") or resultado.get("estado") or "").upper()
    if estado in ESTADOS_DE_FALLO:
        return str(resultado.get("mensaje") or resultado.get("error") or f"El sistema externo respondió {estado}")
    return None


class SagaOrchestrator:
    """Ejecuta pasos en orden y compensa en orden inverso ante el primer fallo."""

    def __init__(self, transaccion: str):
        self.transaccion = transaccion
        self._pasos: List[tuple] = []

    def paso(self, nombre: str, accion: Accion, compensacion: Optional[Compensacion] = None) -> "SagaOrchestrator":
        self._pasos.append((nombre, accion, compensacion))
        return self

    async def ejecutar(self) -> ResultadoSaga:
        saga = ResultadoSaga(transaccion=self.transaccion, exitosa=False)
        completados: List[tuple] = []  # (ResultadoPaso, compensacion)

        for nombre, accion, compensacion in self._pasos:
            try:
                resultado = await accion()
                motivo = _mensaje_de_fallo(resultado)
            except Exception as exc:  # noqa: BLE001 - cualquier fallo de integración compensa
                resultado, motivo = None, f"{type(exc).__name__}: {exc}"

            if motivo is not None:
                logger.error("[%s] Falló el paso '%s': %s", self.transaccion, nombre, motivo)
                saga.pasos.append(ResultadoPaso(nombre=nombre, ok=False, resultado=resultado, error=motivo))
                saga.paso_fallido = nombre
                saga.error = f"{nombre}: {motivo}"
                await self._compensar(saga, completados)
                return saga

            paso = ResultadoPaso(nombre=nombre, ok=True, resultado=resultado)
            saga.pasos.append(paso)
            completados.append((paso, compensacion))
            logger.info("[%s] Paso '%s' completado.", self.transaccion, nombre)

        saga.exitosa = True
        return saga

    async def _compensar(self, saga: ResultadoSaga, completados: List[tuple]) -> None:
        for paso, compensacion in reversed(completados):
            if compensacion is None:
                continue
            try:
                await compensacion(paso.resultado or {})
                paso.compensado = True
                saga.compensados.append(paso.nombre)
                logger.warning("[%s] Compensado el paso '%s'.", self.transaccion, paso.nombre)
            except Exception as exc:  # noqa: BLE001
                paso.error_compensacion = f"{type(exc).__name__}: {exc}"
                saga.compensaciones_fallidas.append(paso.nombre)
                logger.critical(
                    "[%s] FALLÓ la compensación del paso '%s' (%s). Requiere intervención manual.",
                    self.transaccion, paso.nombre, exc,
                )
