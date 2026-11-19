-- Migración KAN-42 / KAN-185: Tabla de preferencias de notificación por cliente
-- Canales: correo (default True), sms (default False), push (default False)
-- Tipos de avisos: avisos_estado_pedido (críticos), avisos_promociones, avisos_recordatorios

CREATE TABLE IF NOT EXISTS preferencias_notificacion (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID UNIQUE NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    canal_correo BOOLEAN NOT NULL DEFAULT TRUE,
    canal_sms BOOLEAN NOT NULL DEFAULT FALSE,
    canal_push BOOLEAN NOT NULL DEFAULT FALSE,
    telefono_sms VARCHAR(50),
    avisos_estado_pedido BOOLEAN NOT NULL DEFAULT TRUE,
    avisos_promociones BOOLEAN NOT NULL DEFAULT FALSE,
    avisos_recordatorios BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preferencias_notificacion_cliente 
    ON preferencias_notificacion(cliente_id);
