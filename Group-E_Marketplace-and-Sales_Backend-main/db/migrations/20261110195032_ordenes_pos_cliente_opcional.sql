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
