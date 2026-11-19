-- KAN-232: persiste las líneas y el comentario de resolución de cada solicitud.
ALTER TABLE devoluciones
    ADD COLUMN IF NOT EXISTS items JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE devoluciones
    ADD COLUMN IF NOT EXISTS comentario_resolucion TEXT;
