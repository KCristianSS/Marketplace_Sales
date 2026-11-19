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
