-- ==============================================================================
-- KAN-54 — Validación de pagos de una orden — migración idempotente
-- Opera sobre ordenes y pagos existentes.
-- ==============================================================================
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS caja_turno_id UUID REFERENCES caja_turnos(id);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS registrado_por TEXT;
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT;
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS codigo_autorizacion VARCHAR(60);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS token_pago VARCHAR(80);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS referencia VARCHAR(60);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS intento INT NOT NULL DEFAULT 1;
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS monto_reembolsado NUMERIC(12, 2) NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_pagos_orden ON pagos(orden_id, created_at);

-- Historial de pagos de la orden: cada cambio de estado de un pago (y la confirmación de la orden).
CREATE TABLE IF NOT EXISTS orden_pagos_historial (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID NOT NULL REFERENCES ordenes(id) ON DELETE CASCADE,
    pago_id UUID REFERENCES pagos(id) ON DELETE SET NULL,
    transaccion_id VARCHAR(100),
    tipo VARCHAR(10) NOT NULL DEFAULT 'pago' CHECK (tipo IN ('pago', 'orden', 'reembolso')),
    metodo VARCHAR(20),
    monto NUMERIC(12, 2),
    estado_anterior VARCHAR(40),
    estado_nuevo VARCHAR(40) NOT NULL,
    origen VARCHAR(20),
    motivo TEXT,
    usuario_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orden_pagos_historial_orden ON orden_pagos_historial(orden_id, created_at);

-- La autorización se realiza en el servicio; no exponer el historial por Data API.
ALTER TABLE public.orden_pagos_historial ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.orden_pagos_historial FROM anon, authenticated;
GRANT ALL ON public.orden_pagos_historial TO service_role;
