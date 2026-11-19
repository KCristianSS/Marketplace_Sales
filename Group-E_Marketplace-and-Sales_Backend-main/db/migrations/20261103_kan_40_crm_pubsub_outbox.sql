-- ==============================================================================
-- MIGRACIÓN KAN-40 / KAN-169: SINCRONIZACIÓN ASÍNCRONA CON CRM VÍA PUB/SUB
-- TÓPICO: projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e
-- ==============================================================================

-- 1. Campos de estado de sincronización en perfiles_clientes
ALTER TABLE perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_estado VARCHAR(20) DEFAULT 'pendiente';
ALTER TABLE perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE perfiles_clientes ADD COLUMN IF NOT EXISTS crm_contact_id VARCHAR(100);

-- 2. Bandeja de salida transaccional (Transactional Outbox) para eventos a Pub/Sub
CREATE TABLE IF NOT EXISTS outbox_eventos_crm (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(100) UNIQUE NOT NULL,
    cliente_id UUID REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL, -- cliente.creado, cliente.actualizado, cliente.compra_registrada
    topic VARCHAR(255) NOT NULL DEFAULT 'projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e',
    payload JSONB NOT NULL,
    attributes JSONB DEFAULT '{}'::jsonb,
    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'sincronizado', 'error', 'reintentando')),
    intentos INT NOT NULL DEFAULT 0,
    max_intentos INT NOT NULL DEFAULT 5,
    ultimo_error TEXT,
    message_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sent_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_eventos_crm_estado ON outbox_eventos_crm(estado);
CREATE INDEX IF NOT EXISTS idx_outbox_eventos_crm_cliente ON outbox_eventos_crm(cliente_id);

-- 3. Tabla de verificación de recepción del CRM con Idempotencia por event_id
CREATE TABLE IF NOT EXISTS crm_suscripcion_verificacion (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(100) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    cliente_id UUID,
    payload JSONB NOT NULL,
    ignorado_duplicado BOOLEAN NOT NULL DEFAULT FALSE,
    recibido_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_verificacion_event_id ON crm_suscripcion_verificacion(event_id);
