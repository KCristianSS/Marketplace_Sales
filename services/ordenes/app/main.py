import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from app.routers import router
    from app.routers_facturacion import router as facturacion_router
    from app.routers_pagos import router as pagos_router
    from app.routers_pagos_validacion import router as pagos_validacion_router
    from app.routers_reembolsos import router as reembolsos_router
    from app.routers_flete import router as flete_router
    from app.routers_vales import router as vales_router
    from app.routers_notificaciones import router as notificaciones_router
    from app.notificaciones import worker_notificaciones
    from app.routers_cotizaciones import router as cotizaciones_router
    from app.cotizaciones import worker_vencimiento_cotizaciones
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app.routers import router
    from backend.services.ordenes.app.routers_facturacion import router as facturacion_router
    from backend.services.ordenes.app.routers_pagos import router as pagos_router
    from backend.services.ordenes.app.routers_pagos_validacion import router as pagos_validacion_router
    from backend.services.ordenes.app.routers_reembolsos import router as reembolsos_router
    from backend.services.ordenes.app.routers_flete import router as flete_router
    from backend.services.ordenes.app.routers_vales import router as vales_router
    from backend.services.ordenes.app.routers_notificaciones import router as notificaciones_router
    from backend.services.ordenes.app.notificaciones import worker_notificaciones
    from backend.services.ordenes.app.routers_cotizaciones import router as cotizaciones_router
    from backend.services.ordenes.app.cotizaciones import worker_vencimiento_cotizaciones
from backend.shared.exceptions import MaxiConectaException, maxiconecta_exception_handler
from .routers_despachos import router as despachos_router
from backend.shared.despachos import lifespan_despachos


@asynccontextmanager
async def lifespan(_app):
    async with lifespan_despachos(_app):
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(worker_notificaciones(stop_event))
        quotes_task = asyncio.create_task(worker_vencimiento_cotizaciones(stop_event))
        try:
            yield
        finally:
            stop_event.set()
            await asyncio.gather(worker_task, quotes_task)


app = FastAPI(
    title="MaxiConecta - Microservicio de Órdenes y Ventas",
    description="Máquina de estados, cancelaciones, reversiones, cotizaciones B2B y pagos (RF-16, RF-27 a RF-39).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(MaxiConectaException, maxiconecta_exception_handler)
app.include_router(pagos_validacion_router)  # antes: /ordenes/pendiente y /ordenes/{id}/pagos
app.include_router(vales_router)
app.include_router(despachos_router)
app.include_router(router)
app.include_router(flete_router)
app.include_router(facturacion_router)
app.include_router(pagos_router)
app.include_router(reembolsos_router)
app.include_router(notificaciones_router)
app.include_router(cotizaciones_router)

@app.get("/health", tags=["Salud"])
async def health():
    return {"status": "ok", "service": "ms-ordenes", "port": 8005}


from backend.shared.audit_runtime import install_auditing
install_auditing(app)
