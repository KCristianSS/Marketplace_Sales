-- Metadatos adicionales. No modifica las tablas ni transacciones comerciales.
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS actor_id text;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS request_id uuid;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS request_method text;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS request_path text;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS user_agent text;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'legacy';
ALTER TABLE public.audit_logs ALTER COLUMN source SET DEFAULT 'application';
CREATE INDEX IF NOT EXISTS idx_audit_entity_date ON public.audit_logs(entity, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_date ON public.audit_logs(actor_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_request ON public.audit_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_date_id ON public.audit_logs(created_at DESC, id DESC);
