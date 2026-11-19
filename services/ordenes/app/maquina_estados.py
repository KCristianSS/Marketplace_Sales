"""Máquina de estados de la orden (RF-28). Única fuente de las transiciones válidas."""
from backend.shared.exceptions import InvalidOrderTransitionException


class MaquinaEstados:
    TRANSICIONES = {
        "pendiente": ["confirmada", "cancelada"],
        "confirmada": ["en_preparacion", "cancelada"],
        "en_preparacion": ["despachada", "cancelada"],
        "despachada": ["entregada"],
        "entregada": [],
        "cancelada": [],
    }

    @classmethod
    def puede_transicionar(cls, actual: str, nuevo: str) -> bool:
        return nuevo in cls.TRANSICIONES.get(actual, [])

    @classmethod
    def validar(cls, actual: str, nuevo: str) -> None:
        if not cls.puede_transicionar(actual, nuevo):
            raise InvalidOrderTransitionException(actual, nuevo)
