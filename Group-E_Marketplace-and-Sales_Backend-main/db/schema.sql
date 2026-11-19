-- ==============================================================================
-- MAXICONECTA - MARKETPLACE Y VENTAS (GRUPO E)
-- DDL DE BASE DE DATOS PARA SUPABASE (POSTGRESQL 15+)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ------------------------------------------------------------------------------
-- ENUMS Y TIPOS DE DATOS (IDEMPOTENTES)
-- ------------------------------------------------------------------------------
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_producto_enum') THEN
        CREATE TYPE estado_producto_enum AS ENUM ('borrador', 'publicado', 'inactivo', 'descontinuado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'canal_venta_enum') THEN
        CREATE TYPE canal_venta_enum AS ENUM ('web', 'pos', 'b2b');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_cliente_enum') THEN
        CREATE TYPE tipo_cliente_enum AS ENUM ('retail', 'corporativo_b2b');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_caja_enum') THEN
        CREATE TYPE estado_caja_enum AS ENUM ('abierta', 'cerrada', 'en_arqueo');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_orden_enum') THEN
        CREATE TYPE estado_orden_enum AS ENUM ('pendiente', 'confirmada', 'en_preparacion', 'despachada', 'entregada', 'cancelada');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_despacho_enum') THEN
        CREATE TYPE tipo_despacho_enum AS ENUM ('domicilio', 'retiro_sucursal');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'metodo_pago_enum') THEN
        CREATE TYPE metodo_pago_enum AS ENUM ('tarjeta', 'qr', 'transferencia', 'efectivo', 'pasarela');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_pago_enum') THEN
        CREATE TYPE estado_pago_enum AS ENUM ('pendiente', 'aprobado', 'rechazado', 'reembolsado');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_cotizacion_enum') THEN
        CREATE TYPE estado_cotizacion_enum AS ENUM ('borrador', 'emitida', 'pendiente_aprobacion', 'aprobada', 'rechazada', 'convertida', 'vencida');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_devolucion_enum') THEN
        CREATE TYPE estado_devolucion_enum AS ENUM ('solicitada', 'aprobada', 'rechazada', 'completada');
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- 1. GESTIÓN DE CATÁLOGO (RF-01 a RF-08)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categorias (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    padre_id UUID REFERENCES categorias(id) ON DELETE SET NULL,
    atributos_dinamicos JSONB DEFAULT '[]'::jsonb,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS productos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100) UNIQUE NOT NULL,
    nombre VARCHAR(255) NOT NULL,
    descripcion TEXT,
    marca VARCHAR(100),
    categoria_id UUID NOT NULL REFERENCES categorias(id),
    estado estado_producto_enum DEFAULT 'borrador',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS variantes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    producto_id UUID NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    sku VARCHAR(100) UNIQUE NOT NULL,
    nombre_variante VARCHAR(255) NOT NULL,
    atributos JSONB NOT NULL DEFAULT '{}'::jsonb,
    precio NUMERIC(12, 2) NOT NULL CHECK (precio >= 0),
    precio_costo NUMERIC(12, 2) DEFAULT 0 CHECK (precio_costo >= 0),
    codigo_barras VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS imagenes_producto (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    producto_id UUID NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    variante_id UUID REFERENCES variantes(id) ON DELETE SET NULL,
    url VARCHAR(500) NOT NULL,
    es_principal BOOLEAN DEFAULT FALSE,
    orden INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS listas_precios (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre VARCHAR(100) NOT NULL,
    canal canal_venta_enum NOT NULL,
    tipo_cliente tipo_cliente_enum NOT NULL,
    sucursal_id UUID,
    moneda VARCHAR(10) DEFAULT 'BOB',
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS precios_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lista_precio_id UUID NOT NULL REFERENCES listas_precios(id) ON DELETE CASCADE,
    variante_id UUID NOT NULL REFERENCES variantes(id) ON DELETE CASCADE,
    precio NUMERIC(12, 2) NOT NULL CHECK (precio >= 0),
    fecha_inicio TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fecha_fin TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_lista_variante UNIQUE(lista_precio_id, variante_id)
);

-- ------------------------------------------------------------------------------
-- 2. GESTIÓN DE CLIENTES (RF-22 a RF-26)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS perfiles_clientes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE, -- Vínculo opcional con auth.users de Supabase
    nombre_completo VARCHAR(200) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    telefono VARCHAR(50),
    nit_ci VARCHAR(50),
    razon_social VARCHAR(200),
    tipo_cliente tipo_cliente_enum DEFAULT 'retail',
    preferencias_notificacion JSONB DEFAULT '{"email": true, "sms": false, "whatsapp": false}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS direcciones_cliente (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    direccion VARCHAR(255) NOT NULL,
    referencia TEXT,
    ciudad VARCHAR(100) NOT NULL,
    latitud NUMERIC(10, 7) CHECK (latitud BETWEEN -90 AND 90),
    longitud NUMERIC(10, 7) CHECK (longitud BETWEEN -180 AND 180),
    es_predeterminada BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_direccion_coordenadas_pareadas CHECK ((latitud IS NULL) = (longitud IS NULL)),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE direcciones_cliente ADD COLUMN IF NOT EXISTS referencia TEXT;
ALTER TABLE direcciones_cliente ADD COLUMN IF NOT EXISTS zona VARCHAR(100);
ALTER TABLE direcciones_cliente ADD COLUMN IF NOT EXISTS latitud NUMERIC(10, 7);
ALTER TABLE direcciones_cliente ADD COLUMN IF NOT EXISTS longitud NUMERIC(10, 7);
ALTER TABLE direcciones_cliente ADD COLUMN IF NOT EXISTS es_predeterminada BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE direcciones_cliente
SET latitud = NULL, longitud = NULL
WHERE (latitud IS NULL) <> (longitud IS NULL);
WITH direcciones_duplicadas AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY cliente_id ORDER BY es_predeterminada DESC, created_at, id) AS posicion
    FROM direcciones_cliente
    WHERE es_predeterminada = TRUE
)
UPDATE direcciones_cliente AS direccion
SET es_predeterminada = FALSE
FROM direcciones_duplicadas AS duplicada
WHERE direccion.id = duplicada.id AND duplicada.posicion > 1;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_direccion_latitud') THEN
        ALTER TABLE direcciones_cliente ADD CONSTRAINT chk_direccion_latitud CHECK (latitud IS NULL OR latitud BETWEEN -90 AND 90);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_direccion_longitud') THEN
        ALTER TABLE direcciones_cliente ADD CONSTRAINT chk_direccion_longitud CHECK (longitud IS NULL OR longitud BETWEEN -180 AND 180);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_direccion_coordenadas_pareadas') THEN
        ALTER TABLE direcciones_cliente ADD CONSTRAINT chk_direccion_coordenadas_pareadas CHECK ((latitud IS NULL) = (longitud IS NULL));
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_direcciones_cliente_predeterminada
    ON direcciones_cliente (cliente_id) WHERE es_predeterminada = TRUE;

CREATE TABLE IF NOT EXISTS puntos_fidelidad (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID UNIQUE NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    puntos_saldo INT DEFAULT 0 CHECK (puntos_saldo >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- KAN-42 / KAN-185: Preferencias de notificación y canales por cliente
CREATE TABLE IF NOT EXISTS preferencias_notificacion (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID UNIQUE NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    canal_correo BOOLEAN NOT NULL DEFAULT TRUE,
    canal_sms BOOLEAN NOT NULL DEFAULT FALSE,
    canal_push BOOLEAN NOT NULL DEFAULT FALSE,
    telefono_sms VARCHAR(50),
    avisos_estado_pedido BOOLEAN NOT NULL DEFAULT TRUE, -- Entrega y cancelación (avisos críticos)
    avisos_promociones BOOLEAN NOT NULL DEFAULT FALSE,
    avisos_recordatorios BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preferencias_notificacion_cliente ON preferencias_notificacion(cliente_id);

CREATE TABLE IF NOT EXISTS movimientos_puntos_fidelidad (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    orden_id UUID,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('acumulacion', 'canje', 'ajuste')),
    puntos INT NOT NULL CHECK (puntos > 0),
    valor_bob NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (valor_bob >= 0),
    descripcion TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_movimientos_puntos_orden_tipo
    ON movimientos_puntos_fidelidad (orden_id, tipo) WHERE orden_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_movimientos_puntos_cliente_fecha
    ON movimientos_puntos_fidelidad (cliente_id, created_at DESC);

-- KAN-40 / KAN-169: Bandeja de salida (Transactional Outbox) y Verificación CRM
CREATE TABLE IF NOT EXISTS outbox_eventos_crm (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(100) UNIQUE NOT NULL,
    cliente_id UUID REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
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

-- ------------------------------------------------------------------------------
-- 3. PUNTOS DE VENTA FÍSICOS (POS) (RF-09 a RF-12)

-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS caja_turnos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sucursal_id UUID NOT NULL,
    cajero_id UUID NOT NULL,
    fondo_inicial NUMERIC(12, 2) NOT NULL CHECK (fondo_inicial >= 0),
    total_efectivo NUMERIC(12, 2) DEFAULT 0,
    total_tarjeta NUMERIC(12, 2) DEFAULT 0,
    total_qr NUMERIC(12, 2) DEFAULT 0,
    monto_cierre_real NUMERIC(12, 2),
    diferencia NUMERIC(12, 2),
    estado estado_caja_enum DEFAULT 'abierta',
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE
);

-- ------------------------------------------------------------------------------
-- 4. MARKETPLACE DIGITAL, PROMOCIONES Y COMBOS (RF-13 a RF-21)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cupones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    codigo VARCHAR(50) UNIQUE NOT NULL,
    descripcion VARCHAR(200),
    tipo_descuento VARCHAR(20) NOT NULL CHECK (tipo_descuento IN ('porcentaje', 'monto_fijo')),
    valor_descuento NUMERIC(10, 2) NOT NULL CHECK (valor_descuento > 0),
    monto_minimo NUMERIC(12, 2) DEFAULT 0,
    usos_maximos INT DEFAULT 100,
    usos_actuales INT DEFAULT 0,
    fecha_inicio TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fecha_fin TIMESTAMP WITH TIME ZONE,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS combos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(100) UNIQUE,
    nombre VARCHAR(200) NOT NULL,
    descripcion TEXT,
    precio_combo NUMERIC(12, 2) NOT NULL CHECK (precio_combo > 0),
    imagen_url TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS combos_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    combo_id UUID NOT NULL REFERENCES combos(id) ON DELETE CASCADE,
    variante_id UUID NOT NULL REFERENCES variantes(id) ON DELETE CASCADE,
    cantidad INT NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    CONSTRAINT uq_combo_variante UNIQUE(combo_id, variante_id)
);

CREATE TABLE IF NOT EXISTS resenas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    producto_id UUID NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    orden_id UUID,
    calificacion INT NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    comentario TEXT NOT NULL,
    aprobada BOOLEAN NOT NULL DEFAULT FALSE,
    estado_moderacion VARCHAR(16) NOT NULL DEFAULT 'pendiente' CHECK (estado_moderacion IN ('pendiente', 'aprobada', 'rechazada')),
    motivo_rechazo TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deseos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    variante_id UUID NOT NULL REFERENCES variantes(id) ON DELETE CASCADE,
    orden_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    comentario TEXT NOT NULL,
    aprobada BOOLEAN NOT NULL DEFAULT FALSE,
    estado_moderacion VARCHAR(16) NOT NULL DEFAULT 'pendiente' CHECK (estado_moderacion IN ('pendiente', 'aprobada', 'rechazada')),
    motivo_rechazo TEXT,

-- ------------------------------------------------------------------------------
-- 5. GESTIÓN DE VENTAS Y ÓRDENES (RF-27 a RF-39)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ordenes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    codigo_orden VARCHAR(50) UNIQUE NOT NULL,
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id),
    sucursal_id UUID,
    canal canal_venta_enum NOT NULL DEFAULT 'web',
    tipo_despacho tipo_despacho_enum NOT NULL DEFAULT 'domicilio',
    direccion_entrega_id UUID REFERENCES direcciones_cliente(id),
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    descuento NUMERIC(12, 2) DEFAULT 0 CHECK (descuento >= 0),
    costo_envio NUMERIC(12, 2) DEFAULT 0 CHECK (costo_envio >= 0),
    entrega JSONB,
    total NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    moneda VARCHAR(10) DEFAULT 'BOB',
    estado estado_orden_enum DEFAULT 'pendiente',
    caja_turno_id UUID REFERENCES caja_turnos(id),
    tracking_number VARCHAR(100),
    reserva_id TEXT,
    cuf_factura VARCHAR(100),
    numero_factura BIGINT,
    motivo_cancelacion TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orden_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID NOT NULL REFERENCES ordenes(id) ON DELETE CASCADE,
    variante_id UUID NOT NULL REFERENCES variantes(id),
    sku VARCHAR(100) NOT NULL,
    nombre_producto VARCHAR(255) NOT NULL,
    cantidad INT NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(12, 2) NOT NULL CHECK (precio_unitario >= 0),
    total_linea NUMERIC(12, 2) NOT NULL CHECK (total_linea >= 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
ALTER TABLE orden_items ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE orden_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS numero_factura BIGINT;
ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS entrega JSONB;
ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS reserva_id TEXT;
ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS motivo_cancelacion TEXT;
ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS estado_actualizado_por UUID;

CREATE TABLE IF NOT EXISTS orden_estados_historial (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID NOT NULL REFERENCES ordenes(id) ON DELETE CASCADE,
    estado_anterior estado_orden_enum,
    estado_nuevo estado_orden_enum NOT NULL,
    cambiado_por UUID,
    cambiado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
ALTER TABLE orden_estados_historial ADD COLUMN IF NOT EXISTS cambiado_por UUID;

CREATE OR REPLACE FUNCTION registrar_historial_estado_orden() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.estado IS DISTINCT FROM OLD.estado THEN
        INSERT INTO orden_estados_historial (orden_id, estado_anterior, estado_nuevo, cambiado_por)
        VALUES (NEW.id, CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.estado END, NEW.estado, NEW.estado_actualizado_por);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_orden_estado_auditoria ON ordenes;
CREATE TRIGGER trg_orden_estado_auditoria
AFTER INSERT OR UPDATE OF estado ON ordenes
FOR EACH ROW EXECUTE FUNCTION registrar_historial_estado_orden();

ALTER TABLE resenas ADD COLUMN IF NOT EXISTS orden_id UUID;
ALTER TABLE resenas ADD COLUMN IF NOT EXISTS estado_moderacion VARCHAR(16) NOT NULL DEFAULT 'pendiente';
ALTER TABLE resenas ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT;
UPDATE resenas SET estado_moderacion = 'aprobada' WHERE aprobada = TRUE AND estado_moderacion = 'pendiente';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_resenas_orden') THEN
        ALTER TABLE resenas ADD CONSTRAINT fk_resenas_orden FOREIGN KEY (orden_id) REFERENCES ordenes(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_resenas_estado_moderacion') THEN
        ALTER TABLE resenas ADD CONSTRAINT chk_resenas_estado_moderacion CHECK (estado_moderacion IN ('pendiente', 'aprobada', 'rechazada'));
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_resenas_cliente_producto_orden
    ON resenas (cliente_id, producto_id, orden_id) WHERE orden_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_resenas_producto_estado
    ON resenas (producto_id, estado_moderacion, created_at DESC);

ALTER TABLE resenas ADD COLUMN IF NOT EXISTS orden_id UUID;
ALTER TABLE resenas ADD COLUMN IF NOT EXISTS estado_moderacion VARCHAR(16) NOT NULL DEFAULT 'pendiente';
ALTER TABLE resenas ADD COLUMN IF NOT EXISTS motivo_rechazo TEXT;
UPDATE resenas SET estado_moderacion = CASE WHEN aprobada THEN 'aprobada' ELSE 'pendiente' END;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_resenas_orden') THEN
        ALTER TABLE resenas ADD CONSTRAINT fk_resenas_orden FOREIGN KEY (orden_id) REFERENCES ordenes(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_resenas_estado_moderacion') THEN
        ALTER TABLE resenas ADD CONSTRAINT chk_resenas_estado_moderacion CHECK (estado_moderacion IN ('pendiente', 'aprobada', 'rechazada'));
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_resenas_cliente_producto_orden
    ON resenas (cliente_id, producto_id, orden_id) WHERE orden_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_resenas_producto_estado
    ON resenas (producto_id, estado_moderacion, created_at DESC);

CREATE TABLE IF NOT EXISTS pagos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID NOT NULL REFERENCES ordenes(id) ON DELETE CASCADE,
    transaccion_id VARCHAR(100) UNIQUE,
    metodo metodo_pago_enum NOT NULL,
    monto NUMERIC(12, 2) NOT NULL CHECK (monto > 0),
    moneda VARCHAR(10) DEFAULT 'BOB',
    estado estado_pago_enum DEFAULT 'pendiente',
    raw_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION confirmar_orden_atomica(p_orden JSONB, p_items JSONB, p_pagos JSONB)
RETURNS JSONB AS $$
DECLARE
    v_orden_id UUID := (p_orden->>'id')::UUID;
    v_pago JSONB;
    v_tx TEXT;
    v_existing_order UUID;
    v_result JSONB;
BEGIN
    v_tx := COALESCE(p_pagos->0->>'transaccion_id', 'orden:' || v_orden_id::TEXT);
    PERFORM pg_advisory_xact_lock(hashtextextended(v_tx, 0));
    SELECT orden_id INTO v_existing_order FROM pagos
    WHERE transaccion_id = v_tx AND orden_id IS NOT NULL LIMIT 1;
    IF v_existing_order IS NOT NULL THEN
        SELECT jsonb_build_object('id', id, 'codigo_orden', codigo_orden, 'existente', TRUE)
        INTO v_result FROM ordenes WHERE id = v_existing_order;
        RETURN v_result;
    END IF;

    INSERT INTO ordenes (id, codigo_orden, cliente_id, sucursal_id, canal, tipo_despacho,
        direccion_entrega_id, subtotal, descuento, costo_envio, total, estado, tracking_number, reserva_id, cuf_factura, numero_factura, entrega)
    VALUES (v_orden_id, p_orden->>'codigo_orden', (p_orden->>'cliente_id')::UUID,
        NULLIF(p_orden->>'sucursal_id', '')::UUID, (p_orden->>'canal')::canal_venta_enum,
        (p_orden->>'tipo_despacho')::tipo_despacho_enum, NULLIF(p_orden->>'direccion_entrega_id', '')::UUID,
        (p_orden->>'subtotal')::NUMERIC, (p_orden->>'descuento')::NUMERIC,
        (p_orden->>'costo_envio')::NUMERIC, (p_orden->>'total')::NUMERIC,
        (p_orden->>'estado')::estado_orden_enum, p_orden->>'tracking_number', p_orden->>'reserva_id', p_orden->>'cuf_factura',
        NULLIF(p_orden->>'numero_factura', '')::BIGINT, p_orden->'entrega');

    INSERT INTO orden_items (orden_id, variante_id, sku, nombre_producto, cantidad, precio_unitario, total_linea)
    SELECT v_orden_id, (item.value->>'variante_id')::UUID, item.value->>'sku', item.value->>'nombre_producto',
        (item.value->>'cantidad')::INT, (item.value->>'precio_unitario')::NUMERIC, (item.value->>'total_linea')::NUMERIC
    FROM jsonb_array_elements(p_items) AS item(value);

    FOR v_pago IN SELECT value FROM jsonb_array_elements(p_pagos)
    LOOP
        INSERT INTO pagos (orden_id, transaccion_id, metodo, monto, moneda, estado, raw_payload)
        VALUES (v_orden_id, v_pago->>'transaccion_id', (v_pago->>'metodo')::metodo_pago_enum,
            (v_pago->>'monto')::NUMERIC, 'BOB', 'aprobado', COALESCE(v_pago->'raw_payload', '{}'::JSONB))
        ON CONFLICT (transaccion_id) DO UPDATE
            SET orden_id = EXCLUDED.orden_id, estado = 'aprobado', raw_payload = EXCLUDED.raw_payload
            WHERE pagos.orden_id IS NULL;
    END LOOP;
    RETURN jsonb_build_object('id', v_orden_id, 'codigo_orden', p_orden->>'codigo_orden', 'existente', FALSE);
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS devoluciones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID NOT NULL REFERENCES ordenes(id),
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id),
    motivo TEXT NOT NULL,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    comentario_resolucion TEXT,
    estado estado_devolucion_enum DEFAULT 'solicitada',
    evidencia_urls JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolucion_at TIMESTAMP WITH TIME ZONE
);
ALTER TABLE devoluciones ADD COLUMN IF NOT EXISTS items JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE devoluciones ADD COLUMN IF NOT EXISTS comentario_resolucion TEXT;

-- KAN-46 / KAN-217: cola durable e idempotente para correos de estado de órdenes
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

CREATE TABLE IF NOT EXISTS cotizaciones_b2b (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    codigo_cotizacion VARCHAR(50) UNIQUE NOT NULL,
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id),
    gerente_id UUID,
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    descuento_porcentaje NUMERIC(5, 2) DEFAULT 0,
    total NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    vigencia_dias INT NOT NULL DEFAULT 7 CHECK (vigencia_dias IN (7, 15, 30)),
    vigencia_hasta DATE NOT NULL,
    estado estado_cotizacion_enum DEFAULT 'borrador',
    orden_id UUID REFERENCES ordenes(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cotizacion_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cotizacion_id UUID NOT NULL REFERENCES cotizaciones_b2b(id) ON DELETE CASCADE,
    variante_id UUID NOT NULL REFERENCES variantes(id),
    cantidad INT NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(12, 2) NOT NULL CHECK (precio_unitario >= 0),
    total_linea NUMERIC(12, 2) NOT NULL CHECK (total_linea >= 0)
);

CREATE TABLE IF NOT EXISTS cotizaciones_b2b_secuencia (
    anio INT PRIMARY KEY,
    ultimo_numero INT NOT NULL CHECK (ultimo_numero > 0)
);
ALTER TABLE cotizaciones_b2b_secuencia ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON cotizaciones_b2b_secuencia FROM anon, authenticated;

CREATE OR REPLACE FUNCTION generar_codigo_cotizacion_b2b() RETURNS TEXT AS $$
DECLARE
    anio_actual INT := EXTRACT(YEAR FROM (CURRENT_TIMESTAMP - INTERVAL '4 hours'))::INT;
    siguiente_numero INT;
BEGIN
    INSERT INTO cotizaciones_b2b_secuencia (anio, ultimo_numero)
    VALUES (anio_actual, 1)
    ON CONFLICT (anio) DO UPDATE
        SET ultimo_numero = cotizaciones_b2b_secuencia.ultimo_numero + 1
    RETURNING ultimo_numero INTO siguiente_numero;

    RETURN 'COT-' || anio_actual::TEXT || '-' || LPAD(siguiente_numero::TEXT, 4, '0');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
REVOKE ALL ON FUNCTION generar_codigo_cotizacion_b2b() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION generar_codigo_cotizacion_b2b() TO service_role;

-- ------------------------------------------------------------------------------
-- 6. ADMINISTRACIÓN, SEGURIDAD Y AUDITORÍA (RF-49, RF-50)
-- ------------------------------------------------------------------------------
-- KAN-421 / KAN-423: Tabla propia de usuarios internos (cajeros, gerentes, administradores)
CREATE TABLE IF NOT EXISTS usuarios_internos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE,
    nombre_completo VARCHAR(200) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    rol VARCHAR(50) NOT NULL CHECK (rol IN ('cajero', 'gerente_comercial', 'administrador')),
    sucursal_id VARCHAR(100),
    sucursal_nombre VARCHAR(200),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    debe_cambiar_password BOOLEAN NOT NULL DEFAULT TRUE,
    password_temporal VARCHAR(255),
    sesion_revocada BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_internos_email ON usuarios_internos(email);
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_rol ON usuarios_internos(rol);
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_sucursal ON usuarios_internos(sucursal_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_activo ON usuarios_internos(activo);

CREATE TABLE IF NOT EXISTS audit_logs (

    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    user_role VARCHAR(50),
    ip_address VARCHAR(45),
    action VARCHAR(100) NOT NULL,
    entity VARCHAR(100) NOT NULL,
    entity_id UUID,
    payload_before JSONB,
    payload_after JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices de alto rendimiento
CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_productos_estado ON productos(estado);
CREATE INDEX IF NOT EXISTS idx_productos_marca ON productos(marca);
CREATE INDEX IF NOT EXISTS idx_variantes_producto ON variantes(producto_id);
CREATE INDEX IF NOT EXISTS idx_variantes_precio ON variantes(precio);
CREATE INDEX IF NOT EXISTS idx_ordenes_cliente ON ordenes(cliente_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_estado ON ordenes(estado);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

-- ------------------------------------------------------------------------------
-- SOPORTE FULL-TEXT SEARCH (FTS) Y BÚSQUEDA FACETADA (RF-06 / US-06)
-- ------------------------------------------------------------------------------
ALTER TABLE productos ADD COLUMN IF NOT EXISTS search_vector tsvector 
    GENERATED ALWAYS AS (
        to_tsvector('spanish', 
            coalesce(nombre, '') || ' ' || 
            coalesce(marca, '') || ' ' || 
            coalesce(sku, '') || ' ' || 
            coalesce(descripcion, '')
        )
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_productos_fts_gin ON productos USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_productos_nombre_trgm ON productos USING GIN (nombre gin_trgm_ops);

-- Tickets POS disponibles para consulta y reimpresión durante el turno (KAN-347).
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

-- ==============================================================================
-- HISTORIA KAN-10 / KAN-345: AUTORIZACIÓN DE DESCUENTOS MANUALES EN POS (RF-10)
-- SUBTAREAS: KAN-360, KAN-362
-- ==============================================================================

CREATE TABLE IF NOT EXISTS pos_supervisor_pins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    supervisor_id UUID NOT NULL,
    supervisor_username VARCHAR(100) NOT NULL UNIQUE,
    supervisor_nombre VARCHAR(200) NOT NULL,
    pin_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(50) NOT NULL DEFAULT 'administrador',
    intentos_fallidos INT NOT NULL DEFAULT 0,
    bloqueado_hasta TIMESTAMP WITH TIME ZONE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pos_supervisor_username ON pos_supervisor_pins(supervisor_username);

CREATE TABLE IF NOT EXISTS pos_descuentos_manuales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    autorizacion_token VARCHAR(100) NOT NULL UNIQUE,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('item', 'total')),
    item_sku VARCHAR(100),
    porcentaje_descuento NUMERIC(5, 2) NOT NULL CHECK (porcentaje_descuento > 0 AND porcentaje_descuento <= 30.00),
    monto_descuento NUMERIC(12, 2) NOT NULL CHECK (monto_descuento >= 0),
    monto_base NUMERIC(12, 2) NOT NULL CHECK (monto_base >= 0),
    motivo TEXT NOT NULL,
    supervisor_id UUID NOT NULL,
    supervisor_nombre VARCHAR(200) NOT NULL,
    cajero_id UUID,
    cajero_nombre VARCHAR(200),
    sucursal_id UUID,
    usado BOOLEAN NOT NULL DEFAULT FALSE,
    orden_id UUID REFERENCES ordenes(id) ON DELETE SET NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pos_descuentos_token ON pos_descuentos_manuales(autorizacion_token);
CREATE INDEX IF NOT EXISTS idx_pos_descuentos_orden ON pos_descuentos_manuales(orden_id);



-- ==============================================================================
-- SPRINT 3: KAN-341 / KAN-342 / KAN-54 / KAN-55 (copia de db/migrations/20261029_*)
-- ==============================================================================

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
ALTER TABLE public.caja_movimientos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.caja_movimientos FROM anon, authenticated;
GRANT ALL ON public.caja_movimientos TO service_role;

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
ALTER TABLE public.reembolsos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reembolsos FROM anon, authenticated;
GRANT ALL ON public.reembolsos TO service_role;
-- Configuracion administrable de flete y registro de cambios.
CREATE TABLE IF NOT EXISTS public.flete_configuracion (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    configuracion JSONB NOT NULL CHECK (jsonb_typeof(configuracion) = 'object'),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    actualizado_por TEXT,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.flete_configuracion_historial (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    configuracion_anterior JSONB NOT NULL,
    configuracion_nueva JSONB NOT NULL,
    actualizado_por TEXT,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.flete_configuracion ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flete_configuracion_historial ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.flete_configuracion, public.flete_configuracion_historial FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.flete_configuracion TO service_role;
GRANT SELECT, INSERT ON public.flete_configuracion_historial TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.flete_configuracion_historial_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.auditar_configuracion_flete()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    IF NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'La version de envios debe incrementarse en uno';
    END IF;
    NEW.actualizado_en := now();
    INSERT INTO public.flete_configuracion_historial
        (version, configuracion_anterior, configuracion_nueva, actualizado_por)
    VALUES (NEW.version, OLD.configuracion, NEW.configuracion, NEW.actualizado_por);
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS auditar_configuracion_flete ON public.flete_configuracion;
CREATE TRIGGER auditar_configuracion_flete BEFORE UPDATE ON public.flete_configuracion
FOR EACH ROW EXECUTE FUNCTION public.auditar_configuracion_flete();

INSERT INTO public.flete_configuracion (id, configuracion)
VALUES (1, '{"envio_gratis_habilitado": true, "umbral_envio_gratis": 500, "recargo_express": 15, "peso_incluido_kg": 5, "recargo_por_kg": 5, "peso_estimado_por_unidad_kg": 1.5, "zonas": [{"id": "d5ac8f27-5944-5cbd-b5e9-fe285d102d0a", "ciudad": "La Paz", "nombre": "Centro", "tarifa_base": 15.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "404e41b1-ab65-5e4e-9690-df7e4f565fe5", "ciudad": "La Paz", "nombre": "Miraflores", "tarifa_base": 15.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "5015c209-39e2-56fd-9f42-c3dff77f7cdc", "ciudad": "La Paz", "nombre": "Sopocachi", "tarifa_base": 15.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "fe448f6e-f59a-55c0-8892-b3842af849b8", "ciudad": "La Paz", "nombre": "San Pedro", "tarifa_base": 15.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "f405b714-62d7-5aaf-9e8c-4937dad830e9", "ciudad": "La Paz", "nombre": "Zona Sur (Calacoto / San Miguel)", "tarifa_base": 20.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "ff5cb764-8a22-5f7a-a25c-16d1f248b238", "ciudad": "La Paz", "nombre": "Achumani / Irpavi / Cota Cota", "tarifa_base": 22.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "13db4c49-1fc5-5fa0-ae22-0355f2f52be1", "ciudad": "La Paz", "nombre": "Periférica / Laderas", "tarifa_base": 25.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "0c0f1288-501f-5ac9-b190-af87e9e3e510", "ciudad": "El Alto", "nombre": "Ceja", "tarifa_base": 20.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "0fdee1aa-3357-5869-a2de-98c8e869565a", "ciudad": "El Alto", "nombre": "Ciudad Satélite", "tarifa_base": 22.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "ac3ac6af-8f98-517e-bb4f-bd7490922935", "ciudad": "El Alto", "nombre": "Villa Adela", "tarifa_base": 25.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "1bee8c7b-ce01-5984-9529-ab37bd1c9fd1", "ciudad": "El Alto", "nombre": "Rio Seco", "tarifa_base": 28.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "1d120720-d4b6-5450-b7df-7d76e4cf3eb5", "ciudad": "Santa Cruz", "nombre": "1er a 4to Anillo", "tarifa_base": 18.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "ed2386ac-a43c-565d-a8e7-8ffc701d054b", "ciudad": "Santa Cruz", "nombre": "Equipetrol", "tarifa_base": 18.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "155f3683-4358-5899-9c0d-83ed58928c55", "ciudad": "Santa Cruz", "nombre": "Urubó", "tarifa_base": 28.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "88fffae6-3dc6-51a4-8d0c-2ed89056f382", "ciudad": "Santa Cruz", "nombre": "5to a 8vo Anillo", "tarifa_base": 25.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "38605548-5501-5a2c-a5aa-675a29f43ee6", "ciudad": "Santa Cruz", "nombre": "Plan 3000", "tarifa_base": 28.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "ea68433f-799c-5e38-850d-39753dfc9397", "ciudad": "Cochabamba", "nombre": "Centro / El Prado", "tarifa_base": 15.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "d94d5379-1b3c-5cd7-bd5f-eaa9a9790143", "ciudad": "Cochabamba", "nombre": "Cala Cala / Recoleta", "tarifa_base": 18.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "50f699c4-a400-57ea-be2a-b45e1f88cf65", "ciudad": "Cochabamba", "nombre": "Zona Sur", "tarifa_base": 22.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "c9020db4-b347-5943-baa5-962a27758f90", "ciudad": "Cochabamba", "nombre": "Sacaba / Quillacollo", "tarifa_base": 30.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 24 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "52e0d5d0-3faa-537f-a520-5a5fd238b30e", "ciudad": "Sucre", "nombre": "Centro Histórico", "tarifa_base": 35.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "207aed9e-e359-507d-ba0d-e92ee59bb9f6", "ciudad": "Sucre", "nombre": "Zona Alta", "tarifa_base": 35.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "e013cdc5-6aed-528e-83fd-af20d9867376", "ciudad": "Sucre", "nombre": "Rumi Rumi", "tarifa_base": 35.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "27b44558-dbb3-5446-af46-b2457dffe11a", "ciudad": "Tarija", "nombre": "Centro", "tarifa_base": 35.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "a11f930a-040f-5d21-9c0a-e598bce27974", "ciudad": "Tarija", "nombre": "San Roque", "tarifa_base": 35.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "6b5dab13-c8b3-5614-8ae3-9c2aca28fe0d", "ciudad": "Tarija", "nombre": "Tomatitas", "tarifa_base": 35.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "3208a8f0-a35d-5c71-99f1-3d56d040740f", "ciudad": "Oruro", "nombre": "Centro", "tarifa_base": 30.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "0f5b7373-e45b-51f8-8f61-51c957b9eb22", "ciudad": "Oruro", "nombre": "Socavón", "tarifa_base": 30.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}, {"id": "26f0047d-9a55-5274-8697-f3a0011a4dca", "ciudad": "Oruro", "nombre": "Zona Norte", "tarifa_base": 30.0, "activa": true, "estandar_habilitado": true, "express_habilitado": true, "plazo_estandar": "Entrega en 48 a 72 horas hábiles", "plazo_express": "Entrega en menos de 4 horas hábiles"}]}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- Tarjetas de regalo (2026-11-05)
-- Aplicar después de 20261022_confirmar_orden_atomica.sql.
-- Solo el servicio de órdenes puede operar sobre dinero prepagado.
ALTER TYPE public.metodo_pago_enum ADD VALUE IF NOT EXISTS 'vale';
-- Las compras de saldo y los pagos pendientes todavía no tienen una orden de productos.
ALTER TABLE public.pagos ALTER COLUMN orden_id DROP NOT NULL;
ALTER TABLE public.pagos ADD COLUMN IF NOT EXISTS token_pago TEXT;
ALTER TABLE public.pagos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.tarjetas_regalo (
    id UUID PRIMARY KEY,
    comprador_id UUID NOT NULL,
    codigo_hash TEXT NOT NULL UNIQUE,
    codigo_version TEXT NOT NULL,
    codigo_ultimos TEXT NOT NULL,
    monto_inicial NUMERIC(14,2) NOT NULL CHECK (monto_inicial > 0),
    saldo NUMERIC(14,2) NOT NULL CHECK (saldo >= 0 AND saldo <= monto_inicial),
    moneda TEXT NOT NULL DEFAULT 'BOB' CHECK (moneda = 'BOB'),
    estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa','bloqueada','anulada')),
    origen TEXT NOT NULL CHECK (origen IN ('compra','administracion')),
    transaccion_compra TEXT UNIQUE,
    vence_en TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tarjetas_regalo_comprador ON public.tarjetas_regalo(comprador_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.reservas_vale (
    id UUID PRIMARY KEY,
    tarjeta_id UUID NOT NULL REFERENCES public.tarjetas_regalo(id),
    cliente_id UUID NOT NULL,
    checkout_id TEXT NOT NULL,
    monto NUMERIC(14,2) NOT NULL CHECK (monto > 0),
    total NUMERIC(14,2) NOT NULL CHECK (total >= monto),
    estado TEXT NOT NULL DEFAULT 'reservada' CHECK (estado IN ('reservada','consumida','liberada','reintegrada')),
    orden_id UUID,
    expira_en TIMESTAMPTZ NOT NULL DEFAULT now() + interval '15 minutes',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS reservas_vale_checkout ON public.reservas_vale(cliente_id,checkout_id)
    WHERE estado IN ('reservada','consumida');
CREATE INDEX IF NOT EXISTS reservas_vale_tarjeta ON public.reservas_vale(tarjeta_id);

CREATE TABLE IF NOT EXISTS public.movimientos_vale (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tarjeta_id UUID NOT NULL REFERENCES public.tarjetas_regalo(id),
    reserva_id UUID REFERENCES public.reservas_vale(id),
    tipo TEXT NOT NULL,
    monto NUMERIC(14,2) NOT NULL DEFAULT 0,
    actor TEXT NOT NULL,
    motivo TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS movimientos_vale_tarjeta ON public.movimientos_vale(tarjeta_id,created_at);

ALTER TABLE public.tarjetas_regalo ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reservas_vale ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.movimientos_vale ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.tarjetas_regalo, public.reservas_vale, public.movimientos_vale FROM anon, authenticated;
GRANT ALL ON public.tarjetas_regalo, public.reservas_vale, public.movimientos_vale TO service_role;

CREATE OR REPLACE FUNCTION public.operar_vale(p_accion TEXT, p_actor TEXT, p_datos JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    v public.tarjetas_regalo%ROWTYPE;
    r public.reservas_vale%ROWTYPE;
    e public.reservas_vale%ROWTYPE;
    tid UUID;
    importe NUMERIC(14,2);
    listado JSONB;
BEGIN
    IF p_accion = 'listar' THEN
        -- Mostrar el disponible correcto aunque todavía no haya ocurrido la limpieza perezosa del TTL.
        SELECT COALESCE(jsonb_agg(fila), '[]'::JSONB) INTO listado FROM (
            SELECT to_jsonb(t) || jsonb_build_object('saldo',t.saldo + COALESCE((
                SELECT SUM(rv.monto) FROM public.reservas_vale rv WHERE rv.tarjeta_id = t.id
                    AND rv.estado = 'reservada' AND rv.expira_en <= now()),0)) AS fila
            FROM public.tarjetas_regalo t
            WHERE (COALESCE((p_datos->>'administracion')::BOOLEAN,FALSE) OR t.comprador_id::TEXT = p_actor)
                AND (p_datos->>'estado' IS NULL OR t.estado = p_datos->>'estado')
                AND (p_datos->>'comprador_id' IS NULL OR t.comprador_id::TEXT = p_datos->>'comprador_id')
                AND (p_datos->>'ultimos' IS NULL OR t.codigo_ultimos = p_datos->>'ultimos')
            ORDER BY t.created_at DESC,t.id
            LIMIT CASE WHEN COALESCE((p_datos->>'administracion')::BOOLEAN,FALSE) THEN 50 ELSE 100 END
            OFFSET COALESCE((p_datos->>'offset')::INT,0)
        ) filas;
        RETURN jsonb_build_object('items',listado);
    END IF;
    -- Serializa reintentos de una emisión/reserva y mantiene un único orden de locks: tarjeta -> reserva.
    IF p_accion = 'emitir' THEN
        tid := (p_datos->>'id')::UUID;
        PERFORM pg_advisory_xact_lock(hashtextextended(tid::TEXT, 0));
        SELECT * INTO v FROM public.tarjetas_regalo WHERE id = tid FOR UPDATE;
        IF FOUND THEN
            IF v.comprador_id::TEXT <> p_datos->>'comprador_id'
               OR v.monto_inicial <> (p_datos->>'monto')::NUMERIC THEN
                RETURN jsonb_build_object('error','La emisión ya existe con otros datos.');
            END IF;
            RETURN to_jsonb(v);
        END IF;
        INSERT INTO public.tarjetas_regalo(id,comprador_id,codigo_hash,codigo_version,codigo_ultimos,
            monto_inicial,saldo,origen,transaccion_compra,vence_en)
        VALUES (tid,(p_datos->>'comprador_id')::UUID,p_datos->>'codigo_hash',p_datos->>'codigo_version',
            p_datos->>'codigo_ultimos',(p_datos->>'monto')::NUMERIC,(p_datos->>'monto')::NUMERIC,
            p_datos->>'origen',p_datos->>'transaccion_compra',(p_datos->>'vence_en')::TIMESTAMPTZ)
        RETURNING * INTO v;
        INSERT INTO public.movimientos_vale(tarjeta_id,tipo,monto,actor,motivo)
        VALUES(tid,'emision',v.saldo,p_actor,p_datos->>'motivo');
        RETURN to_jsonb(v);
    END IF;

    IF p_accion IN ('reservar','consultar') THEN
        SELECT * INTO v FROM public.tarjetas_regalo WHERE codigo_hash = p_datos->>'codigo_hash' FOR UPDATE;
    ELSIF p_accion IN ('reserva','consumir','liberar','reintegrar','restaurar_consumo') THEN
        SELECT tarjeta_id INTO tid FROM public.reservas_vale WHERE id = (p_datos->>'reserva_id')::UUID;
        SELECT * INTO v FROM public.tarjetas_regalo WHERE id = tid FOR UPDATE;
    ELSE
        SELECT * INTO v FROM public.tarjetas_regalo WHERE id = (p_datos->>'id')::UUID FOR UPDATE;
    END IF;
    IF v.id IS NULL THEN RETURN jsonb_build_object('error','Vale o reserva no disponible.','status',404); END IF;
    tid := v.id;

    -- Las reservas vencidas nunca se convierten en consumo ni retienen saldo indefinidamente.
    FOR e IN SELECT * FROM public.reservas_vale WHERE tarjeta_id = tid
        AND estado = 'reservada' AND expira_en <= now() FOR UPDATE
    LOOP
        UPDATE public.reservas_vale SET estado = 'liberada' WHERE id = e.id;
        UPDATE public.tarjetas_regalo SET saldo = saldo + e.monto WHERE id = tid RETURNING * INTO v;
        INSERT INTO public.movimientos_vale(tarjeta_id,reserva_id,tipo,monto,actor,motivo)
        VALUES(tid,e.id,'liberacion',e.monto,'sistema','Reserva vencida');
    END LOOP;

    IF p_accion IN ('reserva','consumir','liberar','reintegrar','restaurar_consumo') THEN
        SELECT * INTO r FROM public.reservas_vale WHERE id = (p_datos->>'reserva_id')::UUID FOR UPDATE;
        IF p_accion IN ('reserva','consumir','liberar') AND r.cliente_id::TEXT <> p_actor THEN
            RETURN jsonb_build_object('error','Reserva no disponible.','status',404);
        END IF;
        IF p_accion = 'reserva' THEN RETURN to_jsonb(r); END IF;
        IF p_accion = 'consumir' THEN
            IF r.estado = 'consumida' AND r.orden_id = (p_datos->>'orden_id')::UUID THEN RETURN to_jsonb(r); END IF;
            IF r.estado <> 'reservada' OR v.estado <> 'activa' OR (v.vence_en IS NOT NULL AND v.vence_en <= now()) THEN
                RETURN jsonb_build_object('error','La reserva ya no puede canjearse.');
            END IF;
            UPDATE public.reservas_vale SET estado = 'consumida', orden_id = (p_datos->>'orden_id')::UUID
            WHERE id = r.id RETURNING * INTO r;
            INSERT INTO public.movimientos_vale(tarjeta_id,reserva_id,tipo,monto,actor,motivo)
            VALUES(tid,r.id,'consumo',-r.monto,p_actor,'Pago de orden ' || r.orden_id::TEXT);
        ELSIF p_accion = 'liberar' AND r.estado = 'reservada' THEN
            UPDATE public.reservas_vale SET estado = 'liberada' WHERE id = r.id RETURNING * INTO r;
            UPDATE public.tarjetas_regalo SET saldo = saldo + r.monto WHERE id = tid;
            INSERT INTO public.movimientos_vale(tarjeta_id,reserva_id,tipo,monto,actor,motivo)
            VALUES(tid,r.id,'liberacion',r.monto,p_actor,'Checkout cancelado');
        ELSIF p_accion = 'reintegrar' AND r.estado = 'consumida' THEN
            UPDATE public.reservas_vale SET estado = 'reintegrada' WHERE id = r.id RETURNING * INTO r;
            UPDATE public.tarjetas_regalo SET saldo = saldo + r.monto WHERE id = tid;
            INSERT INTO public.movimientos_vale(tarjeta_id,reserva_id,tipo,monto,actor,motivo)
            VALUES(tid,r.id,'devolucion',r.monto,p_actor,'Reversión de orden');
        ELSIF p_accion = 'restaurar_consumo' AND r.estado = 'reintegrada' THEN
            IF v.saldo < r.monto THEN RETURN jsonb_build_object('error','No hay saldo para compensar la devolución.'); END IF;
            UPDATE public.reservas_vale SET estado = 'consumida' WHERE id = r.id RETURNING * INTO r;
            UPDATE public.tarjetas_regalo SET saldo = saldo - r.monto WHERE id = tid;
            INSERT INTO public.movimientos_vale(tarjeta_id,reserva_id,tipo,monto,actor,motivo)
            VALUES(tid,r.id,'consumo',-r.monto,p_actor,'Compensación de reversión fallida');
        END IF;
        RETURN to_jsonb(r);
    END IF;

    IF p_accion = 'consultar' THEN
        IF v.estado <> 'activa' OR v.saldo <= 0 OR (v.vence_en IS NOT NULL AND v.vence_en <= now()) THEN
            RETURN jsonb_build_object('error','El vale está bloqueado, vencido, anulado o sin saldo.');
        END IF;
        RETURN jsonb_build_object('saldo',v.saldo,'moneda',v.moneda,'codigo_ultimos',v.codigo_ultimos,'vence_en',v.vence_en);
    END IF;
    IF p_accion = 'reservar' THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(p_actor || ':' || (p_datos->>'checkout_id'), 0));
        SELECT * INTO r FROM public.reservas_vale WHERE cliente_id::TEXT = p_actor
            AND checkout_id = p_datos->>'checkout_id' AND estado IN ('reservada','consumida');
        IF FOUND THEN
            IF r.tarjeta_id <> tid OR r.total <> (p_datos->>'total')::NUMERIC THEN
                RETURN jsonb_build_object('error','El checkout ya tiene otro vale o importe reservado.');
            END IF;
            RETURN to_jsonb(r);
        END IF;
        IF v.estado <> 'activa' OR v.saldo <= 0 OR (v.vence_en IS NOT NULL AND v.vence_en <= now()) THEN
            RETURN jsonb_build_object('error','El vale está bloqueado, vencido, anulado o sin saldo.');
        END IF;
        importe := LEAST(v.saldo,(p_datos->>'total')::NUMERIC);
        INSERT INTO public.reservas_vale(id,tarjeta_id,cliente_id,checkout_id,monto,total)
        VALUES((p_datos->>'reserva_id')::UUID,tid,p_actor::UUID,p_datos->>'checkout_id',importe,(p_datos->>'total')::NUMERIC)
        RETURNING * INTO r;
        UPDATE public.tarjetas_regalo SET saldo = saldo - importe,updated_at = now() WHERE id = tid;
        INSERT INTO public.movimientos_vale(tarjeta_id,reserva_id,tipo,monto,actor,motivo)
        VALUES(tid,r.id,'reserva',-importe,p_actor,'Reserva de checkout');
        RETURN to_jsonb(r);
    END IF;

    IF p_accion IN ('estado','regenerar') THEN
        IF EXISTS(SELECT 1 FROM public.reservas_vale WHERE tarjeta_id = tid AND estado = 'reservada') THEN
            RETURN jsonb_build_object('error','Hay un checkout activo. Espera o libera su reserva antes de gestionar el vale.');
        END IF;
        IF v.estado = 'anulada' THEN RETURN jsonb_build_object('error','Una tarjeta anulada no puede modificarse.'); END IF;
        IF p_accion = 'estado' THEN
            UPDATE public.tarjetas_regalo SET estado = p_datos->>'estado',updated_at = now() WHERE id = tid RETURNING * INTO v;
        ELSE
            UPDATE public.tarjetas_regalo SET codigo_hash = p_datos->>'codigo_hash',codigo_version = p_datos->>'codigo_version',
                codigo_ultimos = p_datos->>'codigo_ultimos',updated_at = now() WHERE id = tid RETURNING * INTO v;
        END IF;
        INSERT INTO public.movimientos_vale(tarjeta_id,tipo,actor,motivo)
        VALUES(tid,p_accion || ':' || v.estado,p_actor,p_datos->>'motivo');
        RETURN to_jsonb(v);
    END IF;
    RETURN jsonb_build_object('error','Operación no soportada.','status',400);
END;
$$;
REVOKE ALL ON FUNCTION public.operar_vale(TEXT,TEXT,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.operar_vale(TEXT,TEXT,JSONB) TO service_role;

-- Orden y canje forman una sola transacción: si falla cualquiera, se revierte todo.
CREATE OR REPLACE FUNCTION public.confirmar_orden_con_vale(p_orden JSONB, p_items JSONB, p_pagos JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    r public.reservas_vale%ROWTYPE;
    resultado JSONB;
    consumo JSONB;
BEGIN
    -- Misma jerarquía de locks que operar_vale: tarjeta antes que reserva.
    PERFORM 1 FROM public.tarjetas_regalo WHERE id = (
        SELECT tarjeta_id FROM public.reservas_vale WHERE id = (p_orden->>'vale_reserva_id')::UUID
    ) FOR UPDATE;
    SELECT * INTO r FROM public.reservas_vale WHERE id = (p_orden->>'vale_reserva_id')::UUID FOR UPDATE;
    IF r.id IS NULL OR r.cliente_id::TEXT <> p_orden->>'cliente_id'
       OR r.checkout_id <> p_orden->>'reserva_id' OR r.total <> (p_orden->>'total')::NUMERIC
       OR p_pagos->0->>'metodo' <> 'vale' OR (p_pagos->0->>'monto')::NUMERIC <> r.monto
       OR p_pagos->0->>'transaccion_id' <> 'VALE-' || r.id::TEXT THEN
        RAISE EXCEPTION 'Reserva de vale inconsistente';
    END IF;
    consumo := public.operar_vale('consumir',r.cliente_id::TEXT,
        jsonb_build_object('reserva_id',r.id,'orden_id',p_orden->>'id'));
    IF consumo ? 'error' THEN RAISE EXCEPTION 'El vale no pudo canjearse'; END IF;
    resultado := public.confirmar_orden_atomica(p_orden,p_items,p_pagos);
    RETURN resultado;
END;
$$;
REVOKE ALL ON FUNCTION public.confirmar_orden_con_vale(JSONB,JSONB,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.confirmar_orden_con_vale(JSONB,JSONB,JSONB) TO service_role;
NOTIFY pgrst, 'reload schema';

-- Despachos automáticos por Pub/Sub (RIO-ENT-01/02)
ALTER TABLE public.ordenes ADD COLUMN IF NOT EXISTS entrega JSONB;

-- Register the atomic order RPC used by services/ordenes/app/routers.py.
-- Older deployed databases predate these columns, and the function below writes both.
ALTER TABLE public.ordenes ADD COLUMN IF NOT EXISTS reserva_id TEXT;
ALTER TABLE public.ordenes ADD COLUMN IF NOT EXISTS numero_factura BIGINT;

CREATE OR REPLACE FUNCTION public.confirmar_orden_atomica(
    p_orden JSONB,
    p_items JSONB,
    p_pagos JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_orden_id UUID := (p_orden->>'id')::UUID;
    v_pago JSONB;
    v_tx TEXT;
    v_existing_order UUID;
    v_result JSONB;
BEGIN
    v_tx := COALESCE(p_pagos->0->>'transaccion_id', 'orden:' || v_orden_id::TEXT);
    PERFORM pg_advisory_xact_lock(hashtextextended(v_tx, 0));

    SELECT orden_id INTO v_existing_order
    FROM public.pagos
    WHERE transaccion_id = v_tx AND orden_id IS NOT NULL
    LIMIT 1;

    IF v_existing_order IS NOT NULL THEN
        SELECT jsonb_build_object('id', id, 'codigo_orden', codigo_orden, 'existente', TRUE)
        INTO v_result
        FROM public.ordenes
        WHERE id = v_existing_order;
        RETURN v_result;
    END IF;

    INSERT INTO public.ordenes (
        id, codigo_orden, cliente_id, sucursal_id, canal, tipo_despacho,
        direccion_entrega_id, subtotal, descuento, costo_envio, total, estado,
        tracking_number, reserva_id, cuf_factura, numero_factura, entrega
    )
    VALUES (
        v_orden_id,
        p_orden->>'codigo_orden',
        (p_orden->>'cliente_id')::UUID,
        NULLIF(p_orden->>'sucursal_id', '')::UUID,
        (p_orden->>'canal')::public.canal_venta_enum,
        (p_orden->>'tipo_despacho')::public.tipo_despacho_enum,
        NULLIF(p_orden->>'direccion_entrega_id', '')::UUID,
        (p_orden->>'subtotal')::NUMERIC,
        (p_orden->>'descuento')::NUMERIC,
        (p_orden->>'costo_envio')::NUMERIC,
        (p_orden->>'total')::NUMERIC,
        (p_orden->>'estado')::public.estado_orden_enum,
        p_orden->>'tracking_number',
        p_orden->>'reserva_id',
        p_orden->>'cuf_factura',
        NULLIF(p_orden->>'numero_factura', '')::BIGINT,
        p_orden->'entrega'
    );

    INSERT INTO public.orden_items (
        orden_id, variante_id, sku, nombre_producto, cantidad, precio_unitario, total_linea
    )
    SELECT
        v_orden_id,
        (item.value->>'variante_id')::UUID,
        item.value->>'sku',
        item.value->>'nombre_producto',
        (item.value->>'cantidad')::INT,
        (item.value->>'precio_unitario')::NUMERIC,
        (item.value->>'total_linea')::NUMERIC
    FROM jsonb_array_elements(p_items) AS item(value);

    FOR v_pago IN SELECT value FROM jsonb_array_elements(p_pagos)
    LOOP
        INSERT INTO public.pagos (
            orden_id, transaccion_id, metodo, monto, moneda, estado, raw_payload
        )
        VALUES (
            v_orden_id,
            v_pago->>'transaccion_id',
            (v_pago->>'metodo')::public.metodo_pago_enum,
            (v_pago->>'monto')::NUMERIC,
            'BOB',
            'aprobado',
            COALESCE(v_pago->'raw_payload', '{}'::JSONB)
        )
        ON CONFLICT (transaccion_id) DO UPDATE
        SET orden_id = EXCLUDED.orden_id,
            estado = 'aprobado',
            raw_payload = EXCLUDED.raw_payload
        WHERE pagos.orden_id IS NULL;
    END LOOP;

    RETURN jsonb_build_object(
        'id', v_orden_id,
        'codigo_orden', p_orden->>'codigo_orden',
        'existente', FALSE
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.confirmar_orden_atomica(JSONB, JSONB, JSONB) TO service_role;
NOTIFY pgrst, 'reload schema';
-- RIO-ENT-01/02. Aplicar después de 20261102_cotizacion_flete.sql.
ALTER TABLE public.ordenes ADD COLUMN IF NOT EXISTS entrega JSONB;

CREATE TABLE public.despachos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    orden_id UUID NOT NULL UNIQUE REFERENCES public.ordenes(id) ON DELETE CASCADE,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN
        ('pendiente','programado','en_preparacion','en_transito','entregado','rechazado','cancelado')),
    guia TEXT, transportista TEXT, ruta TEXT, ubicacion_actual TEXT, motivo TEXT,
    fecha_estimada TIMESTAMPTZ, version BIGINT NOT NULL DEFAULT 0,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE public.despachos_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    despacho_id UUID NOT NULL REFERENCES public.despachos(id) ON DELETE CASCADE,
    tipo_evento TEXT NOT NULL CHECK (tipo_evento IN
        ('despacho.solicitado','despacho.estado.consultado','despacho.cancelacion.solicitada')),
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','procesando','publicado','cancelado')),
    intentos INT NOT NULL DEFAULT 0, message_id TEXT, ultimo_error TEXT,
    disponible_desde TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_id UUID, lease_hasta TIMESTAMPTZ,
    payload JSONB, actor TEXT NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX despachos_solicitud_unica ON public.despachos_outbox(despacho_id)
    WHERE tipo_evento = 'despacho.solicitado';
CREATE UNIQUE INDEX despachos_cancelacion_unica ON public.despachos_outbox(despacho_id)
    WHERE tipo_evento = 'despacho.cancelacion.solicitada';
CREATE INDEX despachos_outbox_pendientes ON public.despachos_outbox(disponible_desde,created_at)
    WHERE estado IN ('pendiente','procesando');
CREATE INDEX despachos_outbox_historial ON public.despachos_outbox(despacho_id,created_at DESC);
CREATE TABLE public.despachos_inbox (
    event_id UUID PRIMARY KEY,
    despacho_id UUID NOT NULL REFERENCES public.despachos(id) ON DELETE CASCADE,
    tipo_evento TEXT NOT NULL, version BIGINT NOT NULL,
    aplicado BOOLEAN NOT NULL DEFAULT FALSE,
    recibido_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX despachos_inbox_historial ON public.despachos_inbox(despacho_id,recibido_en DESC);
ALTER TABLE public.despachos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.despachos_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.despachos_inbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.despachos,public.despachos_outbox,public.despachos_inbox FROM anon,authenticated;
GRANT ALL ON public.despachos,public.despachos_outbox,public.despachos_inbox TO service_role;

CREATE FUNCTION public.encolar_despacho_orden() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public,pg_temp AS $$
DECLARE did UUID;
BEGIN
    IF NEW.tipo_despacho::TEXT <> 'domicilio' THEN RETURN NEW; END IF;
    IF NEW.estado::TEXT = 'confirmada' THEN
        INSERT INTO public.despachos(orden_id) VALUES(NEW.id) ON CONFLICT(orden_id) DO NOTHING;
        SELECT id INTO did FROM public.despachos WHERE orden_id = NEW.id;
        INSERT INTO public.despachos_outbox(despacho_id,tipo_evento)
            VALUES(did,'despacho.solicitado') ON CONFLICT DO NOTHING;
    ELSIF NEW.estado::TEXT = 'cancelada' THEN
        SELECT id INTO did FROM public.despachos WHERE orden_id = NEW.id;
        IF did IS NOT NULL THEN
            UPDATE public.despachos SET estado = 'cancelado',actualizado_en = now() WHERE id = did;
            UPDATE public.despachos_outbox SET estado = 'cancelado' WHERE despacho_id = did
                AND tipo_evento <> 'despacho.cancelacion.solicitada' AND estado IN ('pendiente','procesando');
            INSERT INTO public.despachos_outbox(despacho_id,tipo_evento)
                VALUES(did,'despacho.cancelacion.solicitada') ON CONFLICT DO NOTHING;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.encolar_despacho_orden() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER orden_despacho_outbox AFTER INSERT OR UPDATE OF estado ON public.ordenes
    FOR EACH ROW EXECUTE FUNCTION public.encolar_despacho_orden();

CREATE FUNCTION public.operar_despacho(p_accion TEXT,p_datos JSONB DEFAULT '{}')
RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = public,pg_temp AS $$
DECLARE
    d public.despachos%ROWTYPE;
    e public.despachos_outbox%ROWTYPE;
    o public.ordenes%ROWTYPE;
    filas JSONB := '[]';
    eventos JSONB;
    nuevo_estado TEXT;
    aplicada BOOLEAN := FALSE;
BEGIN
    IF p_accion = 'salud' THEN RETURN jsonb_build_object('habilitado',TRUE); END IF;
    IF p_accion = 'reclamar' THEN
        FOR e IN SELECT * FROM public.despachos_outbox
            WHERE (estado = 'pendiente' OR (estado = 'procesando' AND lease_hasta < now()))
              AND disponible_desde <= now()
            ORDER BY created_at,id LIMIT 10 FOR UPDATE SKIP LOCKED
        LOOP
            SELECT * INTO d FROM public.despachos WHERE id = e.despacho_id;
            SELECT * INTO o FROM public.ordenes WHERE id = d.orden_id;
            IF o.estado::TEXT = 'cancelada' AND e.tipo_evento <> 'despacho.cancelacion.solicitada' THEN
                UPDATE public.despachos_outbox SET estado = 'cancelado' WHERE id = e.id;
                CONTINUE;
            END IF;
            UPDATE public.despachos_outbox SET estado = 'procesando',intentos = intentos+1,
                lease_id = gen_random_uuid(),lease_hasta = now()+interval '2 minutes',
                payload = COALESCE(payload,jsonb_build_object(
                    'version_contrato',1,'solicitud_id',d.id,'orden_id',o.id,'codigo_orden',o.codigo_orden,
                    'sucursal_id',o.sucursal_id,'cliente_id',o.cliente_id,'entrega',o.entrega,
                    'guia',d.guia,'items',COALESCE((SELECT jsonb_agg(jsonb_build_object(
                        'sku',i.sku,'nombre_producto',i.nombre_producto,'cantidad',i.cantidad))
                        FROM public.orden_items i WHERE i.orden_id = o.id),'[]'::JSONB)))
                WHERE id = e.id RETURNING * INTO e;
            filas := filas || jsonb_build_array(to_jsonb(e));
        END LOOP;
        RETURN jsonb_build_object('eventos',filas);
    END IF;
    IF p_accion = 'finalizar' THEN
        UPDATE public.despachos_outbox SET
            estado = CASE WHEN COALESCE(p_datos->>'message_id','') <> '' THEN 'publicado' ELSE 'pendiente' END,
            message_id = p_datos->>'message_id',ultimo_error = p_datos->>'error',
            disponible_desde = now() + make_interval(secs => LEAST(300,POWER(2,LEAST(intentos,8))::INT)),
            lease_id = NULL,lease_hasta = NULL
            WHERE id = (p_datos->>'event_id')::UUID AND lease_id = (p_datos->>'lease_id')::UUID
                AND estado = 'procesando';
        RETURN jsonb_build_object('actualizado',FOUND);
    END IF;
    IF p_accion = 'respuesta' THEN
        -- Orden antes que despacho, igual que el trigger de cancelación.
        PERFORM 1 FROM public.ordenes WHERE id = (
            SELECT orden_id FROM public.despachos WHERE id = (p_datos->>'solicitud_id')::UUID
        ) FOR UPDATE;
        SELECT * INTO d FROM public.despachos WHERE id = (p_datos->>'solicitud_id')::UUID FOR UPDATE;
        IF d.id IS NULL OR d.orden_id <> (p_datos->>'orden_id')::UUID THEN
            RETURN jsonb_build_object('error','La respuesta no corresponde a un despacho conocido.');
        END IF;
        IF NOT EXISTS(SELECT 1 FROM public.despachos_outbox WHERE id = (p_datos->>'request_event_id')::UUID
            AND despacho_id = d.id) THEN RETURN jsonb_build_object('error','La respuesta no corresponde a una solicitud enviada.'); END IF;
        INSERT INTO public.despachos_inbox(event_id,despacho_id,tipo_evento,version)
            VALUES((p_datos->>'event_id')::UUID,d.id,p_datos->>'event_type',(p_datos->>'version')::BIGINT)
            ON CONFLICT DO NOTHING;
        IF NOT FOUND THEN RETURN jsonb_build_object('duplicado',TRUE); END IF;
        nuevo_estado := p_datos->>'estado';
        SELECT * INTO o FROM public.ordenes WHERE id = d.orden_id;
        IF (p_datos->>'version')::BIGINT > d.version
            AND (d.estado NOT IN ('entregado','cancelado') OR nuevo_estado = d.estado)
            AND (d.estado <> 'en_transito' OR nuevo_estado IN ('en_transito','entregado','cancelado'))
            AND (d.estado <> 'en_preparacion' OR nuevo_estado <> 'programado')
            AND (o.estado::TEXT <> 'cancelada' OR nuevo_estado = 'cancelado') THEN
            UPDATE public.despachos SET estado = nuevo_estado,guia = COALESCE(p_datos->>'guia',guia),
                transportista = COALESCE(p_datos->>'transportista',transportista),
                ruta = COALESCE(p_datos->>'ruta',ruta),ubicacion_actual = p_datos->>'ubicacion_actual',
                motivo = p_datos->>'motivo',fecha_estimada = (p_datos->>'fecha_estimada')::TIMESTAMPTZ,
                version = (p_datos->>'version')::BIGINT,actualizado_en = now() WHERE id = d.id;
            UPDATE public.ordenes SET tracking_number = COALESCE(p_datos->>'guia',tracking_number) WHERE id = d.orden_id;
            IF nuevo_estado = 'en_preparacion' AND o.estado::TEXT = 'confirmada' THEN
                UPDATE public.ordenes SET estado = 'en_preparacion' WHERE id = d.orden_id;
            ELSIF nuevo_estado = 'en_transito' AND o.estado::TEXT IN ('confirmada','en_preparacion') THEN
                UPDATE public.ordenes SET estado = 'despachada' WHERE id = d.orden_id;
            ELSIF nuevo_estado = 'entregado' AND o.estado::TEXT IN ('confirmada','en_preparacion','despachada') THEN
                UPDATE public.ordenes SET estado = 'entregada' WHERE id = d.orden_id;
            END IF;
            aplicada := TRUE;
        END IF;
        UPDATE public.despachos_inbox SET aplicado = aplicada WHERE event_id = (p_datos->>'event_id')::UUID;
        RETURN jsonb_build_object('aplicado',aplicada);
    END IF;

    SELECT * INTO o FROM public.ordenes WHERE id = (p_datos->>'orden_id')::UUID;
    IF o.id IS NULL THEN RETURN jsonb_build_object('error','Orden no encontrada.','status',404); END IF;
    IF o.tipo_despacho::TEXT <> 'domicilio' THEN RETURN jsonb_build_object('error','La orden no requiere envío a domicilio.'); END IF;
    SELECT * INTO d FROM public.despachos WHERE orden_id = o.id FOR UPDATE;
    IF d.id IS NULL AND p_accion = 'reintentar' AND o.estado::TEXT IN ('confirmada','en_preparacion') AND o.tracking_number IS NULL THEN
        INSERT INTO public.despachos(orden_id) VALUES(o.id) ON CONFLICT(orden_id) DO NOTHING;
        SELECT * INTO d FROM public.despachos WHERE orden_id = o.id FOR UPDATE;
        INSERT INTO public.despachos_outbox(despacho_id,tipo_evento) VALUES(d.id,'despacho.solicitado') ON CONFLICT DO NOTHING;
    END IF;
    IF d.id IS NULL THEN RETURN jsonb_build_object('error','El despacho todavía no está registrado.','status',404); END IF;
    IF p_accion = 'consultar' THEN
        IF o.estado::TEXT = 'cancelada' THEN RETURN jsonb_build_object('error','La orden está cancelada.'); END IF;
        INSERT INTO public.despachos_outbox(despacho_id,tipo_evento,actor)
            VALUES(d.id,'despacho.estado.consultado',p_datos->>'actor');
    ELSIF p_accion = 'reintentar' THEN
        IF o.estado::TEXT NOT IN ('confirmada','en_preparacion') OR d.estado <> 'pendiente' THEN
            RETURN jsonb_build_object('error','Solo se puede reintentar un despacho pendiente de una orden confirmada.');
        END IF;
        UPDATE public.despachos_outbox SET estado = 'pendiente',disponible_desde = now(),actor = p_datos->>'actor'
            WHERE despacho_id = d.id AND tipo_evento = 'despacho.solicitado'
              AND (estado <> 'procesando' OR lease_hasta < now());
    ELSIF p_accion <> 'obtener' THEN RETURN jsonb_build_object('error','Operación inválida.'); END IF;
    SELECT COALESCE(jsonb_agg(fila),'[]'::JSONB) INTO eventos FROM (
        SELECT jsonb_build_object('id',id,'tipo_evento',tipo_evento,'estado',estado,'intentos',intentos,
            'message_id',message_id,'ultimo_error',ultimo_error,'created_at',created_at,'actor',actor) fila
        FROM public.despachos_outbox WHERE despacho_id = d.id ORDER BY created_at DESC,id LIMIT 20
    ) resumen;
    RETURN to_jsonb(d) || jsonb_build_object('eventos',eventos);
END;
$$;
REVOKE ALL ON FUNCTION public.operar_despacho(TEXT,JSONB) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.operar_despacho(TEXT,JSONB) TO service_role;
NOTIFY pgrst,'reload schema';

-- Auditoría de Entregas y cola independiente para cotizaciones de simulación.
CREATE TABLE public.envios_mensajes_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT NOT NULL, tipo_evento TEXT NOT NULL,
    direccion TEXT NOT NULL CHECK (direccion IN ('salida','entrada')),
    estado TEXT NOT NULL, orden_id UUID, correlation_id TEXT, simulacion BOOLEAN NOT NULL DEFAULT FALSE,
    topic TEXT, message_id TEXT, ultimo_error TEXT, estado_logistico TEXT,
    mensaje JSONB NOT NULL, atributos JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX envios_log_fecha ON public.envios_mensajes_log(created_at DESC,id);
CREATE INDEX envios_log_orden ON public.envios_mensajes_log(orden_id,created_at DESC);
CREATE INDEX envios_log_evento ON public.envios_mensajes_log(event_id);

CREATE TABLE public.envios_cotizaciones_outbox (
    id UUID PRIMARY KEY, payload JSONB NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','procesando','publicado')),
    intentos INT NOT NULL DEFAULT 0, message_id TEXT, ultimo_error TEXT,
    disponible_desde TIMESTAMPTZ NOT NULL DEFAULT now(), lease_id UUID, lease_hasta TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), publicado_en TIMESTAMPTZ
);
CREATE INDEX cotizaciones_envio_pendientes ON public.envios_cotizaciones_outbox(disponible_desde)
    WHERE estado IN ('pendiente','procesando');
ALTER TABLE public.envios_mensajes_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.envios_cotizaciones_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.envios_mensajes_log,public.envios_cotizaciones_outbox FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.envios_mensajes_log,public.envios_cotizaciones_outbox TO service_role;

CREATE FUNCTION public.operar_cotizacion_envio(p_accion TEXT,p_datos JSONB DEFAULT '{}') RETURNS JSONB
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE fila public.envios_cotizaciones_outbox%ROWTYPE; eventos JSONB := '[]';
BEGIN
    IF p_accion = 'encolar' THEN
        IF p_datos->'payload'->'simulacion' IS DISTINCT FROM 'true'::JSONB THEN
            RAISE EXCEPTION 'Solo se permiten cotizaciones de simulación';
        END IF;
        INSERT INTO public.envios_cotizaciones_outbox(id,payload)
            VALUES((p_datos->>'id')::UUID,p_datos->'payload') ON CONFLICT DO NOTHING;
        RETURN jsonb_build_object('encolado',TRUE);
    ELSIF p_accion = 'reclamar' THEN
        FOR fila IN SELECT * FROM public.envios_cotizaciones_outbox
            WHERE (estado='pendiente' OR (estado='procesando' AND lease_hasta < now()))
              AND disponible_desde <= now()
            ORDER BY created_at,id LIMIT 10 FOR UPDATE SKIP LOCKED
        LOOP
            UPDATE public.envios_cotizaciones_outbox SET estado='procesando',intentos=intentos+1,
                lease_id=gen_random_uuid(),lease_hasta=now()+interval '2 minutes'
                WHERE id=fila.id RETURNING * INTO fila;
            eventos := eventos || jsonb_build_array(to_jsonb(fila));
        END LOOP;
        RETURN jsonb_build_object('eventos',eventos);
    ELSIF p_accion = 'finalizar' THEN
        UPDATE public.envios_cotizaciones_outbox SET
            estado=CASE WHEN COALESCE(p_datos->>'message_id','')<>'' THEN 'publicado' ELSE 'pendiente' END,
            message_id=p_datos->>'message_id',ultimo_error=p_datos->>'error',
            publicado_en=CASE WHEN COALESCE(p_datos->>'message_id','')<>'' THEN now() ELSE NULL END,
            disponible_desde=now()+make_interval(secs=>LEAST(300,POWER(2,LEAST(intentos,8))::INT)),
            lease_id=NULL,lease_hasta=NULL
            WHERE id=(p_datos->>'id')::UUID AND lease_id=(p_datos->>'lease_id')::UUID AND estado='procesando';
        RETURN jsonb_build_object('actualizado',FOUND);
    END IF;
    RAISE EXCEPTION 'Operación de cotización inválida';
END;
$$;
REVOKE ALL ON FUNCTION public.operar_cotizacion_envio(TEXT,JSONB) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.operar_cotizacion_envio(TEXT,JSONB) TO service_role;

-- Estado actual de todas las colas + cada publicación/recepción registrada.
-- Las respuestas históricas solo conservan los metadatos existentes, sin inventar su contenido.
CREATE VIEW public.envios_trazabilidad WITH (security_invoker=true) AS
SELECT 'log-'||l.id::TEXT AS id,l.event_id,l.tipo_evento,l.direccion,l.estado,l.orden_id,l.correlation_id,
    l.simulacion,l.topic,l.message_id,0 AS intentos,l.ultimo_error,l.estado_logistico,
    l.mensaje,l.atributos,l.created_at,'mensaje'::TEXT AS registro
FROM public.envios_mensajes_log l
UNION ALL
SELECT 'despacho-'||e.id::TEXT,e.id::TEXT,e.tipo_evento,'salida',e.estado,d.orden_id,d.id::TEXT,
    FALSE,NULL,e.message_id,e.intentos,e.ultimo_error,d.estado,
    jsonb_build_object('payload',e.payload),jsonb_build_object('destino','entregas'),e.created_at,'estado_actual'
FROM public.despachos_outbox e JOIN public.despachos d ON d.id=e.despacho_id
UNION ALL
SELECT 'cotizacion-'||c.id::TEXT,c.id::TEXT,'despacho.cotizacion.calculada','salida',c.estado,NULL,c.id::TEXT,
    TRUE,NULL,c.message_id,c.intentos,c.ultimo_error,NULL,
    jsonb_build_object('payload',c.payload),jsonb_build_object('destino','entregas','simulacion','true'),c.created_at,'estado_actual'
FROM public.envios_cotizaciones_outbox c
UNION ALL
SELECT 'inbox-'||i.event_id::TEXT,i.event_id::TEXT,i.tipo_evento,'entrada',
    CASE WHEN i.aplicado THEN 'aplicado' ELSE 'ignorado' END,d.orden_id,d.id::TEXT,
    FALSE,NULL,NULL,0,NULL,NULL,jsonb_build_object('version',i.version),'{}'::JSONB,i.recibido_en,'metadatos_historicos'
FROM public.despachos_inbox i JOIN public.despachos d ON d.id=i.despacho_id
WHERE NOT EXISTS(SELECT 1 FROM public.envios_mensajes_log l WHERE l.event_id=i.event_id::TEXT AND l.direccion='entrada');
REVOKE ALL ON public.envios_trazabilidad FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.envios_trazabilidad TO service_role;
NOTIFY pgrst,'reload schema';


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


CREATE TABLE IF NOT EXISTS public.cotizaciones_configuracion (
  id integer PRIMARY KEY CHECK (id=1),
  version integer NOT NULL CHECK (version>0),
  configuracion jsonb NOT NULL CHECK (jsonb_typeof(configuracion)='object'),
  actualizado_por uuid,
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
INSERT INTO public.cotizaciones_configuracion(id,version,configuracion) VALUES
  (1,1,'{"habilitado":true,"escalas":[{"minimo_unidades":5,"descuento_porcentaje":5},{"minimo_unidades":10,"descuento_porcentaje":10},{"minimo_unidades":20,"descuento_porcentaje":15}]}')
ON CONFLICT(id) DO NOTHING;
ALTER TABLE public.cotizaciones_configuracion ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.cotizaciones_configuracion FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,UPDATE ON public.cotizaciones_configuracion TO service_role;

ALTER TABLE public.cotizaciones_b2b ADD COLUMN IF NOT EXISTS configuracion_descuento_version integer;
ALTER TABLE public.cotizaciones_b2b ADD COLUMN IF NOT EXISTS reglas_descuento jsonb;

CREATE OR REPLACE FUNCTION public.guardar_configuracion_cotizaciones(p_version integer,p_configuracion jsonb,p_actor uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE anterior public.cotizaciones_configuracion; nuevo public.cotizaciones_configuracion;
BEGIN
  SELECT * INTO anterior FROM public.cotizaciones_configuracion WHERE id=1 FOR UPDATE;
  IF anterior.id IS NULL THEN RETURN jsonb_build_object('status',503,'error','No existe la configuración B2B.'); END IF;
  IF anterior.version<>p_version THEN
    RETURN jsonb_build_object('status',409,'error','Otro usuario actualizó los descuentos. Recarga las reglas antes de guardar.');
  END IF;
  IF jsonb_typeof(p_configuracion) IS DISTINCT FROM 'object' OR jsonb_typeof(p_configuracion->'escalas') IS DISTINCT FROM 'array'
     OR jsonb_typeof(p_configuracion->'habilitado') IS DISTINCT FROM 'boolean' THEN
    RETURN jsonb_build_object('status',422,'error','La configuración de descuentos no es válida.');
  END IF;
  UPDATE public.cotizaciones_configuracion SET version=version+1,configuracion=p_configuracion,
    actualizado_por=p_actor,actualizado_en=now() WHERE id=1 RETURNING * INTO nuevo;
  RETURN jsonb_build_object('registro',to_jsonb(nuevo),'anterior',to_jsonb(anterior));
END;
$$;
REVOKE ALL ON FUNCTION public.guardar_configuracion_cotizaciones(integer,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.guardar_configuracion_cotizaciones(integer,jsonb,uuid) TO service_role;

-- El alta comercial no crea usuarios Auth ni modifica clientes existentes.
CREATE OR REPLACE FUNCTION public.registrar_empresa_b2b(p_datos jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE nit text:=trim(p_datos->>'nit_ci'); correo text:=lower(trim(p_datos->>'email'));
        empresa public.perfiles_clientes;
BEGIN
  IF nit IS NULL OR nit !~ '^[0-9]{5,20}$' OR coalesce(length(trim(p_datos->>'razon_social')),0)<2
     OR correo IS NULL OR position('@' in correo)=0 THEN
    RETURN jsonb_build_object('status',422,'error','Completa un NIT, razón social y correo válidos.');
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('empresa_b2b:'||nit,0));
  SELECT * INTO empresa FROM public.perfiles_clientes
    WHERE regexp_replace(nit_ci,'[^0-9]','','g')=nit
    ORDER BY (tipo_cliente::text='corporativo_b2b') DESC NULLS LAST,created_at,id LIMIT 1;
  IF empresa.id IS NOT NULL THEN
    IF empresa.tipo_cliente::text='corporativo_b2b' THEN
      RETURN jsonb_build_object('cliente',to_jsonb(empresa),'creado',false);
    END IF;
    RETURN jsonb_build_object('status',409,'error','Este NIT ya pertenece a un cliente particular. Su clasificación debe revisarse antes de registrarlo como empresa.');
  END IF;
  IF EXISTS(SELECT 1 FROM public.perfiles_clientes WHERE lower(email)=correo) THEN
    RETURN jsonb_build_object('status',409,'error','Este correo ya pertenece a otro cliente. Usa el correo comercial de la empresa.');
  END IF;
  INSERT INTO public.perfiles_clientes(nombre_completo,razon_social,nit_ci,email,telefono,tipo_cliente)
    VALUES(coalesce(nullif(trim(p_datos->>'nombre_completo'),''),trim(p_datos->>'razon_social')),
      trim(p_datos->>'razon_social'),nit,correo,nullif(trim(p_datos->>'telefono'),''),'corporativo_b2b')
    RETURNING * INTO empresa;
  RETURN jsonb_build_object('cliente',to_jsonb(empresa),'creado',true);
EXCEPTION WHEN unique_violation THEN
  RETURN jsonb_build_object('status',409,'error','La empresa o su correo ya fueron registrados por otro usuario. Busca el NIT nuevamente.');
END;
$$;
REVOKE ALL ON FUNCTION public.registrar_empresa_b2b(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.registrar_empresa_b2b(jsonb) TO service_role;

-- Estructura de KAN-341 y cierre del turno junto con su reporte en una transacción.
ALTER TABLE public.caja_turnos ADD COLUMN IF NOT EXISTS con_diferencia BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS public.arqueo_caja (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_reporte VARCHAR(40) NOT NULL UNIQUE,
    caja_turno_id UUID NOT NULL UNIQUE REFERENCES public.caja_turnos(id),
    cajero_id UUID NOT NULL, sucursal_id UUID NOT NULL,
    fondo_inicial NUMERIC(12,2) NOT NULL, ventas_efectivo NUMERIC(12,2) NOT NULL DEFAULT 0,
    entradas_extraordinarias NUMERIC(12,2) NOT NULL DEFAULT 0, retiros_boveda NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_esperado NUMERIC(12,2) NOT NULL, total_declarado NUMERIC(12,2) NOT NULL CHECK (total_declarado >= 0),
    diferencia NUMERIC(12,2) NOT NULL,
    estado_cuadre VARCHAR(10) NOT NULL CHECK (estado_cuadre IN ('cuadrado', 'sobrante', 'faltante')),
    con_diferencia BOOLEAN NOT NULL DEFAULT FALSE, observaciones TEXT,
    total_tarjeta NUMERIC(12,2) NOT NULL DEFAULT 0, total_qr NUMERIC(12,2) NOT NULL DEFAULT 0,
    notificacion_contabilidad JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.arqueo_detalle (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arqueo_id UUID NOT NULL REFERENCES public.arqueo_caja(id),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('billete', 'moneda')),
    denominacion NUMERIC(6,2) NOT NULL CHECK (denominacion IN (200,100,50,20,10,5,2,1,0.50,0.20,0.10)),
    cantidad INT NOT NULL CHECK (cantidad >= 0), subtotal NUMERIC(12,2) NOT NULL CHECK (subtotal >= 0),
    UNIQUE (arqueo_id, denominacion)
);
CREATE INDEX IF NOT EXISTS idx_arqueo_caja_sucursal_fecha ON public.arqueo_caja(sucursal_id, created_at DESC);
ALTER TABLE public.arqueo_caja ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.arqueo_detalle ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.arqueo_caja, public.arqueo_detalle FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.arqueo_caja, public.arqueo_detalle TO service_role;

CREATE OR REPLACE FUNCTION public.proteger_arqueo_congelado() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'El arqueo es inmutable'; END IF;
    IF TG_TABLE_NAME = 'arqueo_caja' AND
       (to_jsonb(NEW) - 'notificacion_contabilidad') IS NOT DISTINCT FROM (to_jsonb(OLD) - 'notificacion_contabilidad') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'El arqueo es inmutable';
END;
$$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='public.arqueo_caja'::regclass AND tgname='trg_arqueo_caja_inmutable' AND NOT tgisinternal) THEN
        CREATE TRIGGER trg_arqueo_caja_inmutable BEFORE UPDATE OR DELETE ON public.arqueo_caja FOR EACH ROW EXECUTE FUNCTION public.proteger_arqueo_congelado();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='public.arqueo_detalle'::regclass AND tgname='trg_arqueo_detalle_inmutable' AND NOT tgisinternal) THEN
        CREATE TRIGGER trg_arqueo_detalle_inmutable BEFORE UPDATE OR DELETE ON public.arqueo_detalle FOR EACH ROW EXECUTE FUNCTION public.proteger_arqueo_congelado();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.confirmar_arqueo_ciego(p_arqueo JSONB, p_detalle JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_id UUID := (p_arqueo->>'id')::UUID;
BEGIN
    UPDATE public.caja_turnos SET estado='cerrada', monto_cierre_real=(p_arqueo->>'total_declarado')::numeric,
        diferencia=(p_arqueo->>'diferencia')::numeric, con_diferencia=(p_arqueo->>'con_diferencia')::boolean,
        observaciones=p_arqueo->>'observaciones', closed_at=(p_arqueo->>'created_at')::timestamptz
    WHERE id=(p_arqueo->>'caja_turno_id')::uuid AND estado='abierta';
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO public.arqueo_caja SELECT * FROM jsonb_populate_record(NULL::public.arqueo_caja, p_arqueo);
    INSERT INTO public.arqueo_detalle (arqueo_id,tipo,denominacion,cantidad,subtotal)
    SELECT v_id, d.tipo, d.denominacion, d.cantidad, d.subtotal
    FROM jsonb_to_recordset(p_detalle) AS d(tipo text, denominacion numeric, cantidad integer, subtotal numeric);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.confirmar_arqueo_ciego(JSONB,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.confirmar_arqueo_ciego(JSONB,JSONB) TO service_role;

ALTER TABLE public.usuarios_internos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.usuarios_internos FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.usuarios_internos TO service_role;

-- Una simulación no es un reembolso completado y no afecta el saldo real.
ALTER TABLE public.reembolsos DROP CONSTRAINT IF EXISTS chk_reembolsos_estado;
ALTER TABLE public.reembolsos ADD CONSTRAINT chk_reembolsos_estado
    CHECK (estado IN ('solicitado', 'procesando', 'completado', 'fallido', 'simulado'));

ALTER TABLE public.ordenes ALTER COLUMN cliente_id DROP NOT NULL;
ALTER TABLE public.ordenes ADD CONSTRAINT ordenes_cliente_requerido_fuera_pos CHECK (canal = 'pos' OR cliente_id IS NOT NULL);

CREATE OR REPLACE FUNCTION public.crear_orden_pendiente_atomica(p_orden jsonb, p_items jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
BEGIN
  INSERT INTO public.ordenes (id, codigo_orden, cliente_id, canal, tipo_despacho, subtotal, descuento, total, estado)
  VALUES ((p_orden->>'id')::uuid, p_orden->>'codigo_orden', (p_orden->>'cliente_id')::uuid,
    (p_orden->>'canal')::canal_venta_enum, (p_orden->>'tipo_despacho')::tipo_despacho_enum,
    (p_orden->>'subtotal')::numeric, (p_orden->>'descuento')::numeric, (p_orden->>'total')::numeric, 'pendiente');
  INSERT INTO public.orden_items (id, orden_id, variante_id, sku, nombre_producto, cantidad, precio_unitario, total_linea)
  SELECT (i->>'id')::uuid, (p_orden->>'id')::uuid, (i->>'variante_id')::uuid, i->>'sku',
    i->>'nombre_producto', (i->>'cantidad')::integer, (i->>'precio_unitario')::numeric, (i->>'total_linea')::numeric
  FROM jsonb_array_elements(p_items) i;
END;
$$;
REVOKE ALL ON FUNCTION public.crear_orden_pendiente_atomica(jsonb, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.crear_orden_pendiente_atomica(jsonb, jsonb) TO service_role;

CREATE TABLE IF NOT EXISTS public.preferencias_notificacion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id uuid UNIQUE NOT NULL REFERENCES public.perfiles_clientes(id) ON DELETE CASCADE,
  canal_correo boolean NOT NULL DEFAULT true,
  canal_sms boolean NOT NULL DEFAULT false,
  canal_push boolean NOT NULL DEFAULT false,
  telefono_sms varchar(50),
  avisos_estado_pedido boolean NOT NULL DEFAULT true,
  avisos_promociones boolean NOT NULL DEFAULT false,
  avisos_recordatorios boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.preferencias_notificacion ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_preferencias_notificacion_cliente ON public.preferencias_notificacion(cliente_id);

CREATE OR REPLACE FUNCTION public.encolar_notificacion_estado_orden()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE correo text; permitido boolean; etiqueta text; codigo text;
BEGIN
  IF NEW.estado IS NOT DISTINCT FROM OLD.estado OR NEW.cliente_id IS NULL THEN RETURN NEW; END IF;
  SELECT p.email, coalesce(n.canal_correo, true) AND coalesce(n.avisos_estado_pedido, true)
    INTO correo, permitido FROM public.perfiles_clientes p
    LEFT JOIN public.preferencias_notificacion n ON n.cliente_id=p.id WHERE p.id=NEW.cliente_id;
  IF correo IS NULL OR btrim(correo) = '' OR NOT coalesce(permitido,false) THEN RETURN NEW; END IF;
  etiqueta := CASE NEW.estado::text WHEN 'confirmada' THEN 'Confirmado' WHEN 'en_preparacion' THEN 'En preparación' WHEN 'despachada' THEN 'Despachado' WHEN 'entregada' THEN 'Entregado' WHEN 'cancelada' THEN 'Cancelado' ELSE initcap(replace(NEW.estado::text,'_',' ')) END;
  codigo := replace(replace(replace(NEW.codigo_orden,'&','&amp;'),'<','&lt;'),'>','&gt;');
  INSERT INTO public.notificaciones_log(event_key,orden_id,cliente_id,correo_destino,estado_orden,asunto,contenido)
  VALUES ('estado:' || gen_random_uuid()::text, NEW.id, NEW.cliente_id, correo, NEW.estado::text,
    'Actualización de tu pedido ' || NEW.codigo_orden || ': ' || etiqueta,
    '<html><body><h2>Tu pedido ' || codigo || ' está: ' || etiqueta || '</h2><p>Te avisamos que el estado de tu pedido tuvo una actualización.</p><p><a href="{{SEGUIMIENTO_URL}}">Consultar seguimiento del pedido</a></p><p>Gracias por comprar en MaxiConecta.</p></body></html>');
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.encolar_notificacion_estado_orden() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS notificar_estado_orden ON public.ordenes;
CREATE TRIGGER notificar_estado_orden AFTER UPDATE OF estado ON public.ordenes
FOR EACH ROW EXECUTE FUNCTION public.encolar_notificacion_estado_orden();

-- RIO-CRM-01: perfil y direcciones en una outbox transaccional para Pub/Sub.
ALTER TABLE public.perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_estado varchar(30) DEFAULT 'pendiente';
ALTER TABLE public.perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_at timestamptz;
ALTER TABLE public.perfiles_clientes ADD COLUMN IF NOT EXISTS crm_contact_id varchar(100);
ALTER TABLE public.perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_version bigint NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.outbox_eventos_crm (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id varchar(100) UNIQUE NOT NULL,
  cliente_id uuid REFERENCES public.perfiles_clientes(id) ON DELETE CASCADE,
  event_type varchar(100) NOT NULL,
  topic varchar(255) NOT NULL DEFAULT 'projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e',
  payload jsonb NOT NULL, attributes jsonb DEFAULT '{}'::jsonb,
  estado varchar(30) NOT NULL DEFAULT 'pendiente', intentos int NOT NULL DEFAULT 0,
  max_intentos int NOT NULL DEFAULT 5, ultimo_error text, message_id varchar(100),
  created_at timestamptz DEFAULT now(), sent_at timestamptz, updated_at timestamptz DEFAULT now()
);
ALTER TABLE public.outbox_eventos_crm DROP CONSTRAINT IF EXISTS outbox_eventos_crm_estado_check;
ALTER TABLE public.outbox_eventos_crm ADD CONSTRAINT outbox_eventos_crm_estado_check
 CHECK (estado IN ('pendiente','publicando','publicado','sincronizado','error','reintentando'));
ALTER TABLE public.outbox_eventos_crm ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE public.outbox_eventos_crm ADD COLUMN IF NOT EXISTS proximo_intento_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE public.outbox_eventos_crm ADD COLUMN IF NOT EXISTS lease_id uuid;
ALTER TABLE public.outbox_eventos_crm ADD COLUMN IF NOT EXISTS lease_hasta timestamptz;

CREATE TABLE IF NOT EXISTS public.crm_suscripcion_verificacion (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id varchar(100) UNIQUE NOT NULL,
 event_type varchar(100) NOT NULL, cliente_id uuid, payload jsonb NOT NULL,
 ignorado_duplicado boolean NOT NULL DEFAULT false, recibido_at timestamptz DEFAULT now()
);
ALTER TABLE public.crm_suscripcion_verificacion ADD COLUMN IF NOT EXISTS duplicados int NOT NULL DEFAULT 0;
ALTER TABLE public.crm_suscripcion_verificacion ADD COLUMN IF NOT EXISTS message_id text;
ALTER TABLE public.crm_suscripcion_verificacion ADD COLUMN IF NOT EXISTS aplicado boolean NOT NULL DEFAULT false;
ALTER TABLE public.crm_suscripcion_verificacion ADD COLUMN IF NOT EXISTS crm_status text;
CREATE INDEX IF NOT EXISTS idx_crm_outbox_pendiente ON public.outbox_eventos_crm(estado,proximo_intento_at);

ALTER TABLE public.outbox_eventos_crm ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_suscripcion_verificacion ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.outbox_eventos_crm, public.crm_suscripcion_verificacion FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.outbox_eventos_crm, public.crm_suscripcion_verificacion TO service_role;

CREATE OR REPLACE FUNCTION public.encolar_cliente_crm(p_cliente uuid, p_tipo text DEFAULT 'cliente.actualizado')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c public.perfiles_clientes; e public.outbox_eventos_crm; eid uuid := gen_random_uuid(); direcciones jsonb;
BEGIN
 UPDATE public.perfiles_clientes SET crm_sync_version=crm_sync_version+1, crm_sync_estado='pendiente'
 WHERE id=p_cliente RETURNING * INTO c;
 IF c.id IS NULL THEN RETURN jsonb_build_object('error','Cliente no encontrado.','status',404); END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'direccion',direccion,'referencia',referencia,
  'ciudad',ciudad,'zona',zona,'latitud',latitud,'longitud',longitud,'es_predeterminada',es_predeterminada)
  ORDER BY es_predeterminada DESC, created_at, id),'[]'::jsonb) INTO direcciones
 FROM public.direcciones_cliente WHERE cliente_id=p_cliente;
 INSERT INTO public.outbox_eventos_crm(id,event_id,cliente_id,event_type,version,payload,attributes)
 VALUES(eid,eid::text,c.id,p_tipo,c.crm_sync_version,
  jsonb_build_object('version_contrato',1,'version',c.crm_sync_version,'cliente_id',c.id,
   'nombre_completo',c.nombre_completo,'email',c.email,'telefono',c.telefono,'nit_ci',c.nit_ci,
   'razon_social',c.razon_social,'tipo_cliente',c.tipo_cliente,'crm_contact_id',c.crm_contact_id,
   'fecha_registro',c.created_at,'direcciones',direcciones),
  jsonb_build_object('destino','crm','version_contrato','1','cliente_id',c.id::text)) RETURNING * INTO e;
 RETURN to_jsonb(e);
END $$;

CREATE OR REPLACE FUNCTION public.trigger_cliente_crm()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
 IF TG_OP='INSERT' THEN PERFORM public.encolar_cliente_crm(NEW.id,'cliente.creado');
 ELSIF ROW(NEW.nombre_completo,NEW.email,NEW.telefono,NEW.nit_ci,NEW.razon_social,NEW.tipo_cliente)
  IS DISTINCT FROM ROW(OLD.nombre_completo,OLD.email,OLD.telefono,OLD.nit_ci,OLD.razon_social,OLD.tipo_cliente)
 THEN PERFORM public.encolar_cliente_crm(NEW.id,'cliente.actualizado'); END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS cliente_crm_outbox ON public.perfiles_clientes;
CREATE TRIGGER cliente_crm_outbox AFTER INSERT OR UPDATE OF nombre_completo,email,telefono,nit_ci,razon_social,tipo_cliente
 ON public.perfiles_clientes FOR EACH ROW EXECUTE FUNCTION public.trigger_cliente_crm();

CREATE OR REPLACE FUNCTION public.trigger_direccion_crm()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
 IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM public.encolar_cliente_crm(OLD.cliente_id); RETURN OLD; END IF;
 PERFORM public.encolar_cliente_crm(NEW.cliente_id);
 IF TG_OP='UPDATE' AND OLD.cliente_id IS DISTINCT FROM NEW.cliente_id THEN PERFORM public.encolar_cliente_crm(OLD.cliente_id); END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS direccion_crm_outbox ON public.direcciones_cliente;
CREATE TRIGGER direccion_crm_outbox AFTER INSERT OR UPDATE OR DELETE ON public.direcciones_cliente
 FOR EACH ROW EXECUTE FUNCTION public.trigger_direccion_crm();

CREATE OR REPLACE FUNCTION public.operar_crm(p_accion text,p_datos jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE eventos jsonb; e public.outbox_eventos_crm; respuesta jsonb; cid uuid; estado_cliente text; actualizado boolean;
BEGIN
 IF p_accion='encolar' THEN RETURN public.encolar_cliente_crm((p_datos->>'cliente_id')::uuid); END IF;
 IF p_accion='reclamar' THEN
  UPDATE public.outbox_eventos_crm SET estado='error',ultimo_error='Se agotaron los intentos de publicación.'
   WHERE estado='publicando' AND lease_hasta<now() AND intentos>=max_intentos;
  WITH candidatos AS (
   SELECT id FROM public.outbox_eventos_crm WHERE intentos<max_intentos AND
    ((estado IN ('pendiente','reintentando') AND proximo_intento_at<=now()) OR (estado='publicando' AND lease_hasta<now()))
   ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT least(greatest(coalesce((p_datos->>'limite')::int,10),1),50)
  ), reclamados AS (
   UPDATE public.outbox_eventos_crm o SET estado='publicando',intentos=intentos+1,lease_id=gen_random_uuid(),
    lease_hasta=now()+interval '2 minutes',updated_at=now() FROM candidatos c WHERE o.id=c.id RETURNING o.*
  ) SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]'::jsonb) INTO eventos FROM reclamados r;
  RETURN jsonb_build_object('eventos',eventos);
 END IF;
 IF p_accion='finalizar' THEN
  SELECT cliente_id INTO cid FROM public.outbox_eventos_crm WHERE id=(p_datos->>'id')::uuid;
  PERFORM 1 FROM public.perfiles_clientes WHERE id=cid FOR UPDATE;
  SELECT * INTO e FROM public.outbox_eventos_crm WHERE id=(p_datos->>'id')::uuid FOR UPDATE;
  IF e.id IS NULL OR e.lease_id IS DISTINCT FROM (p_datos->>'lease_id')::uuid THEN RETURN jsonb_build_object('ignorado',true); END IF;
  UPDATE public.outbox_eventos_crm SET
   estado=CASE WHEN estado IN ('sincronizado','error') THEN estado WHEN p_datos->>'message_id' IS NOT NULL THEN 'publicado'
     WHEN intentos>=max_intentos THEN 'error' ELSE 'reintentando' END,
   topic=coalesce(p_datos->>'topic',topic),message_id=coalesce(p_datos->>'message_id',message_id),
   sent_at=CASE WHEN p_datos->>'message_id' IS NOT NULL THEN now() ELSE sent_at END,
   ultimo_error=CASE WHEN estado IN ('sincronizado','error') THEN ultimo_error ELSE p_datos->>'error' END,lease_hasta=NULL,lease_id=NULL,updated_at=now(),
   proximo_intento_at=now()+make_interval(secs=>least(600,(power(2,intentos)*5)::int)) WHERE id=e.id RETURNING * INTO e;
  UPDATE public.perfiles_clientes SET crm_sync_estado=e.estado WHERE id=e.cliente_id AND crm_sync_version=e.version AND e.estado<>'sincronizado';
  RETURN to_jsonb(e);
 END IF;
 IF p_accion='respuesta' THEN
  cid := (p_datos->>'cliente_id')::uuid;
  -- Mismo orden de bloqueo que el encolado: cliente, luego evento.
  PERFORM 1 FROM public.perfiles_clientes WHERE id=cid FOR UPDATE;
  SELECT * INTO e FROM public.outbox_eventos_crm WHERE event_id=p_datos->>'request_event_id' AND cliente_id=cid FOR UPDATE;
  IF e.id IS NULL THEN RETURN jsonb_build_object('error','Respuesta sin solicitud correlacionada.','status',409); END IF;
  INSERT INTO public.crm_suscripcion_verificacion(event_id,event_type,cliente_id,payload,message_id,crm_status)
  VALUES(p_datos->>'event_id',p_datos->>'event_type',cid,p_datos,p_datos->>'message_id',p_datos->>'event_type')
  ON CONFLICT(event_id) DO NOTHING RETURNING to_jsonb(crm_suscripcion_verificacion.*) INTO respuesta;
  IF respuesta IS NULL THEN
   UPDATE public.crm_suscripcion_verificacion SET duplicados=duplicados+1 WHERE event_id=p_datos->>'event_id';
   RETURN jsonb_build_object('duplicado',true);
  END IF;
  IF EXISTS(SELECT 1 FROM public.crm_suscripcion_verificacion WHERE payload->>'request_event_id'=p_datos->>'request_event_id'
    AND event_id<>p_datos->>'event_id') THEN RETURN jsonb_build_object('ignorado',true); END IF;
  estado_cliente := CASE WHEN p_datos->>'event_type'='cliente.sincronizado' THEN 'sincronizado' ELSE 'error' END;
  UPDATE public.outbox_eventos_crm SET estado=estado_cliente,ultimo_error=p_datos->>'motivo',updated_at=now() WHERE id=e.id;
  UPDATE public.perfiles_clientes SET crm_sync_estado=estado_cliente,
   crm_sync_at=CASE WHEN estado_cliente='sincronizado' THEN now() ELSE crm_sync_at END,
   crm_contact_id=CASE WHEN estado_cliente='sincronizado' THEN p_datos->>'crm_contact_id' ELSE crm_contact_id END
   WHERE id=cid AND crm_sync_version=e.version;
  actualizado := FOUND;
  UPDATE public.crm_suscripcion_verificacion SET aplicado=actualizado WHERE event_id=p_datos->>'event_id';
  RETURN jsonb_build_object('aplicado',actualizado);
 END IF;
 IF p_accion='estado' THEN
  RETURN jsonb_build_object(
   'clientes',coalesce((SELECT jsonb_agg(to_jsonb(c)) FROM (SELECT id,nombre_completo,email,telefono,tipo_cliente,crm_sync_estado,crm_sync_at,crm_contact_id,crm_sync_version FROM public.perfiles_clientes ORDER BY created_at DESC,id LIMIT 500) c),'[]'::jsonb),
   'metricas_clientes',(SELECT jsonb_build_object('total',count(*),'sincronizados',count(*) FILTER(WHERE crm_sync_estado='sincronizado'),'pendientes',count(*) FILTER(WHERE crm_sync_estado IN ('pendiente','reintentando','publicando','publicado')),'errores',count(*) FILTER(WHERE crm_sync_estado='error')) FROM public.perfiles_clientes),
   'outbox_metricas',(SELECT jsonb_build_object('total_eventos',count(*),'sincronizados',count(*) FILTER(WHERE estado='sincronizado'),'publicados',count(*) FILTER(WHERE estado='publicado'),'pendientes',count(*) FILTER(WHERE estado IN ('pendiente','reintentando','publicando')),'errores',count(*) FILTER(WHERE estado='error')) FROM public.outbox_eventos_crm),
   'crm_verificacion_metricas',(SELECT jsonb_build_object('total_mensajes_recibidos',count(*),'duplicados_ignorados_idempotencia',coalesce(sum(duplicados),0)) FROM public.crm_suscripcion_verificacion),
   'ultimos_eventos_outbox',coalesce((SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT * FROM public.outbox_eventos_crm ORDER BY created_at DESC,id DESC LIMIT 50) x),'[]'::jsonb),
   'ultimas_verificaciones_crm',coalesce((SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT * FROM public.crm_suscripcion_verificacion ORDER BY recibido_at DESC LIMIT 50) x),'[]'::jsonb));
 END IF;
 RETURN jsonb_build_object('error','Acción CRM no soportada.','status',422);
END $$;

REVOKE ALL ON FUNCTION public.encolar_cliente_crm(uuid,text),public.trigger_cliente_crm(),public.trigger_direccion_crm(),public.operar_crm(text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.operar_crm(text,jsonb) TO service_role;

-- Preferencias de cliente: el único canal habilitado es correo electrónico.
UPDATE public.preferencias_notificacion SET canal_sms=false,canal_push=false,telefono_sms=NULL
 WHERE canal_sms OR canal_push OR telefono_sms IS NOT NULL;
ALTER TABLE public.preferencias_notificacion ADD CONSTRAINT preferencias_solo_correo
 CHECK (canal_sms=false AND canal_push=false AND telefono_sms IS NULL);
