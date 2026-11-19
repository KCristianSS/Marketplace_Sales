# Clientes hacia CRM por Pub/Sub · RIO-CRM-01

El servicio de Clientes usa `backend.shared.pubsub_client.GooglePubSubClient`, el mismo publicador que Despachos. El tópico predeterminado es `PUBSUB_TOPIC_ENTREGAS`; se puede configurar explícitamente `PUBSUB_TOPIC_CRM`.

## Flujo

1. Registrar un perfil, modificar sus datos comerciales o agregar/editar/eliminar una dirección crea un evento en `outbox_eventos_crm`, en la misma transacción PostgreSQL. Una escritura sin cambios de datos comerciales no genera otra sincronización de perfil.
2. El worker de Clientes reclama eventos cada cinco segundos con lease y bloqueo `SKIP LOCKED`. Publica con `destino=crm` y conserva el mismo `event_id` en cada reintento.
3. Solo un `message_id` real del broker deja el mensaje como `publicado`. Un fallback del publicador se registra como fallo y se reintenta con espera creciente (hasta cinco intentos). Los mensajes publicados esperan la respuesta del CRM.
4. Una respuesta válida `cliente.sincronizado` confirma el contacto. `cliente.rechazado` registra el motivo. La versión del perfil impide que una respuesta antigua reemplace el resultado de una actualización más reciente. Las respuestas duplicadas no vuelven a aplicar cambios.
5. Administración y Gerencia Comercial pueden consultar clientes, mensajes y respuestas desde **Sincronización CRM (Pub/Sub)**. **Sincronizar** encola una nueva versión con datos de la base de datos; no acepta nombres, contactos ni correos inventados desde el navegador. Los clientes históricos se sincronizan mediante esta acción; la migración no publica automáticamente toda la base histórica.

## Solicitud

Mismo envelope de Despachos, con un evento específico para CRM:

```json
{
  "specversion": "1.0",
  "event_id": "UUID_ESTABLE",
  "event_type": "cliente.creado",
  "source": "maxiconecta.marketplace.grupo-e",
  "destination": "crm",
  "correlation_id": "UUID_CLIENTE",
  "payload": {
    "version_contrato": 1,
    "version": 1,
    "cliente_id": "UUID_CLIENTE",
    "nombre_completo": "Nombre registrado",
    "email": "correo registrado",
    "telefono": null,
    "nit_ci": null,
    "razon_social": null,
    "tipo_cliente": "retail",
    "crm_contact_id": null,
    "fecha_registro": "FECHA_ISO",
    "direcciones": []
  }
}
```

Los eventos son `cliente.creado` y `cliente.actualizado`. Cada actualización contiene el snapshot completo del perfil y sus direcciones, incluyendo los identificadores, referencias, ciudad, zona y coordenadas que estén registradas. El CRM debe aplicar un **upsert por cliente_id** y conservar la versión más alta por cliente: Pub/Sub puede reentregar o cambiar el orden de eventos. Debe deduplicar por `event_id`.

Los atributos incluyen `destino=crm`, `tipo_evento`, `cliente_id`, `version_contrato=1` y la correlación. El CRM necesita su propia suscripción al tópico con filtro `attributes.destino = "crm"`. La aceptación del contrato y el consumidor corresponden al sistema CRM externo.

## Respuesta esperada

```json
{
  "event_id": "UUID_RESPUESTA",
  "event_type": "cliente.sincronizado",
  "source": "erp.crm",
  "destination": "maxiconecta",
  "correlation_id": "UUID_CLIENTE",
  "payload": {
    "request_event_id": "UUID_ESTABLE_DE_LA_SOLICITUD",
    "cliente_id": "UUID_CLIENTE",
    "crm_contact_id": "IDENTIFICADOR_REAL_DEL_CRM"
  }
}
```

Un rechazo utiliza `event_type=cliente.rechazado` e incluye `motivo` en lugar de un contacto confirmado. Las respuestas deben tener los atributos Pub/Sub `destino=maxiconecta` y `tipo_evento` con el tipo de respuesta. No se generan respuestas ficticias ni contactos de demostración.

## Configuración

```dotenv
# Por defecto hereda el tópico de despachos.
# PUBSUB_TOPIC_CRM=projects/PROYECTO/topics/TOPICO_COMPARTIDO
CRM_WORKER_ENABLED=true
PUBSUB_SUBSCRIPTION_CRM=projects/PROYECTO/subscriptions/maxiconecta-crm-respuestas
```

`docker-compose.yml` monta en Clientes las mismas credenciales de servicio que usa Órdenes para Pub/Sub. Requieren permiso de publicación en el tópico y consumo de la suscripción propia. La tabla, funciones y cola se crean con `db/migrations/20261110225022_crm_pubsub_persistente.sql`; las tablas usan RLS y las funciones están restringidas a `service_role`.

La suscripción de respuestas de CRM debe ser independiente de la suscripción de Entregas. Un administrador de Google Cloud puede crearla con este filtro:

```text
attributes.destino = "maxiconecta" AND (attributes.tipo_evento = "cliente.sincronizado" OR attributes.tipo_evento = "cliente.rechazado")
```

Después debe proporcionar el nombre completo en `PUBSUB_SUBSCRIPTION_CRM` y recrear `ms-clientes`. Si no se configura, se publica y conserva la trazabilidad pero no se marca una confirmación externa. La interfaz informa esa condición.

En el entorno revisado, la cuenta de servicio puede acceder al tópico compartido, pero Google Cloud rechazó la creación de la suscripción por falta de `pubsub.subscriptions.create`. No se modificaron permisos IAM.

RIO-CRM-02 (compras) y RIO-CRM-03 (fidelidad) conservan sus adaptadores propios. Este cambio corresponde a la sincronización de perfiles y direcciones.
