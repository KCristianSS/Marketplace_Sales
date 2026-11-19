-- KAN-194: habilita el estado emitida y los códigos correlativos COT-AAAA-NNNN.
ALTER TYPE estado_cotizacion_enum ADD VALUE IF NOT EXISTS 'emitida';

ALTER TABLE cotizaciones_b2b
    ADD COLUMN IF NOT EXISTS vigencia_dias INT NOT NULL DEFAULT 7;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'cotizaciones_b2b_vigencia_dias_check'
    ) THEN
        ALTER TABLE cotizaciones_b2b
            ADD CONSTRAINT cotizaciones_b2b_vigencia_dias_check
            CHECK (vigencia_dias IN (7, 15, 30));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS cotizaciones_b2b_secuencia (
    anio INT PRIMARY KEY,
    ultimo_numero INT NOT NULL CHECK (ultimo_numero > 0)
);
ALTER TABLE cotizaciones_b2b_secuencia ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON cotizaciones_b2b_secuencia FROM anon, authenticated;

CREATE OR REPLACE FUNCTION generar_codigo_cotizacion_b2b() RETURNS TEXT AS $$
DECLARE
    anio_actual INT := EXTRACT(YEAR FROM (CURRENT_TIMESTAMP - INTERVAL '4 hours'))::INT;
    siguiente_numero INT;
BEGIN
    INSERT INTO cotizaciones_b2b_secuencia (anio, ultimo_numero)
    VALUES (anio_actual, 1)
    ON CONFLICT (anio) DO UPDATE
        SET ultimo_numero = cotizaciones_b2b_secuencia.ultimo_numero + 1
    RETURNING ultimo_numero INTO siguiente_numero;

    RETURN 'COT-' || anio_actual::TEXT || '-' || LPAD(siguiente_numero::TEXT, 4, '0');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
REVOKE ALL ON FUNCTION generar_codigo_cotizacion_b2b() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION generar_codigo_cotizacion_b2b() TO service_role;
