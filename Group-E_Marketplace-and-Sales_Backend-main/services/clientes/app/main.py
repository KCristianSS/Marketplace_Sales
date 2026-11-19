from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from app.services_crm_sync import lifespan_crm
except (ModuleNotFoundError, ImportError):
    from backend.services.clientes.app.services_crm_sync import lifespan_crm
try:
    from app.routers import router
    from app.routers_admin_usuarios import router as router_admin_usuarios
    from app.routers_crm_sync import router as router_crm_sync
except (ModuleNotFoundError, ImportError):
    from backend.services.clientes.app.routers import router
    from backend.services.clientes.app.routers_admin_usuarios import router as router_admin_usuarios
    from backend.services.clientes.app.routers_crm_sync import router as router_crm_sync
from backend.shared.exceptions import MaxiConectaException, maxiconecta_exception_handler
from backend.shared.routers_auditoria import router as auditoria_router
from .routers_corporativos import router as corporativos_router

app = FastAPI(
    lifespan=lifespan_crm,
    title="MaxiConecta - Microservicio de Clientes y Administración",
    description="Identidad, perfiles, direcciones, fidelización, gestión de usuarios internos y sincronización con CRM vía Pub/Sub (RF-22 a RF-26, RF-49, RF-14).",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(MaxiConectaException, maxiconecta_exception_handler)
app.include_router(corporativos_router)
app.include_router(router)
app.include_router(router_admin_usuarios)
app.include_router(router_crm_sync)
app.include_router(auditoria_router)


# Soporte para clientes que consumen con o sin prefijo /api
from fastapi import APIRouter
secondary_router = APIRouter(prefix="/v1/clientes", tags=["Clientes y Autenticación (v1)"])
for route in router.routes:
    pass


@app.get("/health", tags=["Salud"])
async def health():
    return {"status": "ok", "service": "ms-clientes", "port": 8004}


from backend.shared.audit_runtime import install_auditing
install_auditing(app)
