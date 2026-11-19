-- Tabla usada por KAN-342 en instalaciones que aún no aplicaron la migración POS.
CREATE TABLE IF NOT EXISTS public.caja_movimientos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    caja_turno_id UUID NOT NULL REFERENCES public.caja_turnos(id),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('entrada', 'retiro')),
    monto NUMERIC(12, 2) NOT NULL CHECK (monto > 0),
    motivo VARCHAR(255) NOT NULL CHECK (char_length(btrim(motivo)) >= 3),
    requiere_supervisor BOOLEAN NOT NULL DEFAULT FALSE,
    supervisor_id TEXT,
    registrado_por TEXT,
    numero_comprobante VARCHAR(40),
    comprobante JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_caja_movimientos_turno ON public.caja_movimientos(caja_turno_id, created_at);

ALTER TABLE public.caja_movimientos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.caja_movimientos FROM anon, authenticated;
GRANT ALL ON public.caja_movimientos TO service_role;
