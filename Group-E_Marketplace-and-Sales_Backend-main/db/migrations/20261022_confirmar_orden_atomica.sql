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
        tracking_number, reserva_id, cuf_factura, numero_factura
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
        NULLIF(p_orden->>'numero_factura', '')::BIGINT
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