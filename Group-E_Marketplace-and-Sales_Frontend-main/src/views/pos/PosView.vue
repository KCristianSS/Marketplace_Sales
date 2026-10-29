<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { apiClient } from '@/api/client';
import { consultarStock, resolverPrecioVariante } from '@/api/catalogo';
import { obtenerCajaActivaApi, obtenerCajaPorIdApi } from '@/api/caja';
import { obtenerTicketParaReimpresion, obtenerVentasRecientesPos, type VentaPOSReciente } from '@/api/pos';
import FiscalBillingForm from '@/components/FiscalBillingForm.vue';
import QuickStockModal from '@/components/QuickStockModal.vue';
import CajaAperturaModal from '@/components/pos/CajaAperturaModal.vue';
import CajaMovimientoModal from '@/components/pos/CajaMovimientoModal.vue';
import CajaArqueoCierreModal from '@/components/pos/CajaArqueoCierreModal.vue';
import ClickAndCollectModal from '@/components/ClickAndCollectModal.vue';
import SplitPaymentPanel from '@/components/pos/SplitPaymentPanel.vue';
import { usePosSyncStore } from '@/stores/posSync';
import { useAuthStore } from '@/stores/auth';
import type { Producto, DatosFiscales, TramoPagoPos, CajaTurno, ArqueoCajaResultado } from '@/types';
import { 
  Scan, 
  Trash2, 
  PauseCircle, 
  PlayCircle, 
  CreditCard, 
  Banknote, 
  QrCode, 
  Printer, 
  CheckCircle, 
  Store,
  FileText,
  ShieldCheck,
  CheckCircle2,
  PackageSearch,
  Zap,
  RefreshCw,
  X,
  ArrowDownLeft,
  ArrowUpRight,
  Calculator,
  Lock,
  AlertCircle,
  PackageCheck
} from 'lucide-vue-next';

interface PosItem {
  id: string;
  variante_id?: string;
  sku: string;
  nombre: string;
  precio: number;
  cantidad: number;
}

interface TicketEmitido {
  orden_id: string;
  codigo_orden: string;
  subtotal_neto: number;
  monto_iva: number;
  total: number;
  metodo_pago: string;
  desglose_pagos: Array<{
    metodo: string;
    monto: number;
    transaccion_id?: string | null;
    referencia?: string | null;
    cambio?: number;
  }>;
  cambio_total: number;
  factura_estado: 'autorizada' | 'pendiente';
  factura_mensaje?: string | null;
  numero_factura?: number | null;
  cuf?: string | null;
  cufd?: string | null;
  qr_url?: string | null;
  qr_code?: string | null;
  items: Array<{
    sku: string;
    nombre: string;
    cantidad: number;
    precio_unitario: number;
    total_linea: number;
  }>;
  ticket_impresion: string;
  duplicado?: boolean;
}

function numeroDeApi(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizarTicketEmitido(response: unknown): TicketEmitido {
  if (!response || typeof response !== 'object') {
    throw new Error('El POS devolvió una respuesta de venta inválida.');
  }

  const ticket = response as Record<string, unknown>;
  const items = Array.isArray(ticket.items) ? ticket.items : [];
  const desglose = Array.isArray(ticket.desglose_pagos) ? ticket.desglose_pagos : [];
  const facturaEstado = ticket.factura_estado === 'autorizada' ? 'autorizada' : 'pendiente';

  return {
    orden_id: String(ticket.orden_id ?? ''),
    codigo_orden: String(ticket.codigo_orden ?? ''),
    subtotal_neto: numeroDeApi(ticket.subtotal_neto),
    monto_iva: numeroDeApi(ticket.monto_iva),
    total: numeroDeApi(ticket.total),
    metodo_pago: String(ticket.metodo_pago ?? ''),
    desglose_pagos: desglose.map((value) => {
      const pago = value && typeof value === 'object' ? value as Record<string, unknown> : {};
      return {
        metodo: String(pago.metodo ?? ''),
        monto: numeroDeApi(pago.monto),
        transaccion_id: pago.transaccion_id == null ? null : String(pago.transaccion_id),
        referencia: pago.referencia == null ? null : String(pago.referencia),
        cambio: numeroDeApi(pago.cambio),
      };
    }),
    cambio_total: numeroDeApi(ticket.cambio_total),
    factura_estado: facturaEstado,
    factura_mensaje: ticket.factura_mensaje == null ? null : String(ticket.factura_mensaje),
    numero_factura: ticket.numero_factura == null ? null : numeroDeApi(ticket.numero_factura),
    cuf: ticket.cuf == null ? null : String(ticket.cuf),
    cufd: ticket.cufd == null ? null : String(ticket.cufd),
    qr_url: ticket.qr_url == null ? null : String(ticket.qr_url),
    qr_code: ticket.qr_code == null ? null : String(ticket.qr_code),
    items: items.map((value) => {
      const item = value && typeof value === 'object' ? value as Record<string, unknown> : {};
      return {
        sku: String(item.sku ?? ''),
        nombre: String(item.nombre ?? ''),
        cantidad: numeroDeApi(item.cantidad),
        precio_unitario: numeroDeApi(item.precio_unitario),
        total_linea: numeroDeApi(item.total_linea),
      };
    }),
    ticket_impresion: String(ticket.ticket_impresion ?? ''),
  };
}

const authStore = useAuthStore();
const skuInput = ref('');
const cajaAbierta = ref(false);
const cajaId = ref<string | null>(null);
const cajaActual = ref<CajaTurno | null>(null);
const cargandoCaja = ref(false);

const isAperturaModalOpen = ref(false);
const isMovimientoModalOpen = ref(false);
const isArqueoModalOpen = ref(false);
const isClickAndCollectModalOpen = ref(false);

const SUCURSAL_POR_DEFECTO = 'b0000000-0000-0000-0000-000000000001';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// caja_turnos.sucursal_id is a UUID; older cached profiles may still carry a text code.
const sucursalId = computed(() => {
  const perfil = authStore.user?.sucursal_id;
  return perfil && UUID_RE.test(perfil) ? perfil : SUCURSAL_POR_DEFECTO;
});
const sucursalListaPrecioId = 'SUC-LP-CENTRAL';
const cajeroId = computed(() => authStore.user?.id || authStore.user?.user_id || 'a0000000-0000-0000-0000-000000000001');
const sucursalNombre = ref('Sucursal Central - La Paz');
const cajeroNombre = computed(() => 
  authStore.user?.nombre_completo 
    ? `Cajero: ${authStore.user.nombre_completo}` 
    : 'Cajero: Oscar Menacho (Turno Mañana)'
);
const catalogoDb = ref<Producto[]>([]);
const stockBySku = ref<Record<string, number>>({});
const tipoClientePos = ref<'retail' | 'corporativo_b2b'>('retail');
const isAddingItem = ref(false);
const isSuggestionsOpen = ref(false);
const highlightedIndex = ref(0);

interface PosSearchCandidate {
  sku: string;
  nombre: string;
  precio: number;
  searchText: string;
}

function normalizarTexto(texto: string) {
  return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

const searchCandidates = computed<PosSearchCandidate[]>(() => {
  const candidates = new Map<string, PosSearchCandidate>();
  for (const product of catalogoDb.value) {
    candidates.set(product.sku, {
      sku: product.sku,
      nombre: product.nombre,
      precio: Number(product.precio || 0),
      searchText: normalizarTexto(`${product.nombre} ${product.sku} ${product.marca || ''}`)
    });
  }
  for (const product of Object.values(posSyncStore.catalogoLocal)) {
    if (!candidates.has(product.sku) && product.estado !== 'baja') {
      candidates.set(product.sku, {
        sku: product.sku,
        nombre: product.nombre,
        precio: Number(product.precio_referencia || 0),
        searchText: normalizarTexto(`${product.nombre} ${product.sku}`)
      });
    }
  }
  return [...candidates.values()];
});

const suggestions = computed(() => {
  const tokens = normalizarTexto(skuInput.value).split(/\s+/).filter(Boolean);
  if (!tokens.length || skuInput.value.trim().length < 2) return [];
  return searchCandidates.value
    .filter(candidate => tokens.every(token => candidate.searchText.includes(token)))
    .slice(0, 8);
});

watch(skuInput, () => {
  highlightedIndex.value = 0;
  isSuggestionsOpen.value = true;
});

// Resuelve SKU exacto (incluido el SKU de una variante) antes que coincidencias por nombre.
function skuExacto(texto: string): string | null {
  const buscado = texto.trim().toUpperCase();
  const producto = catalogoDb.value.find(product =>
    product.sku.toUpperCase() === buscado || product.variantes?.some(variant => variant.sku.toUpperCase() === buscado)
  );
  if (producto) return producto.sku;
  return posSyncStore.buscarPorSku(buscado)?.sku ?? null;
}

function mostrarAviso(message: string) {
  syncToast.value = { message, type: 'warn', timestamp: new Date().toLocaleTimeString() };
}

async function submitBusqueda() {
  const texto = skuInput.value.trim();
  if (!texto || isAddingItem.value) return;

  const exacto = skuExacto(texto);
  if (exacto) return agregarProducto(exacto);

  if (isSuggestionsOpen.value && suggestions.value[highlightedIndex.value] && suggestions.value.length > 1) {
    return agregarProducto(suggestions.value[highlightedIndex.value].sku);
  }
  if (suggestions.value.length === 1) return agregarProducto(suggestions.value[0].sku);
  if (suggestions.value.length > 1) {
    isSuggestionsOpen.value = true;
    mostrarAviso(`Hay ${suggestions.value.length} productos que coinciden con "${texto}". Selecciona uno de la lista.`);
    return;
  }
  if (searchCandidates.value.length === 0) return agregarProducto(texto.toUpperCase());
  mostrarAviso(`No se encontró ningún producto con el SKU o nombre "${texto}".`);
}

function seleccionarSugerencia(candidate: PosSearchCandidate) {
  isSuggestionsOpen.value = false;
  void agregarProducto(candidate.sku);
}

function onSearchKeydown(event: KeyboardEvent) {
  if (!isSuggestionsOpen.value || !suggestions.value.length) return;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    highlightedIndex.value = (highlightedIndex.value + 1) % suggestions.value.length;
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    highlightedIndex.value = (highlightedIndex.value - 1 + suggestions.value.length) % suggestions.value.length;
  } else if (event.key === 'Escape') {
    isSuggestionsOpen.value = false;
  }
}

// Control de Stock Multi-Sucursal y Sincronización SSE
const isQuickStockOpen = ref(false);
const posSyncStore = usePosSyncStore();

// Banner de Sincronización Multicanal Reactiva (RF-08)
const syncToast = ref<{ message: string; type: 'info' | 'success' | 'warn'; timestamp: string } | null>(null);

function onCatalogoEvent(event: any) {
  const detail = event.detail;
  if (!detail) return;

  if (detail.sku) {
    const sku = detail.sku.toUpperCase();
    const dbIndex = catalogoDb.value.findIndex(p => p.sku === sku);
    if (dbIndex >= 0) {
      if (detail.precio !== undefined) catalogoDb.value[dbIndex].precio = Number(detail.precio);
      if (detail.nombre) catalogoDb.value[dbIndex].nombre = detail.nombre;
    } else if (detail.nombre) {
      catalogoDb.value.push({
        id: detail.producto_id || detail.id || crypto.randomUUID(),
        sku: sku,
        nombre: detail.nombre,
        precio: detail.precio ? Number(detail.precio) : 0,
        categoria_id: '',
        estado: detail.estado || 'publicado'
      });
    }

    // Actualización reactiva de precios en el ticket activo ante cambios administrativos
    const cartItem = cartItems.value.find(i => i.sku === sku);
    if (cartItem && detail.precio !== undefined && Number(detail.precio) !== cartItem.precio) {
      const oldPrice = cartItem.precio;
      cartItem.precio = Number(detail.precio);
      syncToast.value = {
        message: `🔄 Sincronización Multicanal: El precio de "${cartItem.nombre}" se actualizó de BOB ${oldPrice.toFixed(2)} a BOB ${cartItem.precio.toFixed(2)} en tiempo real.`,
        type: 'info',
        timestamp: new Date().toLocaleTimeString()
      };
      setTimeout(() => { syncToast.value = null; }, 7000);
    } else if (detail.tipo === 'producto_creado') {
      syncToast.value = {
        message: `✨ Catálogo Actualizado: Nuevo producto "${detail.nombre}" disponible para venta en POS.`,
        type: 'success',
        timestamp: new Date().toLocaleTimeString()
      };
      setTimeout(() => { syncToast.value = null; }, 5000);
    }
  } else if (detail.tipo === 'sincronizacion_masiva' || detail.tipo === 'catalogo_resincronizado') {
    loadPosCatalog();
    syncToast.value = {
      message: `⚡ Sincronización Global: Catálogo y precios actualizados desde el Administrador.`,
      type: 'success',
      timestamp: new Date().toLocaleTimeString()
    };
    setTimeout(() => { syncToast.value = null; }, 5000);
  }
}

async function manualSyncPos() {
  await posSyncStore.forzarResincronizacion();
  await loadPosCatalog();
  syncToast.value = {
    message: `Sincronización completada: ${posSyncStore.totalProductosSincronizados} productos en memoria local.`,
    type: 'success',
    timestamp: new Date().toLocaleTimeString()
  };
  setTimeout(() => { syncToast.value = null; }, 4000);
}

function getItemStock(sku: string): number {
  if (stockBySku.value[sku] !== undefined) return stockBySku.value[sku];
  const match = catalogoDb.value.find(p => p.sku === sku) as any;
  if (match && match.stock !== undefined && match.stock !== null) {
    return Number(match.stock);
  }
  return 0;
}

function onSelectProductFromStockModal(sku: string) {
  void agregarProducto(sku);
}
const cajaError = ref('');
const cobroError = ref('');
const isProcessingPayment = ref(false);
const ticketEmitido = ref<TicketEmitido | null>(null);
const isRecentSalesModalOpen = ref(false);
const ventasRecientes = ref<VentaPOSReciente[]>([]);
const cargandoVentasRecientes = ref(false);
const reimpresionError = ref('');
const reimprimiendoOrdenId = ref<string | null>(null);

// Cargar catálogo de Supabase para obtener precios reales al escanear
async function loadPosCatalog() {
  try {
    const res = await apiClient.get('/api/v1/catalogo/productos');
    catalogoDb.value = Array.isArray(res.data) ? res.data : (res.data as any)?.productos || [];
    await Promise.allSettled(cartItems.value.map(actualizarPrecioYStockItem));
  } catch (err) {
    console.error('Error cargando catálogo en POS:', err);
  }
}

async function actualizarPrecioYStockItem(item: PosItem) {
  const stock = await consultarStock(item.sku, sucursalListaPrecioId);
  stockBySku.value[item.sku] = stock.stock_disponible;
  const match = catalogoDb.value.find(product => product.sku === item.sku);
  const varianteId = match?.variante_id || match?.variantes?.[0]?.id || match?.id || item.variante_id;
  if (!varianteId) return;
  item.variante_id = varianteId;
  const resolution = await resolverPrecioVariante({
    variante_id: varianteId,
    canal: 'pos',
    tipo_cliente: tipoClientePos.value,
    sucursal_id: sucursalListaPrecioId
  });
  item.precio = Number(resolution.precio) * (resolution.moneda === 'USD' ? 6.96 : 1);
}

async function recalcularPreciosPos() {
  await Promise.allSettled(cartItems.value.map(actualizarPrecioYStockItem));
}

const cartItems = ref<PosItem[]>([]);

const suspendedSales = ref<{
  id: string;
  cliente_referencia: string;
  items: any[];
  subtotal: number;
}[]>([]);

const subtotal = computed(() => cartItems.value.reduce((acc, curr) => acc + (curr.precio * curr.cantidad), 0));
const total = computed(() => subtotal.value);
const montoIva = computed(() => Math.round((total.value * 13 / 113) * 100) / 100);
const subtotalNeto = computed(() => Math.round((total.value - montoIva.value) * 100) / 100);

// Modal de Cobro & Datos Fiscales (KAN-346, KAN-364, KAN-367)
const isPayModalOpen = ref(false);
const isSuspendedModalOpen = ref(false);
const payMethod = ref<'efectivo' | 'tarjeta' | 'qr'>('efectivo');
const cashGiven = ref<number>(11000);
const changeDue = computed(() => Math.max(0, (cashGiven.value || 0) - total.value));
// Pago dividido: varios métodos de pago en una misma venta
const splitMode = ref(false);
const splitLegs = ref<TramoPagoPos[]>([]);
const isSplitValid = ref(false);
const centavos = (n: number | null | undefined) => Math.round(((Number(n) || 0) + Number.EPSILON) * 100);

function activarPagoDividido(activo: boolean) {
  splitMode.value = activo;
  if (!activo) {
    splitLegs.value = [];
    isSplitValid.value = false;
    return;
  }
  // Punto de partida sugerido: mitad en efectivo y mitad con tarjeta (editable por el cajero).
  const mitad = Math.floor(centavos(total.value) / 2);
  splitLegs.value = [
    { id: `tramo-${Date.now()}-a`, metodo: 'efectivo', monto: mitad / 100, referencia: '', recibido: null },
    { id: `tramo-${Date.now()}-b`, metodo: 'tarjeta', monto: (centavos(total.value) - mitad) / 100, referencia: '', recibido: null },
  ];
}

const isReceiptReady = ref(false);

// Estado de datos fiscales (NIT / CI / Razón Social / Consumidor Final)
const fiscalData = ref<DatosFiscales>({
  modalidad: 'con_factura',
  tipo_documento: 'NIT',
  nit_ci: '1020304050',
  razon_social: 'EMPRESA MINERA SAN CRISTÓBAL S.A.',
  email_facturacion: 'contabilidad@sancristobal.bo',
  guardar_perfil: true
});
const isFiscalValid = ref(true);

async function verificarCajaActiva() {
  cargandoCaja.value = true;
  try {
    const activa = await obtenerCajaActivaApi();
    if (activa) {
      cajaActual.value = activa;
      cajaId.value = activa.id;
      cajaAbierta.value = true;
      console.log('Caja activa detectada:', activa.id);
      void cargarVentasRecientes();
    } else {
      cajaActual.value = null;
      cajaId.value = null;
      cajaAbierta.value = false;
      isAperturaModalOpen.value = true;
    }
  } catch (error) {
    console.warn('No se pudo consultar caja activa:', error);
    cajaAbierta.value = false;
    isAperturaModalOpen.value = true;
  } finally {
    cargandoCaja.value = false;
  }
}

function onCajaOpened(caja: CajaTurno) {
  cajaActual.value = caja;
  cajaId.value = caja.id;
  cajaAbierta.value = true;
  isAperturaModalOpen.value = false;
  cargarVentasSuspendidas();
  void cargarVentasRecientes();
}

async function abrirVentasRecientes() {
  isRecentSalesModalOpen.value = true;
  reimpresionError.value = '';
  await cargarVentasRecientes();
}

async function cargarVentasRecientes() {
  if (!cajaId.value) return;
  cargandoVentasRecientes.value = true;
  try {
    ventasRecientes.value = await obtenerVentasRecientesPos(cajaId.value);
  } catch (error: any) {
    reimpresionError.value = error.response?.data?.detail || 'No se pudieron cargar las ventas del turno.';
  } finally {
    cargandoVentasRecientes.value = false;
  }
}

async function prepararReimpresion(venta: VentaPOSReciente) {
  reimprimiendoOrdenId.value = venta.orden_id;
  reimpresionError.value = '';
  try {
    ticketEmitido.value = await obtenerTicketParaReimpresion(venta.orden_id);
    isRecentSalesModalOpen.value = false;
    isPayModalOpen.value = true;
    isReceiptReady.value = true;
  } catch (error: any) {
    reimpresionError.value = error.response?.data?.detail || 'No se pudo recuperar el comprobante.';
  } finally {
    reimprimiendoOrdenId.value = null;
  }
}

async function onMovementAdded() {
  if (cajaId.value) {
    try {
      cajaActual.value = await obtenerCajaPorIdApi(cajaId.value);
    } catch (e) {
      console.warn('Error al actualizar caja tras movimiento:', e);
    }
  }
}

function onCajaClosed(arqueo: ArqueoCajaResultado) {
  cajaAbierta.value = false;
  cajaId.value = null;
  cajaActual.value = null;
}

async function agregarProducto(sku: string) {
  isAddingItem.value = true;
  try {
    const stock = await consultarStock(sku, sucursalListaPrecioId);
    stockBySku.value[sku] = stock.stock_disponible;
    const existing = cartItems.value.find(item => item.sku === sku);
    if (stock.stock_disponible <= (existing?.cantidad || 0)) {
      mostrarAviso(`Stock insuficiente para ${sku}. Disponibles: ${stock.stock_disponible}.`);
      return;
    }

    const localSync = posSyncStore.buscarPorSku(sku);
    const match = catalogoDb.value.find(product => product.sku === sku);
    const varianteId = match?.variante_id || match?.variantes?.[0]?.id || match?.id || localSync?.id;
    if (!varianteId) {
      mostrarAviso(`El producto ${sku} no existe en el catálogo. No se agregó al ticket.`);
      return;
    }
    const resolution = await resolverPrecioVariante({
      variante_id: varianteId,
      canal: 'pos',
      tipo_cliente: tipoClientePos.value,
      sucursal_id: sucursalListaPrecioId
    });
    const itemPrice = Number(resolution.precio) * (resolution.moneda === 'USD' ? 6.96 : 1);

    if (existing) {
      existing.cantidad += 1;
      existing.precio = itemPrice;
    } else {
      cartItems.value.push({
        id: Date.now().toString(),
        sku,
        nombre: match?.nombre || localSync?.nombre || `Artículo Escaneado [${sku}]`,
        precio: itemPrice,
        cantidad: 1,
        variante_id: varianteId
      });
    }
    skuInput.value = '';
    isSuggestionsOpen.value = false;
  } catch {
    mostrarAviso(`No se pudo verificar el stock o precio de ${sku}. No se agregó al ticket.`);
  } finally {
    isAddingItem.value = false;
async function abrirCaja() {
  try {
    const { data } = await apiClient.post('/api/v1/pos/caja/abrir', {
      sucursal_id: sucursalId.value,
      cajero_id: cajeroId.value,
      fondo_inicial: 0
    });
    cajaId.value = data.id;
    cajaAbierta.value = data.estado === 'abierta';
    cajaError.value = '';
  } catch (error: any) {
    cajaError.value = error.response?.data?.detail || 'No se pudo abrir la caja. Inicia sesión con un usuario autorizado.';
    cajaAbierta.value = false;
  }
}

function addItemByBarcode() {
  if (skuInput.value.trim()) {
    agregarProducto(skuInput.value.trim().toUpperCase());
  }
}
  }
}

function removeItem(id: string) {
  cartItems.value = cartItems.value.filter(i => i.id !== id);
}

async function suspenderVenta() {
  if (cartItems.value.length === 0) return;

  const venta = {
    id: Date.now().toString(),
    cliente_referencia: fiscalData.value.razon_social || 'POS-CLIENTE',
    items: cartItems.value.map(item => ({
      variante_id: item.variante_id || crypto.randomUUID(),
      sku: item.sku,
      nombre: item.nombre,
      cantidad: item.cantidad,
      precio_unitario: item.precio
    })),
    subtotal: total.value
  };

  try {
    if (!cajaId.value) {
      console.error('No hay caja abierta');
      return;
    }

    await apiClient.post(
      `/api/v1/pos/ventas/${cajaId.value}/suspender`,
      venta
    );

    cartItems.value = [];

    await cargarVentasSuspendidas();
  } catch (error) {
    console.error('Error al suspender la venta:', error);
  }
}

async function cargarVentasSuspendidas() {
  try {
    if (!cajaId.value) {
      console.error('No hay caja abierta');
      return;
    }

    const response = await apiClient.get(
      `/api/v1/pos/ventas/${cajaId.value}/suspendidas`
    );

    suspendedSales.value = response.data;
  } catch (error) {
    console.error(
      'Error al cargar ventas suspendidas:',
      error
    );
  }
}

async function reanudarVenta(index: number) {
  const sale = suspendedSales.value[index];

  if (!sale) return;

  try {
    if (!cajaId.value) {
      console.error('No hay caja abierta');
      return;
    }

    const response = await apiClient.delete(
      `/api/v1/pos/ventas/${cajaId.value}/suspendidas/${sale.id}`
    );

    cartItems.value = response.data.items.map((item: any) => ({
      id: item.variante_id || item.sku || Date.now().toString(),
      sku: item.sku,
      nombre: item.nombre,
      precio: Number(item.precio_unitario),
      cantidad: item.cantidad,
      variante_id: item.variante_id
    }));

    if (sale.cliente_referencia && sale.cliente_referencia !== 'POS-CLIENTE') {
      fiscalData.value.razon_social = sale.cliente_referencia;
    }

    suspendedSales.value.splice(index, 1);
  } catch (error) {
    console.error(
      'Error al recuperar la venta:',
      error
    );
  }
}

// Emisión oficial de ticket tributario POS (RF-10 / RIO-PAG-02 / RIO-INV-03)
async function finalizarCobro() {
  if (cartItems.value.length === 0) {
    cobroError.value = 'Agrega productos al ticket antes de cobrar.';
    return;
  }
  if (!cajaId.value || !cajaAbierta.value) {
    cobroError.value = 'No hay una caja abierta. Vuelve a abrir la caja antes de cobrar.';
    return;
  }
  if (!splitMode.value && payMethod.value === 'efectivo' && (cashGiven.value || 0) < total.value) {
    cobroError.value = 'El monto recibido no cubre el total de la venta.';
    return;
  }
  if (!isFiscalValid.value && fiscalData.value.modalidad === 'con_factura') {
    cobroError.value = 'Por favor verifica el NIT/CI y la Razón Social antes de procesar el cobro.';
    return;
  }
  if (splitMode.value && !isSplitValid.value) {
    cobroError.value = 'El pago dividido está incompleto: los montos deben sumar exactamente el total a cobrar.';
    return;
  }

  isProcessingPayment.value = true;
  cobroError.value = '';

  try {
    for (const item of cartItems.value) {
      const stock = await consultarStock(item.sku, sucursalListaPrecioId);
      stockBySku.value[item.sku] = stock.stock_disponible;
      if (item.cantidad > stock.stock_disponible) {
        throw new Error(`Stock insuficiente para ${item.nombre}. Disponibles: ${stock.stock_disponible}.`);
      }
    }

    const pagos = splitMode.value
      ? splitLegs.value.map((tramo) => ({
          metodo: tramo.metodo,
          monto: Number(tramo.monto),
          referencia: tramo.referencia || undefined,
          monto_recibido: tramo.metodo === 'efectivo' && tramo.recibido ? Number(tramo.recibido) : undefined,
        }))
      : [{
          metodo: payMethod.value,
          monto: total.value,
          monto_recibido: payMethod.value === 'efectivo' ? Number(cashGiven.value) : undefined,
        }];

    // Este endpoint coordina el cobro, el descuento de stock y la solicitud fiscal.
    // Evita volver a facturar la misma venta en un segundo endpoint.
    const { data } = await apiClient.post<unknown>('/api/v1/pos/ventas/cobrar', {
      caja_id: cajaId.value,
      sucursal_id: sucursalId.value,
      cliente_nit_ci: fiscalData.value.nit_ci || '0',
      cliente_razon_social: fiscalData.value.razon_social || 'CONSUMIDOR FINAL',
      modalidad: fiscalData.value.modalidad,
      tipo_documento: fiscalData.value.tipo_documento,
      email_facturacion: fiscalData.value.email_facturacion,
      guardar_perfil: fiscalData.value.guardar_perfil ?? true,
      items: cartItems.value.map((item) => ({
        variante_id: item.variante_id || item.id,
        sku: item.sku,
        nombre: item.nombre,
        cantidad: item.cantidad,
        precio_unitario: item.precio,
      })),
      metodo_pago: splitMode.value ? (splitLegs.value[0]?.metodo || payMethod.value) : payMethod.value,
      pagos,
    });

    ticketEmitido.value = normalizarTicketEmitido(data);
    isReceiptReady.value = true;
    void cargarVentasRecientes();
    if (cajaId.value) {
      obtenerCajaPorIdApi(cajaId.value)
        .then((updated) => {
          cajaActual.value = updated;
        })
        .catch(() => {});
    }
  } catch (error: any) {
    cobroError.value = error.response?.data?.detail || error.message || 'No se pudo confirmar la venta. Verifica el estado de caja antes de volver a cobrar.';
  } finally {
    isProcessingPayment.value = false;
  }
}

function imprimirTicket() {
  window.print();
}

function resetPos() {
  cartItems.value = [];
  isPayModalOpen.value = false;
  isReceiptReady.value = false;
  ticketEmitido.value = null;
  cobroError.value = '';
  splitMode.value = false;
  splitLegs.value = [];
  isSplitValid.value = false;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'F3') {
    e.preventDefault();
    isQuickStockOpen.value = !isQuickStockOpen.value;
  } else if (e.key === 'F6') {
    e.preventDefault();
    isClickAndCollectModalOpen.value = !isClickAndCollectModalOpen.value;
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleKeydown);
  window.addEventListener('maxiconecta:catalogo-actualizado', onCatalogoEvent);
  posSyncStore.iniciar();
  await verificarCajaActiva();
  await loadPosCatalog();
  if (cajaId.value) {
    await cargarVentasSuspendidas();
  }
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown);
  window.removeEventListener('maxiconecta:catalogo-actualizado', onCatalogoEvent);
  posSyncStore.detenerEscuchaEnTiempoReal();
});

</script>

<template>
  <div class="min-h-[calc(100vh-8rem)] flex flex-col gap-5">
    <!-- Header de Caja y Turno (RF-09) -->
    <div class="relative overflow-hidden bg-slate-950 text-white px-5 py-4 rounded-xl flex flex-col sm:flex-row justify-between gap-4 sm:items-center shadow-xl shadow-slate-900/20">
      <div class="absolute inset-0 opacity-40 surface-grid" />
      <div class="flex items-center gap-3">
        <span class="relative w-10 h-10 rounded-lg bg-cyan-400/15 border border-cyan-300/20 flex items-center justify-center"><Store class="w-5 h-5 text-cyan-300" /></span>
        <div>
          <h2 class="text-sm font-bold">{{ sucursalNombre }}</h2>
          <p class="text-xs text-slate-400">{{ cajeroNombre }}</p>
        </div>
      </div>
      <div class="relative flex items-center gap-3">
        <!-- Badge y Botón de Sincronización SSE en tiempo real (RF-08) -->
        <button
          type="button"
          @click="manualSyncPos"
          :disabled="posSyncStore.sincronizando"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-300 border border-slate-700 transition-all cursor-pointer"
          :title="'Hacer clic para sincronizar catálogo delta. Última sincronización: ' + (posSyncStore.ultimaSincronizacion || 'Inicial')"
        >
          <span class="w-2 h-2 rounded-full" :class="posSyncStore.conectado ? 'bg-cyan-400 animate-pulse' : 'bg-emerald-400'"></span>
          <span>{{ posSyncStore.conectado ? 'SSE En Vivo' : 'Catálogo Local' }}</span>
          <span class="px-1.5 py-0.2 rounded-md bg-slate-900 text-cyan-300 text-[10px] font-bold">
            {{ posSyncStore.totalProductosSincronizados }} SKUs
          </span>
          <RefreshCw class="w-3.5 h-3.5 text-slate-400" :class="posSyncStore.sincronizando ? 'animate-spin text-cyan-400' : ''" />
        </button>

        <!-- Botón de Consulta Rápida de Stock (RF-07 / Atajo F3) -->
        <button
          type="button"
          @click="isQuickStockOpen = true"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-500/20 transition-all active:scale-95 border border-blue-400/40"
          title="Consultar Stock Multi-Sucursal (F3)"
        >
          <PackageSearch class="w-3.5 h-3.5" />
          <span>Stock Multi-Sucursal [F3]</span>
        </button>

        <!-- Botón Click & Collect (RF-11 / KAN-27 / Subtareas KAN-326, KAN-327) -->
        <button
          type="button"
          @click="isClickAndCollectModalOpen = true"
          class="text-xs bg-teal-950/80 hover:bg-teal-900 border border-teal-500/50 text-teal-200 px-3 py-1.5 rounded-lg font-bold flex items-center gap-1.5 shadow-sm transition-all hover:scale-[1.02]"
          title="Módulo de validación y entrega de compras Click & Collect (Atajo F6)"
        >
          <PackageCheck class="w-3.5 h-3.5 text-teal-400" />
          <span>Click & Collect <kbd class="px-1 py-0.2 bg-teal-900 border border-teal-700 rounded text-[10px] font-mono">F6</kbd></span>
        </button>

        <!-- Estado y Botones de Caja (RF-09) -->
        <template v-if="cajaAbierta">
          <button
            type="button"
            @click="abrirVentasRecientes"
            class="inline-flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-950/70 px-3 py-1.5 text-xs font-bold text-blue-200 transition-colors hover:bg-blue-900"
            title="Consultar las últimas 10 ventas y reimprimir un comprobante"
          >
            <Printer class="h-3.5 w-3.5" />
            <span>Reimprimir ticket</span>
          </button>

          <span 
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
            :title="'Caja abierta ID: ' + (cajaId || '') + ' - Fondo: Bs. ' + (cajaActual?.fondo_inicial || 0)"
          >
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> 
            <span>Caja Abierta (Fondo: Bs. {{ Number(cajaActual?.fondo_inicial || 0).toFixed(0) }})</span>
          </span>

          <button
            type="button"
            @click="isMovimientoModalOpen = true"
            class="inline-flex items-center gap-1.5 text-xs bg-slate-800 hover:bg-slate-700 active:scale-95 px-3 py-1.5 rounded-lg border border-slate-700 font-semibold text-cyan-300 transition-all cursor-pointer"
            title="Registrar Ingreso o Egreso Manual de Efectivo"
          >
            <Banknote class="w-3.5 h-3.5 text-cyan-400" />
            <span>Movimientos</span>
          </button>

          <button
            type="button"
            @click="isArqueoModalOpen = true"
            class="inline-flex items-center gap-1.5 text-xs bg-indigo-950/80 hover:bg-indigo-900 active:scale-95 px-3 py-1.5 rounded-lg border border-indigo-700/60 font-semibold text-indigo-200 transition-all cursor-pointer shadow-sm"
            title="Arqueo y Cierre de Turno de Caja"
          >
            <Calculator class="w-3.5 h-3.5 text-indigo-400" />
            <span>Arqueo / Cierre</span>
          </button>
        </template>

        <template v-else>
          <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-500/20 text-red-300 border border-red-500/30">
            <span class="w-2 h-2 rounded-full bg-red-400"></span> Caja Cerrada
          </span>

          <button
            type="button"
            @click="isAperturaModalOpen = true"
            class="inline-flex items-center gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white px-3 py-1.5 rounded-lg font-bold transition-all cursor-pointer shadow-md shadow-emerald-600/20"
          >
            <Store class="w-3.5 h-3.5" />
            <span>Aperturar Caja</span>
          </button>
        </template>

        <label class="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-semibold text-slate-300">
          Cliente
          <select v-model="tipoClientePos" @change="recalcularPreciosPos" class="bg-transparent text-white outline-none">
            <option value="retail" class="text-slate-900">Retail</option>
            <option value="corporativo_b2b" class="text-slate-900">Corporativo B2B</option>
          </select>
        </label>
      </div>
    </div>
    <p v-if="cajaError" role="alert" class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs font-semibold text-rose-700">{{ cajaError }}</p>

    <!-- Banner de Alerta cuando Caja está cerrada (RF-09) -->
    <div
      v-if="!cajaAbierta && !cargandoCaja"
      class="px-5 py-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-amber-200 shadow-sm"
    >
      <div class="flex items-center gap-2.5">
        <Lock class="w-5 h-5 text-amber-400 shrink-0" />
        <div>
          <span class="font-bold">Turno de caja no aperturado:</span>
          <span class="text-amber-200/90 ml-1">Para procesar cobros y registrar ventas presenciales, debes abrir un turno con fondo inicial.</span>
        </div>
      </div>
      <button
        type="button"
        @click="isAperturaModalOpen = true"
        class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold transition-all shrink-0 cursor-pointer shadow-md shadow-emerald-600/20"
      >
        <Store class="w-4 h-4" />
        <span>Aperturar Turno Ahora</span>
      </button>
    </div>

    <!-- Banner de Notificación de Sincronización en Tiempo Real (RF-08) -->
    <div
      v-if="syncToast"
      :class="[
        'px-4 py-2.5 rounded-xl border flex items-center justify-between text-xs font-semibold animate-in fade-in slide-in-from-top-2 shadow-sm',
        syncToast.type === 'success'
          ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
          : 'bg-cyan-50 dark:bg-cyan-950/40 border-cyan-200 dark:border-cyan-800 text-cyan-900 dark:text-cyan-200'
      ]"
    >
      <div class="flex items-center gap-2.5">
        <Zap class="w-4 h-4 text-cyan-500 shrink-0" />
        <span>{{ syncToast.message }}</span>
        <span class="text-[10px] text-slate-400 ml-2">({{ syncToast.timestamp }})</span>
      </div>
      <button @click="syncToast = null" class="p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5">
        <X class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- Contenido Principal POS -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Columna Izquierda: Escáner y Tabla de Ítems -->
      <div class="lg:col-span-2 flex flex-col min-h-[520px] bg-white/95 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-lg shadow-slate-300/20 dark:shadow-none p-4 overflow-hidden">
        <!-- Input Barcode -->
        <form @submit.prevent="submitBusqueda" class="flex gap-2 mb-4">
          <div class="relative flex-1">
            <Scan class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              v-model="skuInput"
              type="text"
              autofocus
              role="combobox"
              aria-autocomplete="list"
              aria-controls="pos-sugerencias"
              :aria-expanded="isSuggestionsOpen && suggestions.length > 0"
              :aria-activedescendant="isSuggestionsOpen && suggestions.length ? `pos-sugerencia-${highlightedIndex}` : undefined"
              placeholder="Escanear código, escribir SKU o nombre del producto y presionar ENTER..."
              class="w-full pl-10 pr-4 py-2.5 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-600 focus:outline-none font-mono"
              @keydown="onSearchKeydown"
              @focus="isSuggestionsOpen = true"
              @blur="isSuggestionsOpen = false"
            />
            <ul
              v-if="isSuggestionsOpen && suggestions.length"
              id="pos-sugerencias"
              role="listbox"
              class="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-xl dark:border-slate-700 dark:bg-slate-900"
            >
              <li
                v-for="(candidate, index) in suggestions"
                :id="`pos-sugerencia-${index}`"
                :key="candidate.sku"
                role="option"
                :aria-selected="index === highlightedIndex"
                :class="[
                  'flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm',
                  index === highlightedIndex ? 'bg-blue-50 dark:bg-blue-950/50' : 'hover:bg-slate-50 dark:hover:bg-slate-800'
                ]"
                @mousedown.prevent="seleccionarSugerencia(candidate)"
                @mouseenter="highlightedIndex = index"
              >
                <span class="min-w-0">
                  <span class="block truncate font-semibold text-slate-800 dark:text-slate-100">{{ candidate.nombre }}</span>
                  <span class="block font-mono text-xs text-slate-400">{{ candidate.sku }}</span>
                </span>
                <span class="shrink-0 text-xs font-bold text-slate-600 dark:text-slate-300">BOB {{ candidate.precio.toFixed(2) }}</span>
              </li>
            </ul>
          </div>
          <button type="submit" :disabled="isAddingItem" class="bg-teal-700 hover:bg-teal-800 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg font-bold text-sm shadow-sm">
            {{ isAddingItem ? 'Verificando...' : 'Agregar' }}
          </button>
          <button 
            type="button" 
            @click="isQuickStockOpen = true"
            class="inline-flex items-center gap-1.5 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold text-sm shadow-sm transition-all"
            title="Consultar Stock en todas las sucursales (F3)"
          >
            <PackageSearch class="w-4 h-4" />
            <span class="hidden sm:inline">Stock [F3]</span>
          </button>
        </form>

        <!-- Tabla de Productos Escaneados -->
        <div class="flex-1 overflow-y-auto border border-slate-100 dark:border-slate-800 rounded-lg">
          <table class="w-full text-left text-sm">
            <thead class="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold sticky top-0">
              <tr>
                <th class="p-3">SKU</th>
                <th class="p-3">Descripción</th>
                <th class="p-3 text-center">Stock Disp.</th>
                <th class="p-3 text-center">Cant.</th>
                <th class="p-3 text-right">Precio</th>
                <th class="p-3 text-right">Total</th>
                <th class="p-3 text-center">Acción</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="item in cartItems" :key="item.id" class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <td class="p-3 font-mono text-xs font-semibold text-blue-600 dark:text-blue-400">{{ item.sku }}</td>
                <td class="p-3 text-slate-800 dark:text-slate-200">{{ item.nombre }}</td>
                <td class="p-3 text-center">
                  <span 
                    class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-bold"
                    :class="getItemStock(item.sku) > 0 ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800' : 'bg-rose-50 text-rose-700 border border-rose-200'"
                  >
                    <span class="w-1.5 h-1.5 rounded-full" :class="getItemStock(item.sku) > 0 ? 'bg-emerald-500' : 'bg-rose-500'"></span>
                    {{ getItemStock(item.sku) }} unid.
                  </span>
                </td>
                <td class="p-3 text-center">
                  <span class="inline-block px-2 py-0.5 bg-slate-100 dark:bg-slate-800 font-bold rounded">{{ item.cantidad }}</span>
                </td>
                <td class="p-3 text-right">BOB {{ item.precio.toFixed(2) }}</td>
                <td class="p-3 text-right font-bold text-slate-900 dark:text-white">BOB {{ (item.precio * item.cantidad).toFixed(2) }}</td>
                <td class="p-3 text-center">
                  <button @click="removeItem(item.id)" class="text-rose-500 hover:text-rose-700 p-1">
                    <Trash2 class="w-4 h-4" />
                  </button>
                </td>
              </tr>
              <tr v-if="cartItems.length === 0">
                <td colspan="7" class="p-8 text-center text-slate-400">
                  No hay productos escaneados en esta transacción.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Ventas Suspendidas (RF-12) -->
        <div
          v-if="suspendedSales.length > 0"
          class="mt-4 p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-lg flex items-center justify-between"
        >
          <div class="flex items-center gap-2 text-amber-800 dark:text-amber-300 text-xs font-semibold">
            <PauseCircle class="w-4 h-4 text-amber-600" />

            <span>
              {{ suspendedSales.length }} venta(s) suspendida(s) en espera
            </span>
          </div>

          <button
            type="button"
            @click="isSuspendedModalOpen = true"
            class="text-xs bg-amber-600 hover:bg-amber-700 text-white px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 shadow-sm"
          >
            <PlayCircle class="w-4 h-4" />
            Ver ventas en espera
          </button>
        </div>

      </div>

      <!-- Columna Derecha: Panel de Cobro y Totales -->
      <div class="flex flex-col justify-between bg-white/95 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-lg shadow-slate-300/20 dark:shadow-none p-5">
        <div class="space-y-4">
          <h3 class="text-base font-bold text-slate-800 dark:text-slate-100 border-b border-slate-100 dark:border-slate-800 pb-2">
            Resumen de Cobro
          </h3>

          <div class="space-y-2 text-sm text-slate-600 dark:text-slate-400">
            <div class="flex justify-between">
              <span>Ítems totales:</span>
              <span class="font-bold text-slate-800 dark:text-slate-200">{{ cartItems.reduce((a, c) => a + c.cantidad, 0) }}</span>
            </div>
            <div class="flex justify-between">
              <span>Subtotal neto:</span>
              <span>BOB {{ subtotalNeto.toFixed(2) }}</span>
            </div>
            <div class="flex justify-between">
              <span>IVA (13% incluido):</span>
              <span>BOB {{ montoIva.toFixed(2) }}</span>
            </div>
          </div>

          <!-- Total Destacado -->
          <div class="bg-gradient-to-br from-teal-700 to-cyan-800 p-5 rounded-xl border border-teal-500/40 text-center shadow-lg shadow-teal-900/15">
            <span class="text-xs uppercase font-bold text-teal-100 tracking-wider">Total a cobrar</span>
            <div class="text-3xl font-black text-white mt-1">
              BOB {{ total.toFixed(2) }}
            </div>
          </div>
        </div>

        <!-- Botonera de Acción -->
        <div class="space-y-2.5 pt-4">
          <button
            @click="isPayModalOpen = true"
            :disabled="cartItems.length === 0"
            class="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold rounded-lg shadow-lg shadow-emerald-900/15 flex items-center justify-center gap-2 active:scale-98"
          >
            <Banknote class="w-5 h-5" /> Cobrar Transacción [F12]
          </button>

          <button
            @click="suspenderVenta"
            :disabled="cartItems.length === 0"
            class="w-full py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold text-xs rounded-xl flex items-center justify-center gap-2"
          >
            <PauseCircle class="w-4 h-4 text-amber-500" /> Suspender Venta [F4]
          </button>
        </div>
      </div>
    </div>

    <!-- Modal de Cobro y Factura Rápida (RF-10, KAN-346, KAN-364, KAN-367) -->
    <div v-if="isPayModalOpen" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div class="bg-white dark:bg-slate-900 w-full max-w-xl max-h-[92vh] overflow-y-auto rounded-2xl p-5 sm:p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-5">
        <div v-if="!isReceiptReady" class="space-y-4">
          <div class="flex justify-between items-center border-b border-slate-100 dark:border-slate-800 pb-3">
            <div>
              <h3 class="text-base font-bold text-slate-800 dark:text-white flex items-center gap-2">
                <Store class="w-4 h-4 text-emerald-600" /> Procesar Cobro y Facturación en Caja
              </h3>
              <p class="text-xs text-slate-500">Ingreso de datos tributarios antes de procesar el pago</p>
            </div>
            <button @click="isPayModalOpen = false" class="p-1 rounded-lg text-slate-400 hover:text-slate-700">
              <X class="w-4 h-4" />
            </button>
          </div>
          <p v-if="cobroError" role="alert" class="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700">{{ cobroError }}</p>

          <!-- Total a Pagar en Caja -->
          <div class="p-3 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded-xl flex justify-between items-center">
            <span class="text-xs font-semibold text-emerald-800 dark:text-emerald-300">Total a Cobrar:</span>
            <span class="text-xl font-black text-emerald-700 dark:text-emerald-200">BOB {{ total.toFixed(2) }}</span>
          </div>

          <!-- FORMULARIO FISCAL COMPONENTE (KAN-364) -->
          <div class="p-4 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700">
            <FiscalBillingForm
              v-model="fiscalData"
              context="pos"
              @validation-change="isFiscalValid = $event"
            />
          </div>
          
          <!-- Método de Pago -->
          <div class="flex items-center justify-between">
            <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300">Método de Pago:</label>
            <label class="flex items-center gap-2 text-xs font-bold text-slate-700 dark:text-slate-200 cursor-pointer select-none">
              <input type="checkbox" :checked="splitMode" @change="activarPagoDividido(($event.target as HTMLInputElement).checked)" class="w-4 h-4 accent-emerald-600" />
              Dividir pago (varios métodos)
            </label>
          </div>

          <SplitPaymentPanel
            v-if="splitMode"
            v-model="splitLegs"
            :total="total"
            @validity="isSplitValid = $event"
          />

          <div v-else>
            <div class="grid grid-cols-3 gap-2 sm:gap-3">
              <button
                type="button"
                @click="payMethod = 'efectivo'"
                :class="['p-3 rounded-xl border flex flex-col items-center gap-1 text-xs font-bold transition-all', payMethod === 'efectivo' ? 'border-emerald-600 bg-emerald-50 text-emerald-700 shadow-sm' : 'border-slate-200 dark:border-slate-700']"
              >
                <Banknote class="w-5 h-5" /> Efectivo
              </button>
              <button
                type="button"
                @click="payMethod = 'tarjeta'"
                :class="['p-3 rounded-xl border flex flex-col items-center gap-1 text-xs font-bold transition-all', payMethod === 'tarjeta' ? 'border-blue-600 bg-blue-50 text-blue-700 shadow-sm' : 'border-slate-200 dark:border-slate-700']"
              >
                <CreditCard class="w-5 h-5" /> Tarjeta POS
              </button>
              <button
                type="button"
                @click="payMethod = 'qr'"
                :class="['p-3 rounded-xl border flex flex-col items-center gap-1 text-xs font-bold transition-all', payMethod === 'qr' ? 'border-purple-600 bg-purple-50 text-purple-700 shadow-sm' : 'border-slate-200 dark:border-slate-700']"
              >
                <QrCode class="w-5 h-5" /> QR Simple
              </button>
            </div>
          </div>

          <!-- Monto Recibido y Cambio -->
          <div v-if="!splitMode && payMethod === 'efectivo'" class="space-y-3 bg-slate-50 dark:bg-slate-800 p-3.5 rounded-xl border border-slate-200 dark:border-slate-700">
            <div class="flex justify-between items-center">
              <label class="text-xs font-semibold">Monto Recibido en Efectivo (BOB):</label>
              <input
                v-model.number="cashGiven"
                type="number"
                min="0"
                step="1"
                class="w-32 text-right font-bold text-base p-1.5 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-emerald-500"
              />
            </div>
            <div class="flex justify-between items-center text-sm font-bold text-emerald-600 dark:text-emerald-400 border-t border-slate-200 dark:border-slate-700 pt-2">
              <span>Cambio a Entregar:</span>
              <span class="text-lg">BOB {{ changeDue.toFixed(2) }}</span>
            </div>
          </div>

          <p v-if="cobroError" class="p-2.5 rounded-lg bg-rose-50 text-rose-600 text-xs font-semibold border border-rose-200">
            {{ cobroError }}
          </p>

          <div class="flex justify-end gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
            <button @click="isPayModalOpen = false" class="px-4 py-2 text-xs text-slate-500 font-semibold hover:bg-slate-100 rounded-lg">Cancelar</button>
            <button
              @click="finalizarCobro"
              :disabled="isProcessingPayment || !cajaAbierta || (splitMode && !isSplitValid)"
              class="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-bold text-xs rounded-xl shadow-md flex items-center gap-2"
            >
              <FileText class="w-4 h-4" />
              <span>{{ isProcessingPayment ? 'Procesando cobro...' : 'Confirmar cobro' }}</span>
            </button>
          </div>
        </div>

        <div v-else-if="ticketEmitido" class="space-y-4">
          <div class="text-center">
            <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle v-if="ticketEmitido.factura_estado === 'autorizada'" class="h-6 w-6" />
              <AlertCircle v-else class="h-6 w-6" />
            </div>
            <h3 class="mt-2 text-lg font-bold text-slate-900 dark:text-white">
              {{ ticketEmitido.factura_estado === 'autorizada' ? 'Factura autorizada' : 'Venta cobrada; factura pendiente' }}
            </h3>
            <p class="text-xs text-slate-500">{{ ticketEmitido.factura_mensaje || 'Estado confirmado por el servicio de facturación.' }}</p>
          </div>
          <article id="pos-ticket-print" class="mx-auto max-h-[55vh] w-full max-w-[72mm] overflow-y-auto rounded-lg border border-slate-200 bg-white p-4 font-mono text-[10px] text-black shadow-sm">
            <header class="text-center">
              <h4 class="text-sm font-black">MAXICONECTA BOLIVIA</h4>
              <p>{{ sucursalNombre }}</p>
              <p>{{ ticketEmitido.factura_estado === 'autorizada' ? 'FACTURA ELECTRÓNICA' : 'COMPROBANTE DE VENTA' }}</p>
              <p v-if="ticketEmitido.duplicado" class="my-2 border-y-2 border-black py-1 text-base font-black">DUPLICADO</p>
              <p v-if="ticketEmitido.factura_estado === 'autorizada'">No. {{ ticketEmitido.numero_factura }}</p>
            </header>
            <div class="my-2 border-t border-dashed border-black"></div>
            <p>Orden: {{ ticketEmitido?.codigo_orden }}</p>
            <p>Fecha: {{ new Date().toLocaleString('es-BO') }}</p>
            <p>NIT/CI: {{ fiscalData.nit_ci || '0' }}</p>
            <p>Cliente: {{ fiscalData.razon_social || 'CONSUMIDOR FINAL' }}</p>
            <div class="my-2 border-t border-dashed border-black"></div>
            <div v-for="item in (ticketEmitido?.items || [])" :key="item.sku" class="mb-2">
              <p class="break-words font-bold">{{ item.nombre }}</p>
              <div class="flex justify-between gap-2">
                <span>{{ item.cantidad }} x {{ item.precio_unitario.toFixed(2) }}</span>
                <span>{{ item.total_linea.toFixed(2) }}</span>
              </div>
              <p class="text-[9px]">SKU: {{ item.sku }}</p>
            </div>
            <div class="my-2 border-t border-dashed border-black"></div>
            <div class="flex justify-between"><span>Subtotal neto</span><span>BOB {{ ticketEmitido?.subtotal_neto.toFixed(2) }}</span></div>
            <div class="flex justify-between"><span>IVA 13% incluido</span><span>BOB {{ ticketEmitido?.monto_iva.toFixed(2) }}</span></div>
            <div class="mt-1 flex justify-between text-xs font-black"><span>TOTAL</span><span>BOB {{ ticketEmitido?.total.toFixed(2) }}</span></div>
            <p class="mt-1">Pago: {{ ticketEmitido?.metodo_pago.toUpperCase() }}</p>
            <template v-if="ticketEmitido.desglose_pagos.length > 1">
              <p v-for="pago in ticketEmitido.desglose_pagos" :key="pago.transaccion_id || `${pago.metodo}-${pago.monto}`" class="pl-2">
                · {{ pago.metodo.toUpperCase() }}: BOB {{ Number(pago.monto).toFixed(2) }}
              </p>
            </template>
            <p v-if="ticketEmitido.cambio_total > 0" class="mt-1 font-bold">Cambio: BOB {{ Number(ticketEmitido.cambio_total).toFixed(2) }}</p>
            <div class="my-2 border-t border-dashed border-black"></div>
            <div v-if="ticketEmitido.factura_estado === 'autorizada' && ticketEmitido.cuf" class="space-y-2">
              <p class="break-all text-[8px]">CUF: {{ ticketEmitido.cuf }}</p>
              <div v-if="ticketEmitido.qr_code" class="mt-3 flex flex-col items-center text-center">
                <img :src="ticketEmitido.qr_code" alt="QR de verificación fiscal" class="h-36 w-36" />
                <p class="mt-1 text-[8px]">Verifica la factura con el QR del emisor</p>
              </div>
            </div>
            <div v-else class="rounded border border-amber-300 bg-amber-50 p-2 text-center text-[9px] font-bold text-amber-900">
              {{ ticketEmitido.factura_mensaje || 'Comprobante de venta. No es una factura fiscal.' }}
            </div>
          </article>
          <div class="flex flex-wrap justify-center gap-2">
            <button @click="imprimirTicket" class="inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2.5 text-xs font-bold text-white hover:bg-slate-700">
              <Printer class="h-4 w-4" /> {{ ticketEmitido.duplicado ? 'Reimprimir comprobante' : (ticketEmitido.factura_estado === 'autorizada' ? 'Imprimir factura' : 'Imprimir comprobante') }} · 80 mm
            </button>
            <button @click="resetPos" class="rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-blue-700">
              Nueva venta
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Consulta y reimpresión del turno actual (KAN-347) -->
    <div v-if="isRecentSalesModalOpen" class="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm">
      <section class="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900 sm:p-6">
        <header class="mb-5 flex items-start justify-between gap-4">
          <div>
            <h3 class="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-white"><Printer class="h-5 w-5 text-blue-600" /> Reimprimir comprobante</h3>
            <p class="mt-1 text-xs text-slate-500">Últimas 10 ventas de este turno. Cada solicitud queda registrada.</p>
          </div>
          <button type="button" @click="isRecentSalesModalOpen = false" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Cerrar"><X class="h-4 w-4" /></button>
        </header>
        <p v-if="reimpresionError" role="alert" class="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700">{{ reimpresionError }}</p>
        <div v-if="cargandoVentasRecientes" class="py-10 text-center text-sm text-slate-500">Cargando ventas del turno...</div>
        <div v-else-if="ventasRecientes.length" class="max-h-[55vh] space-y-2 overflow-y-auto">
          <article v-for="venta in ventasRecientes" :key="venta.orden_id" class="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p class="font-bold text-slate-900 dark:text-white">{{ venta.codigo_orden }}</p>
              <p class="mt-1 text-xs text-slate-500">{{ venta.created_at ? new Date(venta.created_at).toLocaleString('es-BO') : 'Fecha no disponible' }}<span v-if="venta.numero_factura"> · Factura {{ venta.numero_factura }}</span></p>
              <p class="mt-1 text-sm font-semibold text-emerald-700 dark:text-emerald-300">BOB {{ Number(venta.total).toFixed(2) }}</p>
            </div>
            <button type="button" @click="prepararReimpresion(venta)" :disabled="!!reimprimiendoOrdenId" class="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-60">
              <Printer class="h-4 w-4" /> {{ reimprimiendoOrdenId === venta.orden_id ? 'Preparando...' : 'Reimprimir' }}
            </button>
          </article>
        </div>
        <div v-else class="rounded-xl border border-dashed border-slate-300 py-10 text-center text-sm text-slate-500 dark:border-slate-700">Todavía no hay ventas registradas en este turno.</div>
        <footer class="mt-5 flex justify-end border-t border-slate-100 pt-4 dark:border-slate-800">
          <button type="button" @click="isRecentSalesModalOpen = false" class="rounded-lg px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">Cerrar</button>
        </footer>
      </section>
    </div>

    <!-- Modal de Ventas en Espera (KAN-331) -->
    <div
      v-if="isSuspendedModalOpen"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
    >
      <div
        class="bg-white dark:bg-slate-900 w-full max-w-2xl rounded-2xl p-6 shadow-2xl border border-slate-200 dark:border-slate-800"
      >
        <!-- Encabezado -->
        <div class="flex items-center justify-between mb-5">
          <div>
            <div class="flex items-center gap-2">
              <PauseCircle class="w-6 h-6 text-amber-500" />

              <h3 class="text-lg font-bold text-slate-900 dark:text-white">
                Ventas en espera
              </h3>
            </div>

            <p class="text-xs text-slate-500 mt-1">
              Selecciona una venta para recuperarla al carrito activo.
            </p>
          </div>

          <button
            type="button"
            @click="isSuspendedModalOpen = false"
            class="text-slate-400 hover:text-slate-700 dark:hover:text-white text-xl"
            aria-label="Cerrar"
          >
            ✕
          </button>
        </div>

        <!-- Lista de ventas -->
        <div
          v-if="suspendedSales.length > 0"
          class="space-y-3 max-h-80 overflow-y-auto"
        >
          <div
            v-for="(sale, idx) in suspendedSales"
            :key="sale.id"
            class="border border-slate-200 dark:border-slate-700 rounded-xl p-4 flex items-center justify-between gap-4"
          >
            <div>
              <p class="font-bold text-slate-900 dark:text-white">
                Ticket #{{ sale.id }}
              </p>

              <p class="text-xs text-slate-500 mt-1">
                Cliente: {{ sale.cliente_referencia }}
              </p>

              <p class="text-sm font-semibold text-amber-600 mt-2">
                BOB {{ Number(sale.subtotal).toFixed(2) }}
              </p>
            </div>

            <button
              type="button"
              @click="reanudarVenta(idx); isSuspendedModalOpen = false"
              class="bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-2"
            >
              <PlayCircle class="w-4 h-4" />
              Recuperar
            </button>
          </div>
        </div>

        <!-- Sin ventas -->
        <div
          v-else
          class="text-center py-10 text-slate-500"
        >
          <PauseCircle class="w-10 h-10 mx-auto mb-3 text-slate-300" />

          <p class="font-semibold">
            No hay ventas en espera.
          </p>

          <p class="text-xs mt-1">
            Las ventas suspendidas aparecerán aquí.
          </p>
        </div>

        <!-- Pie -->
        <div class="flex justify-end mt-5 pt-4 border-t border-slate-200 dark:border-slate-700">
          <button
            type="button"
            @click="isSuspendedModalOpen = false"
            class="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>

    <!-- Modal de Consulta Rápida de Stock Multi-Sucursal (RF-07 / Atajo F3) -->
    <QuickStockModal 
      :open="isQuickStockOpen" 
      @close="isQuickStockOpen = false"
      @select="onSelectProductFromStockModal"
    />

    <!-- Modales de Turno de Caja (RF-09) -->
    <CajaAperturaModal
      :open="isAperturaModalOpen"
      :sucursal-id="sucursalId"
      :sucursal-nombre="sucursalNombre"
      :cajero-nombre="cajeroNombre"
      :cajero-id="cajeroId"
      @close="isAperturaModalOpen = false"
      @opened="onCajaOpened"
    />

    <CajaMovimientoModal
      v-if="cajaId"
      :open="isMovimientoModalOpen"
      :caja-id="cajaId"
      @close="isMovimientoModalOpen = false"
      @movement-added="onMovementAdded"
    />

    <CajaArqueoCierreModal
      v-if="cajaId"
      :open="isArqueoModalOpen"
      :caja-id="cajaId"
      :cajero-nombre="cajeroNombre"
      :sucursal-nombre="sucursalNombre"
      @close="isArqueoModalOpen = false"
      @closed="onCajaClosed"
    />

    <!-- Modal Click & Collect (RF-11) -->
    <ClickAndCollectModal
      :is-open="isClickAndCollectModalOpen"
      :sucursal-nombre="sucursalNombre"
      :sucursal-id="sucursalId"
      :cajero-id="cajeroId"
      :cajero-nombre="cajeroNombre"
      @close="isClickAndCollectModalOpen = false"
    />
  </div>
</template>

<style>
@media print {
  @page {
    size: 80mm auto;
    margin: 4mm;
  }

  body * {
    visibility: hidden !important;
  }

  #pos-ticket-print,
  #pos-ticket-print * {
    visibility: visible !important;
  }

  #pos-ticket-print {
    position: absolute !important;
    left: 0 !important;
    top: 0 !important;
    display: block !important;
    width: 72mm !important;
    max-width: 72mm !important;
    max-height: none !important;
    overflow: visible !important;
    border: 0 !important;
    padding: 0 !important;
    background: white !important;
    box-shadow: none !important;
    color: black !important;
  }
}
</style>
