-- Una simulación no es un reembolso completado y no afecta el saldo real.
ALTER TABLE public.reembolsos DROP CONSTRAINT IF EXISTS chk_reembolsos_estado;
ALTER TABLE public.reembolsos ADD CONSTRAINT chk_reembolsos_estado
    CHECK (estado IN ('solicitado', 'procesando', 'completado', 'fallido', 'simulado'));
