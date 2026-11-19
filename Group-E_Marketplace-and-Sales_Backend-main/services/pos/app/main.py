from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from app.routers import router
    from app.routers_caja import router as caja_router
except (ModuleNotFoundError, ImportError):
    from backend.services.pos.app.routers import router
    from backend.services.pos.app.routers_caja import router as caja_router
from backend.shared.exceptions import MaxiConectaException, maxiconecta_exception_handler

app = FastAPI(
    title="MaxiConecta - Microservicio de Puntos de Venta (POS)",
    description="Cajas físicas, turnos, comprobantes y suspensión de ventas (RF-09 a RF-12).",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(MaxiConectaException, maxiconecta_exception_handler)
app.include_router(router)
app.include_router(caja_router)

@app.get("/health", tags=["Salud"])
async def health():
    return {"status": "ok", "service": "ms-pos", "port": 8002}


from backend.shared.audit_runtime import install_auditing
install_auditing(app)
