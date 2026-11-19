-- ==============================================================================
-- KAN-55 — Reembolsos totales o parciales — migración idempotente de la tabla reembolsos
-- Opera sobre cualquier pago aprobado (pagos). Requiere KAN-54 (columna pagos.monto_reembolsado).
-- ==============================================================================
CREATE TABLE IF NOT EXISTS reembolsos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pago_id UUID NOT NULL REFERENCES pagos(id),
    orden_id UUID NOT NULL REFERENCES ordenes(id),
    metodo metodo_pago_enum NOT NULL,
    monto NUMERIC(12, 2) NOT NULL CHECK (monto > 0),
    motivo VARCHAR(255) NOT NULL,
    estado VARCHAR(12) NOT NULL DEFAULT 'solicitado',
    intento INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
-- Columnas agregadas de forma idempotente (por si la tabla ya existía en otra versión).
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS error TEXT;
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS referencia_externa VARCHAR(80);
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS nota_credito VARCHAR(40);
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS numero_comprobante VARCHAR(40);
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS comprobante JSONB;
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS contabilidad JSONB;
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS solicitado_por TEXT;
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_reembolsos_estado') THEN
        ALTER TABLE reembolsos ADD CONSTRAINT chk_reembolsos_estado
            CHECK (estado IN ('solicitado', 'procesando', 'completado', 'fallido'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_reembolsos_pago ON reembolsos(pago_id);
CREATE INDEX IF NOT EXISTS idx_reembolsos_orden ON reembolsos(orden_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reembolsos_estado ON reembolsos(estado, created_at DESC);

-- Solo el servicio autorizado accede a los datos de reembolsos.
ALTER TABLE public.reembolsos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reembolsos FROM anon, authenticated;
GRANT ALL ON public.reembolsos TO service_role;
