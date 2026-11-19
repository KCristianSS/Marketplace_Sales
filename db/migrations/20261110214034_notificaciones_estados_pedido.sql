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
