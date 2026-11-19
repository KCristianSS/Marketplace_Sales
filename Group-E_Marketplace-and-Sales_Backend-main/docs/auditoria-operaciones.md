# Auditoría de operaciones críticas

El administrador abre **Administración → Auditoría** (`/admin?tab=auditoria`).
La API de consulta es `GET /api/v1/admin/auditoria`: JWT obligatorio y rol
`administrador` en `app_metadata` o en el claim de rol del sistema. Un rol enviado
en `user_metadata` no otorga acceso. No hay endpoints para editar o borrar logs.

## Datos y filtros

Cada evento conserva usuario/actor, rol, acción, entidad e identificador, fecha
UTC, IP, método/ruta, navegador, ID de solicitud y snapshots antes/después.
Contraseñas, PIN, tokens y secretos de vales se ocultan tanto al registrar como al
consultar registros históricos. En creaciones el valor anterior es nulo; en
eliminaciones el posterior es nulo. Los snapshots tienen límites de profundidad
y tamaño; no se registran cuerpos HTTP, cabeceras Authorization ni archivos.

Filtros: `accion`, `entidad`, `actor` (UUID), `rol`, `solicitud` (UUID), `desde`,
`hasta`, `page`, `limit` (máximo 100). La respuesta incluye total y páginas, orden
estable por fecha/ID, `Cache-Control: no-store` y cantidad de eventos pendientes.
Las horas de la pantalla se presentan en la zona del navegador.

## Cobertura explícita

- Productos; categorías; listas y asignación/eliminación de tarifas; combos y cupones.
- Órdenes: creación, transición y cancelación; solicitudes y resolución de devoluciones.
- Ventas POS, anulaciones, entrega en sucursal y reimpresión de tickets.
- Apertura/cierre y arqueo de caja; movimientos de efectivo; descuentos autorizados.
- Registro/validación de pagos y reembolsos, con los eventos ya usados por esos servicios.
- Alta, cambios de rol/datos y desactivación de usuarios internos.
- Emisión de factura y cotización B2B; reglas de envío; movimientos y gestión de vales.

Los endpoints administrativos adicionales declaran `@audit_operation(...)` de
forma explícita. Sus lecturas de snapshots son auxiliares: un fallo no cambia el
resultado de la operación y se señala que el valor anterior no está disponible.
No se instalan hooks globales sobre el cliente Supabase ni triggers comerciales.

## Origen e integridad del contexto

El Gateway obtiene la IP de la conexión y firma el contexto con HMAC usando el
secreto interno JWT. Los microservicios verifican firma y vigencia antes de usar
la IP/ID de solicitud recibidos. El actor y rol se obtienen del JWT verificado,
nunca de cabeceras de actor o de metadatos editables. Un acceso directo al
microservicio usa su conexión local. ContextVar aísla solicitudes concurrentes.

## Persistencia y reintentos

`registrar_audit` y `registrar_auditoria` comparten el formato. Primero guardan el
evento redactado en SQLite con un UUID estable; luego intentan insertarlo en
`audit_logs`. Si Supabase falla, queda pendiente. Un worker cada 10 segundos lo
reintenta con espera creciente (hasta 300 segundos), leases y deduplicación por
ID. Se escribe `AUDIT_GUARDADO` únicamente al confirmar el INSERT o reconocer el
mismo ID ya insertado. Una caída del servicio conserva la cola en el volumen
Docker `audit-data`, compartido por los microservicios locales.

`AUDIT_SPOOL_PATH` configura la ruta (`/var/lib/maxiconecta/audit/events.sqlite3`
en Compose). Debe mantenerse en almacenamiento persistente también en otros
despliegues. La cola contiene datos de auditoría y no debe servirse públicamente.
Si además falla la escritura local, se emite `AUDIT_EMERGENCIA` en el log de la
aplicación. En pruebas aisladas se permite memoria, sin usar la BD corporativa.

La escritura comercial y la de auditoría son transacciones independientes. No
hay garantía atómica ante la terminación del proceso justo entre ambas. La
alternativa con triggers transaccionales quedó fuera de esta implementación
porque la revisión automática exigió autorización explícita para su impacto en
las tablas compartidas. Los registros históricos no adquieren retroactivamente
metadatos que no se capturaron en su momento.

## Instalación y comprobación

Aplicar `db/migrations/20261110040056_auditoria_estructurada.sql` antes de actualizar
los servicios. La migración solo añade columnas e índices a `audit_logs`; no
cambia transacciones, tablas comerciales ni permisos existentes. La tabla ya
usa RLS; la consulta pasa por la API administrativa y la clave de servicio.

`tests/test_auditoria_completa.py` verifica acceso, filtros, privacidad, origen
firmado, aislamiento concurrente, reintentos, deduplicación y persistencia en un
PostgreSQL local efímero con `VALES_TEST_DSN`. El componente Vue tiene pruebas de
filtros, paginación, estados de error y comparación de cambios.
