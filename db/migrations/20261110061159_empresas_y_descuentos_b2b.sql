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
