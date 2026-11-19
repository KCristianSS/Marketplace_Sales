-- ==============================================================================
-- KAN-341 (Arqueo ciego) y KAN-342 (Movimientos de efectivo) — migración idempotente
-- Depende de: caja_turnos (Sprint 2), audit_logs.
-- ==============================================================================

ALTER TABLE caja_turnos ADD COLUMN IF NOT EXISTS con_diferencia BOOLEAN NOT NULL DEFAULT FALSE;

-- ---------------------------------------------------------------- KAN-342
CREATE TABLE IF NOT EXISTS caja_movimientos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    caja_turno_id UUID NOT NULL REFERENCES caja_turnos(id),
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
CREATE INDEX IF NOT EXISTS idx_caja_movimientos_turno ON caja_movimientos(caja_turno_id, created_at);

-- ---------------------------------------------------------------- KAN-341
CREATE TABLE IF NOT EXISTS arqueo_caja (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    numero_reporte VARCHAR(40) NOT NULL UNIQUE,
    caja_turno_id UUID NOT NULL UNIQUE REFERENCES caja_turnos(id),   -- un turno solo se arquea una vez
    cajero_id UUID NOT NULL,
    sucursal_id UUID NOT NULL,
    fondo_inicial NUMERIC(12, 2) NOT NULL,
    ventas_efectivo NUMERIC(12, 2) NOT NULL DEFAULT 0,
    entradas_extraordinarias NUMERIC(12, 2) NOT NULL DEFAULT 0,
    retiros_boveda NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_esperado NUMERIC(12, 2) NOT NULL,
    total_declarado NUMERIC(12, 2) NOT NULL CHECK (total_declarado >= 0),
    diferencia NUMERIC(12, 2) NOT NULL,                              -- declarado - esperado (+ sobrante / - faltante)
    estado_cuadre VARCHAR(10) NOT NULL CHECK (estado_cuadre IN ('cuadrado', 'sobrante', 'faltante')),
    con_diferencia BOOLEAN NOT NULL DEFAULT FALSE,
    observaciones TEXT,
    total_tarjeta NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_qr NUMERIC(12, 2) NOT NULL DEFAULT 0,
    notificacion_contabilidad JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arqueo_detalle (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    arqueo_id UUID NOT NULL REFERENCES arqueo_caja(id),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('billete', 'moneda')),
    denominacion NUMERIC(6, 2) NOT NULL
        CHECK (denominacion IN (200, 100, 50, 20, 10, 5, 2, 1, 0.50, 0.20, 0.10)),
    cantidad INT NOT NULL CHECK (cantidad >= 0),
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    UNIQUE (arqueo_id, denominacion)
);
CREATE INDEX IF NOT EXISTS idx_arqueo_caja_sucursal_fecha ON arqueo_caja(sucursal_id, created_at DESC);

-- Lo declarado queda congelado: no se puede editar ni borrar (solo se completa el estado de la notificación).
CREATE OR REPLACE FUNCTION proteger_arqueo_congelado() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'El arqueo % es inmutable y no puede eliminarse', OLD.id;
    END IF;
    IF TG_TABLE_NAME = 'arqueo_caja' THEN
        IF (to_jsonb(NEW) - 'notificacion_contabilidad') IS DISTINCT FROM (to_jsonb(OLD) - 'notificacion_contabilidad') THEN
            RAISE EXCEPTION 'El arqueo % es inmutable: solo puede actualizarse la notificación a Contabilidad', OLD.id;
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'El detalle del arqueo es inmutable';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_arqueo_caja_inmutable ON arqueo_caja;
CREATE TRIGGER trg_arqueo_caja_inmutable BEFORE UPDATE OR DELETE ON arqueo_caja
    FOR EACH ROW EXECUTE FUNCTION proteger_arqueo_congelado();
DROP TRIGGER IF EXISTS trg_arqueo_detalle_inmutable ON arqueo_detalle;
CREATE TRIGGER trg_arqueo_detalle_inmutable BEFORE UPDATE OR DELETE ON arqueo_detalle
    FOR EACH ROW EXECUTE FUNCTION proteger_arqueo_congelado();
