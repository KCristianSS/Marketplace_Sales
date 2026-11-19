-- KAN-217: bitácora y cola persistente para notificaciones de cambios de estado.
CREATE TABLE IF NOT EXISTS notificaciones_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_key VARCHAR(255) UNIQUE NOT NULL,
    orden_id UUID NOT NULL REFERENCES ordenes(id) ON DELETE CASCADE,
    cliente_id UUID REFERENCES perfiles_clientes(id) ON DELETE SET NULL,
    correo_destino VARCHAR(255) NOT NULL,
    estado_orden VARCHAR(40) NOT NULL,
    asunto VARCHAR(255) NOT NULL,
    contenido TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'procesando', 'enviada', 'fallida')),
    intentos INT NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    max_intentos INT NOT NULL DEFAULT 4 CHECK (max_intentos > 0),
    proximo_intento_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ultimo_error TEXT,
    enviado_at TIMESTAMP WITH TIME ZONE,
    creado_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    actualizado_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notificaciones_log_estado_intento
    ON notificaciones_log (estado, proximo_intento_at);
CREATE INDEX IF NOT EXISTS idx_notificaciones_log_orden_creado
    ON notificaciones_log (orden_id, creado_at DESC);
CREATE INDEX IF NOT EXISTS idx_notificaciones_log_correo
    ON notificaciones_log (correo_destino);
