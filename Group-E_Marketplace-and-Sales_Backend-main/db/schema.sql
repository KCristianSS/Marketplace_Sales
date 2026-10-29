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
        CREATE TYPE estado_cotizacion_enum AS ENUM ('borrador', 'pendiente_aprobacion', 'aprobada', 'rechazada', 'convertida', 'vencida');
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
        direccion_entrega_id, subtotal, descuento, costo_envio, total, estado, tracking_number, reserva_id, cuf_factura, numero_factura)
    VALUES (v_orden_id, p_orden->>'codigo_orden', (p_orden->>'cliente_id')::UUID,
        NULLIF(p_orden->>'sucursal_id', '')::UUID, (p_orden->>'canal')::canal_venta_enum,
        (p_orden->>'tipo_despacho')::tipo_despacho_enum, NULLIF(p_orden->>'direccion_entrega_id', '')::UUID,
        (p_orden->>'subtotal')::NUMERIC, (p_orden->>'descuento')::NUMERIC,
        (p_orden->>'costo_envio')::NUMERIC, (p_orden->>'total')::NUMERIC,
        (p_orden->>'estado')::estado_orden_enum, p_orden->>'tracking_number', p_orden->>'reserva_id', p_orden->>'cuf_factura',
        NULLIF(p_orden->>'numero_factura', '')::BIGINT);

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
    estado estado_devolucion_enum DEFAULT 'solicitada',
    evidencia_urls JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolucion_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS cotizaciones_b2b (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    codigo_cotizacion VARCHAR(50) UNIQUE NOT NULL,
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id),
    gerente_id UUID,
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    descuento_porcentaje NUMERIC(5, 2) DEFAULT 0,
    total NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
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

-- ------------------------------------------------------------------------------
-- 6. ADMINISTRACIÓN, SEGURIDAD Y AUDITORÍA (RF-49, RF-50)
-- ------------------------------------------------------------------------------
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

