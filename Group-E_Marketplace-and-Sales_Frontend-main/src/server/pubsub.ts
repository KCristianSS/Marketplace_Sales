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
