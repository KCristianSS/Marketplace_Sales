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
