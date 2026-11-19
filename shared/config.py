import os
from typing import Optional

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Settings(BaseModel):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    AUDIT_SPOOL_PATH: str = os.getenv("AUDIT_SPOOL_PATH", ".audit/events.sqlite3")

    # Supabase / DB
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://tu-proyecto.supabase.co")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "anon-key")
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY", None)
    SUPABASE_PUBLISHABLE_KEY: Optional[str] = os.getenv("SUPABASE_PUBLISHABLE_KEY", None)
    SUPABASE_SECRET_KEY: Optional[str] = os.getenv("SUPABASE_SECRET_KEY", None)
    SUPABASE_JWKS_URL: Optional[str] = os.getenv("SUPABASE_JWKS_URL", None)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/maxiconecta")

    # Correo transaccional para notificaciones de órdenes (KAN-46)
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: Optional[str] = os.getenv("SMTP_FROM_EMAIL")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-dev-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    VALES_CODIGO_SECRET: str = os.getenv("VALES_CODIGO_SECRET", "")
    PAGOS_WEBHOOK_SECRET: str = os.getenv("PAGOS_WEBHOOK_SECRET", "")

    # URLs Microservicios
    MS_CATALOGO_URL: str = os.getenv("MS_CATALOGO_URL") or ("http://" + os.environ["MS_CATALOGO_HOSTPORT"] if os.getenv("MS_CATALOGO_HOSTPORT") else "http://localhost:8001")
    MS_POS_URL: str = os.getenv("MS_POS_URL", "http://localhost:8002")
    MS_CARRITO_URL: str = os.getenv("MS_CARRITO_URL", "http://localhost:8003")
    MS_CLIENTES_URL: str = os.getenv("MS_CLIENTES_URL") or ("http://" + os.environ["MS_CLIENTES_HOSTPORT"] if os.getenv("MS_CLIENTES_HOSTPORT") else "http://localhost:8004")
    MS_ORDENES_URL: str = os.getenv("MS_ORDENES_URL", "http://localhost:8005")
    MS_REPORTES_URL: str = os.getenv("MS_REPORTES_URL", "http://localhost:8006")

    # ERP Externos (RIO)
    ERP_INVENTARIOS_URL: str = os.getenv("ERP_INVENTARIOS_URL", "http://localhost:9001")
    ERP_PAGOS_URL: str = os.getenv("ERP_PAGOS_URL", "http://localhost:9002")
    ERP_CONTABILIDAD_URL: str = os.getenv("ERP_CONTABILIDAD_URL", "http://localhost:9003")
    ERP_CRM_URL: str = os.getenv("ERP_CRM_URL", "http://localhost:9004")
    ERP_ENTREGAS_URL: str = os.getenv("ERP_ENTREGAS_URL", "http://localhost:9005")
    ERP_PRODUCCION_URL: str = os.getenv("ERP_PRODUCCION_URL", "http://localhost:9006")
    ERP_TIMEOUT_SECONDS: float = float(os.getenv("ERP_TIMEOUT_SECONDS", "5.0"))

    # Caja / POS (KAN-342): retiro de efectivo que exige confirmación de un supervisor
    CAJA_LIMITE_SEGURIDAD_RETIRO: float = float(os.getenv("CAJA_LIMITE_SEGURIDAD_RETIRO", "2000"))

    # Pagos (KAN-54): secreto compartido para firmar (HMAC-SHA256) los webhooks de la pasarela simulada
    PAGOS_WEBHOOK_SECRET: str = os.getenv("PAGOS_WEBHOOK_SECRET", "maxiconecta-webhook-dev-secret")

    # Programa de fidelización (RF-25)
    FIDELIDAD_BOB_POR_PUNTO: int = int(os.getenv("FIDELIDAD_BOB_POR_PUNTO", "10"))
    FIDELIDAD_VALOR_PUNTO_BOB: float = float(os.getenv("FIDELIDAD_VALOR_PUNTO_BOB", "0.5"))

    # Google Cloud Pub/Sub (US-40 / RF-40 / KAN-56)
    PUBSUB_TOPIC_ENTREGAS: str = os.getenv("PUBSUB_TOPIC_ENTREGAS", os.getenv("PUBSUB_TOPIC_INVENTARIOS", "projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e"))
    PUBSUB_TOPIC_RESPUESTAS_ENTREGAS: str = os.getenv("PUBSUB_TOPIC_RESPUESTAS_ENTREGAS", os.getenv("PUBSUB_TOPIC_ENTREGAS", "projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e"))
    PUBSUB_SUBSCRIPTION_ENTREGAS: str = os.getenv("PUBSUB_SUBSCRIPTION_ENTREGAS", "")
    PUBSUB_TOPIC_CRM: str = os.getenv("PUBSUB_TOPIC_CRM", os.getenv("PUBSUB_TOPIC_ENTREGAS", os.getenv("PUBSUB_TOPIC_INVENTARIOS", "projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e")))
    PUBSUB_SUBSCRIPTION_CRM: str = os.getenv("PUBSUB_SUBSCRIPTION_CRM", "")
    CRM_WORKER_ENABLED: bool = os.getenv("CRM_WORKER_ENABLED", "true").lower() in {"true", "1", "yes"}
    DESPACHOS_WORKER_ENABLED: bool = os.getenv("DESPACHOS_WORKER_ENABLED", "true").lower() in {"true", "1", "yes"}
    PUBSUB_COTIZACIONES_SIMULACION_ENABLED: bool = os.getenv("PUBSUB_COTIZACIONES_SIMULACION_ENABLED", "false").lower() in {"true", "1", "yes"}
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "project-a96e5fe1-5ba6-4698-a85")
    PUBSUB_TOPIC_INVENTARIOS: str = os.getenv(
        "PUBSUB_TOPIC_INVENTARIOS",
        "projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e"
    )
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "service-account.json"
    )

settings = Settings()

