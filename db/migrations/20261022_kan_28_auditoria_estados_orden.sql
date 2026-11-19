-- KAN-28 / RF-28: auditar quién realizó cada transición de estado de la orden.
ALTER TABLE ordenes ADD COLUMN IF NOT EXISTS estado_actualizado_por UUID;
ALTER TABLE orden_estados_historial ADD COLUMN IF NOT EXISTS cambiado_por UUID;

CREATE OR REPLACE FUNCTION registrar_historial_estado_orden() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.estado IS DISTINCT FROM OLD.estado THEN
        INSERT INTO orden_estados_historial (orden_id, estado_anterior, estado_nuevo, cambiado_por)
        VALUES (NEW.id, CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.estado END, NEW.estado, NEW.estado_actualizado_por);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
