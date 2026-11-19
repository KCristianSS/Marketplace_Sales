-- Preferencias de cliente: el único canal habilitado es correo electrónico.
UPDATE public.preferencias_notificacion SET canal_sms=false,canal_push=false,telefono_sms=NULL
 WHERE canal_sms OR canal_push OR telefono_sms IS NOT NULL;
ALTER TABLE public.preferencias_notificacion ADD CONSTRAINT preferencias_solo_correo
 CHECK (canal_sms=false AND canal_push=false AND telefono_sms IS NULL);
