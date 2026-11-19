-- KAN-347: persistir los tickets POS del turno y auditar sus reimpresiones.
CREATE TABLE IF NOT EXISTS pos_ventas (
    orden_id UUID PRIMARY KEY,
    codigo_orden VARCHAR(50) NOT NULL UNIQUE,
    caja_turno_id UUID NOT NULL REFERENCES caja_turnos(id),
    cajero_id UUID NOT NULL,
    sucursal_id UUID NOT NULL,
    total NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    ticket JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pos_ventas_turno_fecha
    ON pos_ventas(caja_turno_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pos_ticket_reimpresiones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID NOT NULL REFERENCES pos_ventas(orden_id),
    caja_turno_id UUID NOT NULL REFERENCES caja_turnos(id),
    cajero_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pos_ticket_reimpresiones_orden_fecha
    ON pos_ticket_reimpresiones(orden_id, created_at DESC);
