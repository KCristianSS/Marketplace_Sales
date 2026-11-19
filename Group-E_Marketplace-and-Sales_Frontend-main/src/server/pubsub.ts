import { PubSub } from '@google-cloud/pubsub';
import path from 'node:path';
import fs from 'node:fs';

export const GCP_PROJECT_ID = process.env.GCP_PROJECT_ID || 'project-a96e5fe1-5ba6-4698-a85';
export const PUBSUB_TOPIC_INVENTARIOS =
  process.env.PUBSUB_TOPIC_INVENTARIOS ||
  'projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e';

export function resolveCredentialsPath(): string | null {
  const candidates = [
    process.env.GOOGLE_APPLICATION_CREDENTIALS,
    path.resolve(process.cwd(), 'service-account.json'),
    path.resolve(process.cwd(), 'service_account.json'),
    path.resolve(process.cwd(), 'credentials/service-account.json'),
    path.resolve(process.cwd(), 'credentials/gcp-pubsub-service-account.json'),
    path.resolve(process.cwd(), 'Group-E_Marketplace-and-Sales_Backend-main/service-account.json'),
    path.resolve(process.cwd(), 'Group-E_Marketplace-and-Sales_Backend-main/credentials/service-account.json'),
    path.resolve(process.cwd(), 'backend_reference/service-account.json'),
    path.resolve(process.cwd(), 'backend_reference/credentials/service-account.json')
  ];

  for (const c of candidates) {
    if (c && fs.existsSync(c)) return path.resolve(c);
  }
  return null;
}

export interface PubSubEventLog {
  event_id: string;
  event_type: string;
  message_id: string;
  topic: string;
  status: 'PUBLICADO' | 'FALLBACK_OFFLINE';
  timestamp: string;
  payload: any;
  attributes: Record<string, string>;
  error?: string;
  origen_sistema?: string;
}

export const pubSubEventLogs: PubSubEventLog[] = [];

export function getPubSubStatus() {
  const credPath = resolveCredentialsPath();
  return {
    projectId: GCP_PROJECT_ID,
    topic: PUBSUB_TOPIC_INVENTARIOS,
    hasCredentialsFile: Boolean(credPath),
    credentialsPath: credPath,
    mode: credPath ? 'ONLINE (Google Cloud)' : 'FALLBACK SIMULADO (Offline)',
    totalEventsLogged: pubSubEventLogs.length,
    ultimosEventos: pubSubEventLogs.slice(0, 10)
  };
}

export async function publishToPubSub(
  eventType: string,
  payload: any,
  customAttributes: Record<string, string> = {},
  correlationId?: string
): Promise<PubSubEventLog> {
  const eventId = `evt-${Math.random().toString(36).substring(2, 10)}`;
  const corrId = correlationId || payload?.orden_id || `corr-${Date.now()}`;
  const nowIso = new Date().toISOString();

  const envelope = {
    specversion: '1.0',
    event_id: eventId,
    event_type: eventType,
    source: 'maxiconecta.marketplace.grupo-e',
    timestamp: nowIso,
    correlation_id: corrId,
    equipo: 'Grupo E — Marketplace y Ventas',
    materia: 'UCB SIS-323',
    payload
  };

  const attributes: Record<string, string> = {
    grupo: 'Grupo-E',
    modulo: 'Marketplace-and-Sales',
    tipo_evento: eventType,
    correlation_id: String(corrId),
    timestamp: nowIso,
    ...customAttributes
  };

  // Imprimir en la terminal el envío del mensaje desde el sistema
  console.log(`\n======================================================================`);
  console.log(`\x1b[96m\x1b[1m[Google Pub/Sub] >>> ENVIANDO MENSAJE DE SINCRONIZACIÓN DESDE EL SISTEMA\x1b[0m`);
  console.log(`  • Tópico:       \x1b[1m${PUBSUB_TOPIC_INVENTARIOS}\x1b[0m`);
  console.log(`  • Tipo Evento:  \x1b[94m${eventType}\x1b[0m`);
  console.log(`  • Event ID:     ${eventId}`);
  console.log(`  • Correlación:  ${corrId}`);
  console.log(`  • Timestamp:    ${nowIso}`);
  console.log(`  • Carga Útil (CloudEvents 1.0):\n`, JSON.stringify(envelope, null, 2));

  try {
    const keyFilename = resolveCredentialsPath();
    if (!keyFilename) {
      throw new Error('Archivo de credenciales service-account.json no encontrado.');
    }

    const pubsub = new PubSub({
      projectId: GCP_PROJECT_ID,
      keyFilename
    });

    const topic = pubsub.topic(PUBSUB_TOPIC_INVENTARIOS);
    const dataBuffer = Buffer.from(JSON.stringify(envelope));

    const messageId = await topic.publishMessage({
      data: dataBuffer,
      attributes
    });

    // Imprimir en la terminal la confirmación de llegada
    console.log(`----------------------------------------------------------------------`);
    console.log(`\x1b[92m\x1b[1m[Google Pub/Sub] <<< CONFIRMACIÓN DE RECEPCIÓN (GOOGLE CLOUD PUB/SUB)\x1b[0m`);
    console.log(`  • Estado:       \x1b[92m\x1b[1mPUBLICADO CON ÉXITO EN GOOGLE CLOUD\x1b[0m`);
    console.log(`  • Message ID:   \x1b[92m\x1b[1m${messageId}\x1b[0m`);
    console.log(`  • Tópico:       ${PUBSUB_TOPIC_INVENTARIOS}`);
    console.log(`======================================================================\n`);

    const record: PubSubEventLog = {
      event_id: eventId,
      event_type: eventType,
      message_id: messageId,
      topic: PUBSUB_TOPIC_INVENTARIOS,
      status: 'PUBLICADO',
      timestamp: nowIso,
      payload,
      attributes,
      origen_sistema: customAttributes.origen || 'sistema_maxiconecta'
    };

    pubSubEventLogs.unshift(record);
    if (pubSubEventLogs.length > 50) pubSubEventLogs.pop();
    return record;
  } catch (err: any) {
    const fallbackId = `sim-${Math.random().toString(36).substring(2, 10)}`;
    console.log(`----------------------------------------------------------------------`);
    console.log(`\x1b[93m\x1b[1m[Google Pub/Sub] <<< CONFIRMACIÓN DE RECEPCIÓN (MODO SIMULADO OFFLINE)\x1b[0m`);
    console.log(`  • Estado:       \x1b[93mFALLBACK_OFFLINE\x1b[0m`);
    console.log(`  • Message ID:   ${fallbackId}`);
    console.log(`  • Motivo:       ${err?.message || err}`);
    console.log(`======================================================================\n`);

    const fallbackRecord: PubSubEventLog = {
      event_id: eventId,
      event_type: eventType,
      message_id: fallbackId,
      topic: PUBSUB_TOPIC_INVENTARIOS,
      status: 'FALLBACK_OFFLINE',
      timestamp: nowIso,
      payload,
      attributes,
      error: err?.message || String(err),
      origen_sistema: customAttributes.origen || 'sistema_maxiconecta'
    };
    pubSubEventLogs.unshift(fallbackRecord);
    if (pubSubEventLogs.length > 50) pubSubEventLogs.pop();
    return fallbackRecord;
  }
}

export async function publishStockDescuento(
  ordenId: string,
  items: Array<{ sku: string; cantidad: number; nombre?: string }>,
  origen: string = 'marketplace',
  sucursalId: string = 'SUC-LP-CENTRAL',
  reservaId?: string
): Promise<PubSubEventLog> {
  const payload = {
    tipo_movimiento: 'DESCUENTO_DEFINITIVO',
    orden_id: ordenId,
    origen,
    sucursal_id: sucursalId,
    reserva_id: reservaId || null,
    items: items.map(it => ({
      sku: it.sku,
      cantidad: Number(it.cantidad) || 1,
      nombre: it.nombre || ''
    }))
  };

  return publishToPubSub('stock.descuento', payload, { canal: origen, origen }, ordenId);
}

export async function publishStockReintegro(
  ordenId: string,
  items: Array<{ sku: string; cantidad: number; nombre?: string }>,
  motivo: string = 'cancelacion_orden',
  origen: string = 'marketplace',
  sucursalId: string = 'SUC-LP-CENTRAL'
): Promise<PubSubEventLog> {
  const payload = {
    tipo_movimiento: 'REINTEGRO_DEVOLUCION',
    orden_id: ordenId,
    motivo,
    origen,
    sucursal_id: sucursalId,
    items: items.map(it => ({
      sku: it.sku,
      cantidad: Number(it.cantidad) || 1,
      nombre: it.nombre || ''
    }))
  };

  return publishToPubSub('stock.reintegro', payload, { motivo, origen }, ordenId);
}

export async function publishPruebaDocente(
  responsable: string = 'Kevin Sancalli',
  detalle: string = 'Prueba de sincronizacion con Inventario para cátedra UCB SIS-323'
): Promise<PubSubEventLog> {
  const payload = {
    evento: 'PRUEBA_PUBLICACION_DOCENTE',
    equipo: 'Grupo E — Marketplace y Ventas',
    responsable,
    materia: 'UCB SIS-323',
    descripcion: detalle,
    fecha_hora_utc: new Date().toISOString(),
    fecha_hora_bolivia: new Date().toLocaleString('es-BO', { timeZone: 'America/La_Paz' })
  };

  return publishToPubSub('prueba_docente', payload, { canal_prueba: 'docente_sis323', origen: 'interfaz_web_maxiconecta' });
}

// ==============================================================================
// HISTORIA KAN-14 / KAN-40: SINCRONIZACIÓN ASÍNCRONA CON CRM VÍA PUB/SUB (RF-14)
// TÓPICO: projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e
// ==============================================================================

export interface CrmOutboxItem {
  id: string;
  event_id: string;
  cliente_id: string;
  event_type: 'cliente.creado' | 'cliente.actualizado' | 'cliente.compra_registrada';
  topic: string;
  payload: any;
  attributes: Record<string, string>;
  estado: 'pendiente' | 'sincronizado' | 'error' | 'reintentando';
  intentos: number;
  max_intentos: number;
  ultimo_error?: string | null;
  message_id?: string | null;
  created_at: string;
  sent_at?: string | null;
  updated_at: string;
}

export interface CrmVerificacionItem {
  id: string;
  event_id: string;
  event_type: string;
  cliente_id: string;
  payload: any;
  ignorado_duplicado: boolean;
  crm_status: 'PROCESADO_OK' | 'DUPLICADO_IGNORADO';
  recibido_at: string;
}

export const crmOutboxLogs: CrmOutboxItem[] = [];
export const crmVerificacionLogs: CrmVerificacionItem[] = [];

/**
 * Encola un evento de cliente en la bandeja de salida (outbox) con estado 'pendiente'.
 */
export function encolarEventoCrmOutbox(
  clienteId: string,
  eventType: 'cliente.creado' | 'cliente.actualizado' | 'cliente.compra_registrada',
  clienteData: any
): CrmOutboxItem {
  const eventId = `evt-crm-${Math.random().toString(36).substring(2, 10)}`;
  const nowIso = new Date().toISOString();

  const payload = {
    cliente_id: clienteId,
    crm_contact_id: clienteData.crm_contact_id || `CRM-CLI-${String(clienteId).substring(0, 8).toUpperCase()}`,
    nombres: clienteData.nombres || clienteData.nombre || '',
    apellidos: clienteData.apellidos || clienteData.apellido || '',
    email: clienteData.email || '',
    telefono: clienteData.telefono || '',
    tipo_cliente: clienteData.tipo_cliente || 'individual',
    segmento: clienteData.segmento || 'regular',
    ciudad: clienteData.ciudad || 'Santa Cruz',
    fecha_registro: clienteData.created_at || nowIso,
    metadata: clienteData.metadata || {}
  };

  const attributes: Record<string, string> = {
    grupo: 'Grupo-E',
    modulo: 'CRM-Sync',
    tipo_evento: eventType,
    cliente_id: String(clienteId),
    source: 'maxiconecta.marketplace.clientes'
  };

  const item: CrmOutboxItem = {
    id: `outbox-${Math.random().toString(36).substring(2, 10)}`,
    event_id: eventId,
    cliente_id: String(clienteId),
    event_type: eventType,
    topic: PUBSUB_TOPIC_INVENTARIOS,
    payload,
    attributes,
    estado: 'pendiente',
    intentos: 0,
    max_intentos: 5,
    ultimo_error: null,
    message_id: null,
    created_at: nowIso,
    sent_at: null,
    updated_at: nowIso
  };

  crmOutboxLogs.unshift(item);
  return item;
}

/**
 * Simula la recepción del CRM corporativo mediante suscripción de verificación.
 * Aplica IDEMPOTENCIA: Si el event_id ya existe, lo ignora y no reprocesa.
 */
export function simularRecepcionCrmIdempotente(
  eventId: string,
  eventType: string,
  clienteId: string,
  payload: any
): CrmVerificacionItem {
  const existe = crmVerificacionLogs.some(item => item.event_id === eventId);
  const nowIso = new Date().toISOString();

  const registro: CrmVerificacionItem = {
    id: `crm-rec-${Math.random().toString(36).substring(2, 10)}`,
    event_id: eventId,
    event_type: eventType,
    cliente_id: clienteId,
    payload,
    ignorado_duplicado: existe,
    crm_status: existe ? 'DUPLICADO_IGNORADO' : 'PROCESADO_OK',
    recibido_at: nowIso
  };

  crmVerificacionLogs.unshift(registro);
  return registro;
}

/**
 * Publica un evento de la outbox a Google Cloud Pub/Sub.
 */
export async function publicarEventoCrmOutbox(item: CrmOutboxItem): Promise<CrmOutboxItem> {
  item.intentos += 1;
  item.updated_at = new Date().toISOString();

  try {
    const pubLog = await publishToPubSub(
      item.event_type,
      item.payload,
      item.attributes,
      item.event_id
    );

    item.estado = 'sincronizado';
    item.message_id = pubLog.message_id;
    item.sent_at = new Date().toISOString();
    item.ultimo_error = null;

    // Ejecutar verificación en CRM con idempotencia
    simularRecepcionCrmIdempotente(
      item.event_id,
      item.event_type,
      item.cliente_id,
      item.payload
    );
  } catch (err: any) {
    item.ultimo_error = err?.message || String(err);
    if (item.intentos >= item.max_intentos) {
      item.estado = 'error';
    } else {
      item.estado = 'reintentando';
    }
  }

  return item;
}

/**
 * Procesa lote de eventos pendientes de la outbox.
 */
export async function procesarOutboxPendientes(batchSize: number = 10): Promise<CrmOutboxItem[]> {
  const pendientes = crmOutboxLogs
    .filter(it => it.estado === 'pendiente' || it.estado === 'reintentando')
    .slice(0, batchSize);

  const procesados: CrmOutboxItem[] = [];
  for (const item of pendientes) {
    const res = await publicarEventoCrmOutbox(item);
    procesados.push(res);
  }
  return procesados;
}

/**
 * Re-sincroniza un cliente forzando la creación de evento y publicación.
 */
export async function resincronizarClienteCrm(clienteId: string, clienteData: any): Promise<CrmOutboxItem> {
  const item = encolarEventoCrmOutbox(clienteId, 'cliente.actualizado', clienteData);
  return await publicarEventoCrmOutbox(item);
}

/**
 * Obtiene métricas y estado general de sincronización CRM.
 */
export function getCrmSyncStatus() {
  const total = crmOutboxLogs.length;
  const sincronizados = crmOutboxLogs.filter(it => it.estado === 'sincronizado').length;
  const pendientes = crmOutboxLogs.filter(it => it.estado === 'pendiente' || it.estado === 'reintentando').length;
  const errores = crmOutboxLogs.filter(it => it.estado === 'error').length;

  const totalCrm = crmVerificacionLogs.length;
  const duplicadosIgnorados = crmVerificacionLogs.filter(it => it.ignorado_duplicado).length;

  return {
    topic: PUBSUB_TOPIC_INVENTARIOS,
    outbox_metricas: {
      total_eventos: total,
      sincronizados,
      pendientes,
      errores
    },
    crm_verificacion_metricas: {
      total_mensajes_recibidos: totalCrm,
      duplicados_ignorados_idempotencia: duplicadosIgnorados
    },
    ultimos_eventos_outbox: crmOutboxLogs.slice(0, 30),
    ultimas_verificaciones_crm: crmVerificacionLogs.slice(0, 30)
  };
}
