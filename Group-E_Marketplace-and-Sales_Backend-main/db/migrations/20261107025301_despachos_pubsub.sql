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
