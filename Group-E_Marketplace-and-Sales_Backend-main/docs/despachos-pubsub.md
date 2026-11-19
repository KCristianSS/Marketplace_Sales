# Despachos automáticos por Pub/Sub · RIO-ENT-01/02

Al confirmar y guardar una compra a domicilio, MaxiConecta registra automáticamente una solicitud de despacho en la misma transacción PostgreSQL. Un worker del servicio de órdenes publica `despacho.solicitado`. La guía, el transportista y la ruta llegan después, mediante una respuesta del ERP de Entregas, que puede simularse con el proceso incluido en este repositorio.

## Activación

1. Aplicar `db/migrations/20261102_cotizacion_flete.sql` si todavía no está desplegada, y después `db/migrations/20261107025301_despachos_pubsub.sql`. Las instalaciones nuevas de `db/schema.sql` incluyen ambas definiciones. Antes de guardar un envío a domicilio, el backend comprueba que el RPC de despachos está disponible.
2. Configurar la clave de servicio de Supabase en órdenes. Las tablas y el RPC de despacho no están disponibles para `anon` ni `authenticated`: solo los usa el backend. No hay fallback a persistencia por pasos para compras a domicilio, porque publicaría una venta antes de guardar todos sus pagos y productos.
3. Configurar los tópicos completos y una suscripción propia para recibir respuestas:

```dotenv
PUBSUB_TOPIC_ENTREGAS=projects/PROYECTO/topics/TOPICO_SOLICITUDES
PUBSUB_TOPIC_RESPUESTAS_ENTREGAS=projects/PROYECTO/topics/TOPICO_RESPUESTAS
PUBSUB_SUBSCRIPTION_ENTREGAS=projects/PROYECTO/subscriptions/MAXICONECTA_RESPUESTAS_ENTREGAS
DESPACHOS_WORKER_ENABLED=true
PUBSUB_COTIZACIONES_SIMULACION_ENABLED=false
GOOGLE_APPLICATION_CREDENTIALS=/ruta/privada/service-account.json
```

Los tópicos pueden ser el tópico compartido que ya utiliza el proyecto. En ese caso deben existir **dos suscripciones independientes**: la del ERP simulado con filtro `attributes.destino = "entregas"`, y la de MaxiConecta con filtro `attributes.destino = "maxiconecta"`. No compartir una misma suscripción entre ambos procesos: competirían por los mensajes. El valor predeterminado del tópico es el existente de Grupo E; configurar el del equipo receptor cuando se acuerde con Entregas.

La cuenta de servicio necesita publicar en los tópicos de salida y consumir su suscripción. `docker-compose.yml` ya carga el `.env` y monta `backend/credentials` en el contenedor de órdenes. También puede utilizarse el emulador oficial de Pub/Sub configurando `PUBSUB_EMULATOR_HOST` en ambos procesos.

4. Reiniciar el servicio de órdenes. El publicador se inicia automáticamente con FastAPI y revisa la cola cada cinco segundos. El receptor se inicia cuando `PUBSUB_SUBSCRIPTION_ENTREGAS` tiene un valor. Sin suscripción de respuestas, se pueden enviar solicitudes, pero seguirán pendientes de confirmación externa.
5. Ejecutar el ERP simulado desde el directorio superior de backend:

```powershell
python -m backend.scripts.simular_entregas --subscription projects/PROYECTO/subscriptions/ERP_ENTREGAS_SOLICITUDES --state tmp/entregas-erp.sqlite3 --avanzar
```

El simulador consume la solicitud real y publica la respuesta real por Pub/Sub. SQLite conserva identificadores y respuestas ante reentregas o reinicios. `--avanzar` permite demostrar `programado → en_preparacion → en_transito → entregado`, avanzando un estado por consulta nueva. Sin esa opción, consultar devuelve el estado actual.

## Desencadenantes y pantallas

- **Confirmar una orden a domicilio:** el trigger crea un despacho y su mensaje pendiente. Una orden con retiro en sucursal no genera despacho.
- **Abrir el detalle de una compra o venta a domicilio:** el panel encola una consulta de estado por Pub/Sub.
- **Actualizar estado en ERP:** encola otra consulta explícita.
- **Leer la pantalla cada cinco segundos:** solo consulta la respuesta almacenada localmente; no genera tráfico repetido hacia el ERP.
- **Reintentar solicitud**, solo administración: recupera la solicitud existente conservando el identificador del evento. También puede recuperar una orden confirmada anterior a la migración que no tenga despacho ni guía asignada. No se envían automáticamente órdenes históricas para evitar duplicar despachos ya gestionados.
- **Cancelar una orden:** invalida mensajes de despacho todavía pendientes y encola `despacho.cancelacion.solicitada`. El simulador conserva la cancelación incluso si luego llega una solicitud antigua fuera de orden.

El panel está en **Administración → Historial de ventas → Ver detalle** y en el detalle de compras del cliente. Muestra guía, ruta, transportista, ubicación, fecha estimada y estado. Administración también dispone del historial completo paginado de mensajes, intentos, errores, respuestas y contenido JSON descrito en la sección de trazabilidad.

## Contrato de mensajes

Se mantiene el envelope Enterprise JSON del cliente Pub/Sub existente:

```json
{
  "specversion": "1.0",
  "event_id": "UUID_ESTABLE_DEL_EVENTO",
  "event_type": "despacho.solicitado",
  "source": "maxiconecta.marketplace.grupo-e",
  "destination": "entregas",
  "correlation_id": "UUID_DE_LA_SOLICITUD",
  "payload": {
    "version_contrato": 1,
    "solicitud_id": "UUID_DE_LA_SOLICITUD",
    "orden_id": "UUID_DE_LA_ORDEN",
    "codigo_orden": "CODIGO_DE_LA_ORDEN",
    "cliente_id": "UUID_DEL_CLIENTE",
    "sucursal_id": null,
    "entrega": {"direccion": "DIRECCION_DE_ENTREGA", "ciudad": "CIUDAD"},
    "items": [{"sku": "SKU", "nombre_producto": "Producto", "cantidad": 1}]
  }
}
```

La dirección y los productos salen de la orden persistida, no de un formulario de publicación manual. No se añaden nombres, teléfonos ni correos de perfiles al mensaje. El peso estimado que ya exista en la cotización puede viajar en `entrega`; no se inventan dimensiones, transportistas ni rutas.

| Solicitud de MaxiConecta | Respuesta del ERP |
|---|---|
| `despacho.solicitado` | `despacho.generado` o `despacho.rechazado` |
| `despacho.estado.consultado` | `despacho.estado.actualizado` |
| `despacho.cancelacion.solicitada` | `despacho.cancelado` |

Las respuestas usan `source: "erp.entregas"`, `destination: "maxiconecta"`, un `event_id` UUID único, y el mismo `correlation_id`. El payload requiere `solicitud_id`, `orden_id`, `request_event_id` (el evento de solicitud), `version` creciente y `estado`. Para estados logísticos confirmados requiere `guia`; puede incluir `transportista`, `ruta`, `ubicacion_actual`, `fecha_estimada` y `motivo`. Un rechazo requiere motivo.

Los mensajes publicados llevan el atributo Pub/Sub `destino` para enrutar por suscripción. La recepción utiliza Pull con credenciales IAM, sin exponer un endpoint HTTP de recepción público.

## API

Todos los endpoints exigen JWT. Clientes solo pueden acceder a su propia orden; administración puede gestionar las ventas. La autorización usa roles de `app_metadata` o claims firmados del servidor, nunca `user_metadata` editable.

| Método | Ruta | Comportamiento |
|---|---|---|
| GET | `/api/v1/ordenes/{id}/despacho` | Lee estado local e historial |
| POST | `/api/v1/ordenes/{id}/despacho/consultar` | Encola consulta externa; devuelve 202 |
| POST | `/api/v1/ordenes/{id}/despacho/reintentar` | Recupera/reintenta la solicitud, solo administración; devuelve 202 |

## Consistencia

- El trigger y la orden comparten transacción. Si falla la persistencia, no queda una solicitud publicable. No se llama al ERP antes del commit.
- `FOR UPDATE SKIP LOCKED` distribuye mensajes entre workers. Cada lote tiene un lease de dos minutos. Tras un reinicio, otro worker puede recuperar los vencidos.
- Los reintentos mantienen `event_id` y `solicitud_id`. El publicador espera confirmación real de Pub/Sub; el fallback local nunca se marca como publicado.
- Los errores quedan pendientes con retroceso exponencial de hasta cinco minutos. No se cancela una venta confirmada porque Pub/Sub esté desconectado.
- La inbox deduplica respuestas por `event_id`; correlación, versión y transiciones impiden aplicar respuestas a otra orden o retroceder un envío. Los estados terminales no se revierten por mensajes atrasados.
- La guía y el estado de despacho se guardan junto con la respuesta. Preparación, tránsito y entrega actualizan los estados comerciales correspondientes sin reactivar órdenes canceladas. Una cancelación logística externa no ejecuta reembolsos comerciales.
- Se confirma el mensaje recibido (ACK) después de guardar su respuesta. Si falla la BD, queda sin ACK para ser reentregado. Los mensajes con formato u origen inválidos se descartan con registro; es recomendable configurar la política de mensajes fallidos de la suscripción.

## Pruebas

Desde el directorio superior de backend, con PostgreSQL local de pruebas:

```powershell
$env:VALES_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres user=postgres'
python -m pytest backend/tests/test_despachos_pubsub.py -q
```

La suite reutiliza la infraestructura de bases efímeras de las pruebas de vales y rechaza servidores remotos. Crea y elimina una base temporal: no prueba sobre datos reales ni publica en el tópico compartido. Sin la variable, las pruebas SQL se omiten explícitamente.

Frontend: `npm run check:despachos` y `npm test -- src/components/orders/DispatchPanel.test.ts src/components/orders/OrderHistoryPanel.test.ts src/components/orders/ShippingTracePanel.test.ts`.

## Trazabilidad administrativa y cotizaciones de demostración

Aplicar también `db/migrations/20261109171752_trazabilidad_envios.sql`. Los mensajes y la cola de cotizaciones se conservan en Supabase; no dependen del reinicio del contenedor. La vista `envios_trazabilidad` combina los estados actuales de las colas, publicaciones, errores y respuestas recibidas. Solo el backend con `service_role` puede leer las tablas y la vista.

El historial completo, paginado y con filtros está en **Administración → Envíos y cobertura**, **Historial de ventas** y, filtrado por orden, en su detalle. Reemplaza la limitación de 20 eventos del resumen de despacho. Permite ver el contenido JSON y atributos del mensaje, fechas, identificadores de evento/correlación/Pub/Sub, errores, intentos y estados logísticos. Para mensajes anteriores a la migración solo se muestran los datos que ya estaban persistidos; no se reconstruyen respuestas inexistentes.

`GET /api/v1/ordenes/despachos/trazabilidad` exige JWT de administrador o gerente comercial. Admite `orden_id`, `tipo_evento`, `estado`, `estado_logistico`, `direccion` (`entrada`/`salida`), `simulacion`, `page` y `limit`. Los estados de publicación (`pendiente`, `procesando`, `publicado`, `error_publicacion`, `cancelado`) son independientes del estado logístico y de la recepción (`recibido`, `aplicado`, `ignorado`, `duplicado`). Los registros `estado_actual` representan la situación actual de la cola; los registros `mensaje` representan intentos o recepciones concretos.

El log `[PubSub] MENSAJE ENVIADO` se escribe solo después de recibir el `message_id` real del broker e incluye tipo de evento, correlación, tópico y JSON. Un fallback se registra como error y queda pendiente de reintento; nunca se anuncia como enviado.

Para la demostración, habilitar `PUBSUB_COTIZACIONES_SIMULACION_ENABLED=true` y reiniciar órdenes. Cada cotización válida encola `despacho.cotizacion.calculada` con `simulacion: true`, `cotizacion_id`, entradas del cálculo, fórmulas y resultado (tarifa base, peso, recargo express, bonificación, flete final y total). No se publica el JWT de cotización ni la dirección. La cola reintenta con identificador estable y backoff. Un fallo de demostración no modifica ni bloquea el cálculo comercial.

El simulador reconoce este evento y responde `despacho.cotizacion.recibida`, conservando el cálculo de Ventas. No crea guía ni despacho y no recalcula el precio. La respuesta solo puede recibirse si existe una suscripción configurada, igual que los demás mensajes de Entregas. Esta funcionalidad no constituye un contrato de cotización real con el ERP.

Pruebas de integración de la nueva cola y auditoría: `python -m pytest backend/tests/test_trazabilidad_envios.py -q`, con el mismo `VALES_TEST_DSN` local de la sección anterior.
