-- ==============================================================================
-- MAXICONECTA - MARKETPLACE Y VENTAS (GRUPO E)
-- DDL DE BASE DE DATOS PARA SUPABASE (POSTGRESQL 15+)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
    latitud NUMERIC(10, 7),
    longitud NUMERIC(10, 7),
    es_predeterminada BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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
    calificacion INT NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    comentario TEXT,
    aprobada BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deseos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id UUID NOT NULL REFERENCES perfiles_clientes(id) ON DELETE CASCADE,
    variante_id UUID NOT NULL REFERENCES variantes(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_deseo_cliente_variante UNIQUE(cliente_id, variante_id)
);

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

CREATE TABLE IF NOT EXISTS pagos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID REFERENCES ordenes(id) ON DELETE CASCADE,
    transaccion_id VARCHAR(100) UNIQUE,
    token_pago VARCHAR(150),
    metodo metodo_pago_enum NOT NULL,
    monto NUMERIC(12, 2) NOT NULL CHECK (monto > 0),
    moneda VARCHAR(10) DEFAULT 'BOB',
    estado estado_pago_enum DEFAULT 'pendiente',
    raw_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pagos_token ON pagos(token_pago);
CREATE INDEX IF NOT EXISTS idx_pagos_transaccion ON pagos(transaccion_id);

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

CREATE OR REPLACE FUNCTION confirmar_orden_atomica(p_orden JSONB, p_items JSONB, p_pagos JSONB)
RETURNS JSONB AS $$
DECLARE
    v_orden_id UUID := (p_orden->>'id')::UUID;
    v_pago JSONB;
    v_tx TEXT;
    v_existing_order UUID;
    v_result JSONB;
BEGIN
    -- Serializar reintentos del mismo cobro y devolver la orden original si ya se procesó.
    v_tx := COALESCE(p_pagos->0->>'transaccion_id', 'orden:' || v_orden_id::TEXT);
    PERFORM pg_advisory_xact_lock(hashtextextended(v_tx, 0));
    SELECT orden_id INTO v_existing_order
    FROM pagos
    WHERE transaccion_id = v_tx AND orden_id IS NOT NULL
    LIMIT 1;
    IF v_existing_order IS NOT NULL THEN
        SELECT jsonb_build_object('id', id, 'codigo_orden', codigo_orden, 'existente', TRUE)
        INTO v_result FROM ordenes WHERE id = v_existing_order;
        RETURN v_result;
    END IF;

    INSERT INTO ordenes (id, codigo_orden, cliente_id, sucursal_id, canal, tipo_despacho,
        direccion_entrega_id, subtotal, descuento, costo_envio, total, estado, tracking_number, reserva_id, cuf_factura, numero_factura, entrega)
    VALUES (v_orden_id, p_orden->>'codigo_orden', (p_orden->>'cliente_id')::UUID,
        NULLIF(p_orden->>'sucursal_id', '')::UUID, (p_orden->>'canal')::canal_venta_enum,
        (p_orden->>'tipo_despacho')::tipo_despacho_enum,
        NULLIF(p_orden->>'direccion_entrega_id', '')::UUID,
        (p_orden->>'subtotal')::NUMERIC, (p_orden->>'descuento')::NUMERIC,
        (p_orden->>'costo_envio')::NUMERIC, (p_orden->>'total')::NUMERIC,
        (p_orden->>'estado')::estado_orden_enum, p_orden->>'tracking_number', p_orden->>'reserva_id', p_orden->>'cuf_factura',
        NULLIF(p_orden->>'numero_factura', '')::BIGINT, p_orden->'entrega');

    INSERT INTO orden_items (orden_id, variante_id, sku, nombre_producto, cantidad, precio_unitario, total_linea)
    SELECT v_orden_id, (item.value->>'variante_id')::UUID, item.value->>'sku', item.value->>'nombre_producto',
        (item.value->>'cantidad')::INT, (item.value->>'precio_unitario')::NUMERIC,
        (item.value->>'total_linea')::NUMERIC
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


CREATE INDEX IF NOT EXISTS idx_pagos_token ON pagos(token_pago);
CREATE INDEX IF NOT EXISTS idx_pagos_transaccion ON pagos(transaccion_id);

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

CREATE OR REPLACE FUNCTION confirmar_orden_atomica(p_orden JSONB, p_items JSONB, p_pagos JSONB)
RETURNS JSONB AS $$
DECLARE
    v_orden_id UUID := (p_orden->>'id')::UUID;
    v_pago JSONB;
    v_tx TEXT;
    v_existing_order UUID;
    v_result JSONB;
BEGIN
    -- Serializar reintentos del mismo cobro y devolver la orden original si ya se procesó.
    v_tx := COALESCE(p_pagos->0->>'transaccion_id', 'orden:' || v_orden_id::TEXT);
    PERFORM pg_advisory_xact_lock(hashtextextended(v_tx, 0));
    SELECT orden_id INTO v_existing_order
    FROM pagos
    WHERE transaccion_id = v_tx AND orden_id IS NOT NULL
    LIMIT 1;
    IF v_existing_order IS NOT NULL THEN
        SELECT jsonb_build_object('id', id, 'codigo_orden', codigo_orden, 'existente', TRUE)
        INTO v_result FROM ordenes WHERE id = v_existing_order;
        RETURN v_result;
    END IF;

    INSERT INTO ordenes (id, codigo_orden, cliente_id, sucursal_id, canal, tipo_despacho,
        direccion_entrega_id, subtotal, descuento, costo_envio, total, estado, tracking_number, reserva_id, cuf_factura, numero_factura, entrega)
    VALUES (v_orden_id, p_orden->>'codigo_orden', (p_orden->>'cliente_id')::UUID,
        NULLIF(p_orden->>'sucursal_id', '')::UUID, (p_orden->>'canal')::canal_venta_enum,
        (p_orden->>'tipo_despacho')::tipo_despacho_enum,
        NULLIF(p_orden->>'direccion_entrega_id', '')::UUID,
        (p_orden->>'subtotal')::NUMERIC, (p_orden->>'descuento')::NUMERIC,
        (p_orden->>'costo_envio')::NUMERIC, (p_orden->>'total')::NUMERIC,
        (p_orden->>'estado')::estado_orden_enum, p_orden->>'tracking_number', p_orden->>'reserva_id', p_orden->>'cuf_factura',
        NULLIF(p_orden->>'numero_factura', '')::BIGINT);

    INSERT INTO orden_items (orden_id, variante_id, sku, nombre_producto, cantidad, precio_unitario, total_linea)
    SELECT v_orden_id, (item.value->>'variante_id')::UUID, item.value->>'sku', item.value->>'nombre_producto',
        (item.value->>'cantidad')::INT, (item.value->>'precio_unitario')::NUMERIC,
        (item.value->>'total_linea')::NUMERIC
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


-- Facturación Electrónica en Línea (RF-10, RF-45, KAN-346, KAN-367)
CREATE TABLE IF NOT EXISTS facturas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orden_id UUID REFERENCES ordenes(id) ON DELETE CASCADE,
    numero_factura BIGINT NOT NULL,
    cuf VARCHAR(100) NOT NULL UNIQUE,
    cufd VARCHAR(100),
    nit_emisor VARCHAR(50) NOT NULL DEFAULT '1028374029',
    nit_ci_cliente VARCHAR(50) NOT NULL,
    razon_social_cliente VARCHAR(200) NOT NULL,
    email_cliente VARCHAR(150),
    monto_total NUMERIC(12, 2) NOT NULL CHECK (monto_total >= 0),
    monto_iva NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (monto_iva >= 0),
    modalidad VARCHAR(50) DEFAULT 'electronica_en_linea',
    estado VARCHAR(50) DEFAULT 'emitida',
    codigo_qr TEXT,
    items JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_facturas_cuf ON facturas(cuf);
CREATE INDEX IF NOT EXISTS idx_facturas_orden ON facturas(orden_id);
CREATE INDEX IF NOT EXISTS idx_facturas_cliente ON facturas(nit_ci_cliente);

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
CREATE INDEX IF NOT EXISTS idx_variantes_producto ON variantes(producto_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_cliente ON ordenes(cliente_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_estado ON ordenes(estado);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

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
-- HISTORIA KAN-14 / KAN-40: SINCRONIZACIÓN DE CLIENTES CON CRM VÍA PUB/SUB (RF-14)
-- SUBTAREAS: KAN-169, KAN-171, KAN-173
-- TÓPICO: projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e
-- ==============================================================================

-- 1. Campos de sincronización en perfiles_clientes
ALTER TABLE perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_estado VARCHAR(20) DEFAULT 'pendiente';
ALTER TABLE perfiles_clientes ADD COLUMN IF NOT EXISTS crm_sync_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE perfiles_clientes ADD COLUMN IF NOT EXISTS crm_contact_id VARCHAR(100);

-- 2. Bandeja de salida transaccional (Transactional Outbox)
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
