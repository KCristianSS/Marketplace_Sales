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
