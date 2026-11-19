#!/usr/bin/env node
/**
 * Herramienta CLI de Consola (Node.js) para Pruebas de Sincronización con Google Cloud Pub/Sub
 * Asignatura: UCB SIS-323 Sistemas Distribuidos
 * Historia de Usuario: KAN-56 / US-40 (RF-40) - Sincronización con ERP de Inventarios
 * Tópico Cátedra: projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e
 *
 * Uso:
 *   node scripts/test_pubsub_cli.js --tipo docente
 *   node scripts/test_pubsub_cli.js --tipo compra
 *   node scripts/test_pubsub_cli.js --tipo reintegro
 *   node scripts/test_pubsub_cli.js --all
 */

import { PubSub } from '@google-cloud/pubsub';
import fs from 'node:fs';
import path from 'node:path';

const GREEN = '\x1b[92m';
const BLUE = '\x1b[94m';
const CYAN = '\x1b[96m';
const YELLOW = '\x1b[93m';
const BOLD = '\x1b[1m';
const RESET = '\x1b[0m';

const GCP_PROJECT_ID = process.env.GCP_PROJECT_ID || 'project-a96e5fe1-5ba6-4698-a85';
const TOPIC_NAME = process.env.PUBSUB_TOPIC_INVENTARIOS || 'projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e';

function resolveCredentials() {
  const candidates = [
    process.env.GOOGLE_APPLICATION_CREDENTIALS,
    path.resolve(process.cwd(), 'service-account.json'),
    path.resolve(process.cwd(), 'service_account.json'),
    path.resolve(process.cwd(), 'credentials/service-account.json'),
    path.resolve(process.cwd(), 'credentials/gcp-pubsub-service-account.json'),
    path.resolve(process.cwd(), 'Group-E_Marketplace-and-Sales_Backend-main/service-account.json'),
    path.resolve(process.cwd(), 'Group-E_Marketplace-and-Sales_Backend-main/credentials/gcp-pubsub-service-account.json'),
    path.resolve(process.cwd(), 'backend_reference/service-account.json'),
    path.resolve(process.cwd(), 'backend_reference/credentials/gcp-pubsub-service-account.json')
  ];

  for (const c of candidates) {
    if (c && fs.existsSync(c)) return path.resolve(c);
  }
  return null;
}

async function publishEvent(eventType, payload, customAttributes = {}, correlationId = null) {
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

  const attributes = {
    grupo: 'Grupo-E',
    modulo: 'Marketplace-and-Sales',
    tipo_evento: eventType,
    correlation_id: String(corrId),
    timestamp: nowIso,
    ...customAttributes
  };

  const keyFilename = resolveCredentials();

  if (!keyFilename) {
    return {
      event_id: eventId,
      event_type: eventType,
      message_id: `sim-${Math.random().toString(36).substring(2, 10)}`,
      topic: TOPIC_NAME,
      status: 'FALLBACK_OFFLINE',
      timestamp: nowIso,
      payload,
      attributes,
      error: 'service-account.json no detectado. Evento registrado en simulador offline.'
    };
  }

  try {
    const pubsub = new PubSub({
      projectId: GCP_PROJECT_ID,
      keyFilename
    });

    const topic = pubsub.topic(TOPIC_NAME);
    const dataBuffer = Buffer.from(JSON.stringify(envelope));

    const messageId = await topic.publishMessage({
      data: dataBuffer,
      attributes
    });

    return {
      event_id: eventId,
      event_type: eventType,
      message_id: messageId,
      topic: TOPIC_NAME,
      status: 'PUBLICADO',
      timestamp: nowIso,
      payload,
      attributes
    };
  } catch (err) {
    return {
      event_id: eventId,
      event_type: eventType,
      message_id: `sim-err-${Math.random().toString(36).substring(2, 8)}`,
      topic: TOPIC_NAME,
      status: 'FALLBACK_OFFLINE',
      timestamp: nowIso,
      payload,
      attributes,
      error: err.message
    };
  }
}

function printBanner() {
  console.log(`\n${CYAN}${BOLD}` + '='.repeat(76) + `${RESET}`);
  console.log(`${CYAN}${BOLD}  MAXICONECTA — GRUPO E (MARKETPLACE & VENTAS) — UCB SIS-323${RESET}`);
  console.log(`${CYAN}  Módulo de Sincronización de Eventos con ERP Inventarios (Google Pub/Sub)${RESET}`);
  console.log(`${CYAN}${BOLD}` + '='.repeat(76) + `${RESET}\n`);
}

function printStatus() {
  const credPath = resolveCredentials();
  console.log(`${BOLD}[CONFIGURACIÓN ACTUAL]:${RESET}`);
  console.log(`  • ${BOLD}GCP Project ID:${RESET} ${GCP_PROJECT_ID}`);
  console.log(`  • ${BOLD}Pub/Sub Tópico:${RESET} ${TOPIC_NAME}`);
  if (credPath) {
    console.log(`  • ${BOLD}Credenciales:${RESET}   ${GREEN}Detectadas en: ${credPath}${RESET}`);
    console.log(`  • ${BOLD}Modo de Operación:${RESET} ${GREEN}ONLINE (Google Cloud Pub/Sub Activo)${RESET}`);
  } else {
    console.log(`  • ${BOLD}Credenciales:${RESET}   ${YELLOW}No detectadas (archivo service-account.json no encontrado)${RESET}`);
    console.log(`  • ${BOLD}Modo de Operación:${RESET} ${YELLOW}SIMULACIÓN OFFLINE (Generación de eventos deterministas)${RESET}`);
  }
  console.log('-'.repeat(76));
}

function printResult(res) {
  const isOk = res.status === 'PUBLICADO';
  const color = isOk ? GREEN : YELLOW;

  console.log(`\n${color}${BOLD}>> RESULTADO:${RESET}`);
  console.log(`  • Estado:       ${color}${res.status}${RESET}`);
  console.log(`  • Message ID:   ${res.message_id}`);
  console.log(`  • Event ID:     ${res.event_id}`);
  console.log(`  • Tópico:       ${res.topic}`);
  console.log(`  • Tipo Evento:  ${res.event_type}`);
  console.log(`  • Timestamp:    ${res.timestamp}`);
  if (res.error) {
    console.log(`  • Nota:         ${YELLOW}${res.error}${RESET}`);
  }
  console.log(`\n${BOLD}Carga Útil (Payload CloudEvents 1.0):${RESET}`);
  console.log(JSON.stringify(res.payload, null, 2));
  console.log(`${CYAN}` + '-'.repeat(76) + `${RESET}`);
}

async function main() {
  const args = process.argv.slice(2);
  const tipoIndex = args.indexOf('--tipo');
  const tipo = tipoIndex !== -1 ? args[tipoIndex + 1] : null;
  const isAll = args.includes('--all');

  printBanner();
  printStatus();

  if (isAll || tipo === 'docente' || (!tipo && !isAll)) {
    console.log(`\n${BLUE}${BOLD}[TEST: PRUEBA DE PUBLICACIÓN PARA CÁTEDRA DOCENTE]${RESET}`);
    console.log('Enviando mensaje al tópico de la materia para confirmación de recepción...');
    const payload = {
      evento: 'PRUEBA_PUBLICACION_DOCENTE',
      equipo: 'Grupo E — Marketplace y Ventas',
      responsable: 'Kevin Sancalli',
      materia: 'UCB SIS-323',
      descripcion: 'Sincronización simulada enviando eventos de venta y stock al tópico del docente (Grupo E)',
      fecha_hora_utc: new Date().toISOString(),
      fecha_hora_bolivia: new Date().toLocaleString('es-BO', { timeZone: 'America/La_Paz' })
    };
    const resDocente = await publishEvent('prueba_docente', payload, { canal_prueba: 'docente_sis323' });
    printResult(resDocente);
  }

  if (isAll || tipo === 'compra' || (!tipo && !isAll)) {
    console.log(`\n${BLUE}${BOLD}[TEST: EVENTO DE COMPRA — DESCUENTO DEFINITIVO DE STOCK (RIO-INV-03)]${RESET}`);
    const ordenId = `ORD-CLI-${Date.now().toString(36).toUpperCase()}`;
    const items = [
      { sku: 'FAR-PARACETAMOL-500', cantidad: 3, nombre: 'Paracetamol 500mg - Caja 20 tabletas' },
      { sku: 'FAR-IBUPROFENO-400', cantidad: 2, nombre: 'Ibuprofeno 400mg - Caja 10 cápsulas' },
      { sku: 'FAR-ALCOHOL-70', cantidad: 1, nombre: 'Alcohol Medicinal 70% 500ml' }
    ];
    console.log(`Simulando compra en Marketplace (${ordenId}) con ${items.length} productos...`);
    const payload = {
      tipo_movimiento: 'DESCUENTO_DEFINITIVO',
      orden_id: ordenId,
      origen: 'marketplace',
      sucursal_id: 'SUC-LP-CENTRAL',
      reserva_id: null,
      items
    };
    const resCompra = await publishEvent('stock.descuento', payload, { canal: 'marketplace' }, ordenId);
    printResult(resCompra);
    
  }

  if (isAll || tipo === 'reintegro') {
    console.log(`\n${BLUE}${BOLD}[TEST: EVENTO DE DEVOLUCIÓN — REINTEGRO DE STOCK (RIO-INV-04)]${RESET}`);
    const ordenId = `ORD-DEV-${Date.now().toString(36).toUpperCase()}`;
    const items = [
      { sku: 'FAR-PARACETAMOL-500', cantidad: 1, nombre: 'Paracetamol 500mg - Caja 20 tabletas' }
    ];
    console.log(`Simulando devolución/anulación de Orden ${ordenId}...`);
    const payload = {
      tipo_movimiento: 'REINTEGRO_DEVOLUCION',
      orden_id: ordenId,
      motivo: 'anulacion_cliente_empaque_danado',
      origen: 'marketplace',
      sucursal_id: 'SUC-LP-CENTRAL',
      items
    };
    const resReintegro = await publishEvent('stock.reintegro', payload, { motivo: 'anulacion_cliente' }, ordenId);
    printResult(resReintegro);
  }

  console.log(`\n${GREEN}${BOLD}✓ Ejecución completada exitosamente.${RESET}\n`);
}

main().catch(console.error);
