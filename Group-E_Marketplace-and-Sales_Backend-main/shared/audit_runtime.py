import asyncio
import logging
from contextlib import asynccontextmanager

from backend.shared.audit_context import AuditContextMiddleware
from backend.shared.config import settings

logger = logging.getLogger("uvicorn.error.audit")


def install_auditing(app, gateway=False):
    app.add_middleware(AuditContextMiddleware, gateway=gateway)
    if gateway:
        return
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        stop = asyncio.Event()
        async def retry_pending():
            from backend.shared.audit_spool import flush_pending
            from backend.shared.database import get_supabase_admin_client
            while not stop.is_set():
                try:
                    await asyncio.to_thread(flush_pending, get_supabase_admin_client())
                except Exception as exc:
                    logger.warning("AUDIT_REINTENTO_ERROR tipo=%s", type(exc).__name__)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass
        async with previous(application):
            task = asyncio.create_task(retry_pending()) if settings.ENVIRONMENT != "testing" else None
            try:
                yield
            finally:
                stop.set()
                if task:
                    try:
                        await asyncio.wait_for(task, timeout=5)
                    except asyncio.TimeoutError:
                        task.cancel()
    app.router.lifespan_context = lifespan
