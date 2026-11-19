-- Estructura de KAN-341 y cierre del turno junto con su reporte en una transacción.
ALTER TABLE public.caja_turnos ADD COLUMN IF NOT EXISTS con_diferencia BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS public.arqueo_caja (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_reporte VARCHAR(40) NOT NULL UNIQUE,
    caja_turno_id UUID NOT NULL UNIQUE REFERENCES public.caja_turnos(id),
    cajero_id UUID NOT NULL, sucursal_id UUID NOT NULL,
    fondo_inicial NUMERIC(12,2) NOT NULL, ventas_efectivo NUMERIC(12,2) NOT NULL DEFAULT 0,
    entradas_extraordinarias NUMERIC(12,2) NOT NULL DEFAULT 0, retiros_boveda NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_esperado NUMERIC(12,2) NOT NULL, total_declarado NUMERIC(12,2) NOT NULL CHECK (total_declarado >= 0),
    diferencia NUMERIC(12,2) NOT NULL,
    estado_cuadre VARCHAR(10) NOT NULL CHECK (estado_cuadre IN ('cuadrado', 'sobrante', 'faltante')),
    con_diferencia BOOLEAN NOT NULL DEFAULT FALSE, observaciones TEXT,
    total_tarjeta NUMERIC(12,2) NOT NULL DEFAULT 0, total_qr NUMERIC(12,2) NOT NULL DEFAULT 0,
    notificacion_contabilidad JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.arqueo_detalle (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arqueo_id UUID NOT NULL REFERENCES public.arqueo_caja(id),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('billete', 'moneda')),
    denominacion NUMERIC(6,2) NOT NULL CHECK (denominacion IN (200,100,50,20,10,5,2,1,0.50,0.20,0.10)),
    cantidad INT NOT NULL CHECK (cantidad >= 0), subtotal NUMERIC(12,2) NOT NULL CHECK (subtotal >= 0),
    UNIQUE (arqueo_id, denominacion)
);
CREATE INDEX IF NOT EXISTS idx_arqueo_caja_sucursal_fecha ON public.arqueo_caja(sucursal_id, created_at DESC);
ALTER TABLE public.arqueo_caja ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.arqueo_detalle ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.arqueo_caja, public.arqueo_detalle FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.arqueo_caja, public.arqueo_detalle TO service_role;

CREATE OR REPLACE FUNCTION public.proteger_arqueo_congelado() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'El arqueo es inmutable'; END IF;
    IF TG_TABLE_NAME = 'arqueo_caja' AND
       (to_jsonb(NEW) - 'notificacion_contabilidad') IS NOT DISTINCT FROM (to_jsonb(OLD) - 'notificacion_contabilidad') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'El arqueo es inmutable';
END;
$$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='public.arqueo_caja'::regclass AND tgname='trg_arqueo_caja_inmutable' AND NOT tgisinternal) THEN
        CREATE TRIGGER trg_arqueo_caja_inmutable BEFORE UPDATE OR DELETE ON public.arqueo_caja FOR EACH ROW EXECUTE FUNCTION public.proteger_arqueo_congelado();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='public.arqueo_detalle'::regclass AND tgname='trg_arqueo_detalle_inmutable' AND NOT tgisinternal) THEN
        CREATE TRIGGER trg_arqueo_detalle_inmutable BEFORE UPDATE OR DELETE ON public.arqueo_detalle FOR EACH ROW EXECUTE FUNCTION public.proteger_arqueo_congelado();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.confirmar_arqueo_ciego(p_arqueo JSONB, p_detalle JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_id UUID := (p_arqueo->>'id')::UUID;
BEGIN
    UPDATE public.caja_turnos SET estado='cerrada', monto_cierre_real=(p_arqueo->>'total_declarado')::numeric,
        diferencia=(p_arqueo->>'diferencia')::numeric, con_diferencia=(p_arqueo->>'con_diferencia')::boolean,
        observaciones=p_arqueo->>'observaciones', closed_at=(p_arqueo->>'created_at')::timestamptz
    WHERE id=(p_arqueo->>'caja_turno_id')::uuid AND estado='abierta';
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO public.arqueo_caja SELECT * FROM jsonb_populate_record(NULL::public.arqueo_caja, p_arqueo);
    INSERT INTO public.arqueo_detalle (arqueo_id,tipo,denominacion,cantidad,subtotal)
    SELECT v_id, d.tipo, d.denominacion, d.cantidad, d.subtotal
    FROM jsonb_to_recordset(p_detalle) AS d(tipo text, denominacion numeric, cantidad integer, subtotal numeric);
    RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION public.confirmar_arqueo_ciego(JSONB,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.confirmar_arqueo_ciego(JSONB,JSONB) TO service_role;
