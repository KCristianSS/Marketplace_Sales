<script setup lang="ts">
import { useNotificationMessage, notify } from '@/lib/feedback';
import { computed, onMounted, reactive, ref } from 'vue';
import { CalendarDays, ChevronLeft, ChevronRight, Download, FileText, Plus, Search, Trash2, Settings2, Building2 } from 'lucide-vue-next';
import { apiClient } from '@/api/client';
import { buscarClientesCorporativos, descargarCotizacionPdf, emitirCotizacion, listarCotizaciones, obtenerReglasB2B, errorB2B, type ReglasDescuentosB2B, type ClienteCorporativo, type CotizacionB2B } from '@/api/cotizaciones';
import CorporateCustomerModal from './CorporateCustomerModal.vue';
import B2BDiscountSettings from './B2BDiscountSettings.vue';
import type { Producto } from '@/types';

interface OpcionVariante { id: string; sku: string; nombre: string; precio: number; }
interface LineaFormulario { variante_id: string; cantidad: number; }
const clientes = ref<ClienteCorporativo[]>([]);
const productos = ref<Producto[]>([]);
const cotizaciones = ref<CotizacionB2B[]>([]);
const searchNit = ref('');
const showCompanyForm = ref(false);
const showDiscounts = ref(false);
const clientsSearched = ref(false);
const rules = ref<ReglasDescuentosB2B | null>(null);
const loadingRules = ref(false);
const rulesError = ref('');
let clientSearchSequence = 0;
const clienteSeleccionado = ref('');
const searchingClients = ref(false);
const loadingCatalog = ref(false);
const loadingQuotes = ref(false);
const saving = ref(false);
const downloadingId = ref('');
const error = ref('');
const success = useNotificationMessage<string>('success', '');
const page = ref(1);
const pages = ref(1);
const total = ref(0);
const vigenciaDias = ref<7 | 15 | 30>(15);
const lines = ref<LineaFormulario[]>([{ variante_id: '', cantidad: 1 }]);
const filters = reactive({ estado: '', cliente_id: '', fecha_desde: '', fecha_hasta: '' });
const variantes = computed<OpcionVariante[]>(() => productos.value.flatMap(product => (product.variantes || []).map(variant => ({
  id: variant.id,
  sku: variant.sku,
  nombre: `${product.nombre}${variant.nombre_variante ? ` · ${variant.nombre_variante}` : ''}`,
  precio: Number(variant.precio || 0)
}))));
const selectedCustomer = computed(() => clientes.value.find(client => client.id === clienteSeleccionado.value));
const totalUnidades = computed(() => lines.value.reduce((sum, line) => sum + Math.max(0, Number(line.cantidad) || 0), 0));
const discountPercent = computed(() => {
  const config = rules.value?.configuracion;
  if (!config?.habilitado) return 0;
  return [...config.escalas].sort((a, b) => b.minimo_unidades - a.minimo_unidades).find(tier => totalUnidades.value >= tier.minimo_unidades)?.descuento_porcentaje || 0;
});
const discountSummary = computed(() => !rules.value ? 'Cargando reglas…' : !rules.value.configuracion.habilitado ? 'Descuentos por volumen desactivados.' : !rules.value.configuracion.escalas.length ? 'Sin escalas de descuento configuradas.' : 'Escalas: ' + rules.value.configuracion.escalas.map(tier => `${tier.minimo_unidades} unidades → ${tier.descuento_porcentaje}%`).join(' · '));
const subtotalPreview = computed(() => lines.value.reduce((sum, line) => {
  const variant = variantes.value.find(item => item.id === line.variante_id);
  return sum + (variant?.precio || 0) * Math.max(0, Number(line.cantidad) || 0);
}, 0));
const totalPreview = computed(() => subtotalPreview.value * (1 - discountPercent.value / 100));

async function loadCatalog() {
  loadingCatalog.value = true;
  try {
    const { data } = await apiClient.get<Producto[]>('/api/v1/catalogo/productos', { params: { limit: 500 } });
    productos.value = data.filter(product => ['publicado', 'activo'].includes(String(product.estado).toLowerCase()));
    if (variantes.value.length) lines.value[0].variante_id ||= variantes.value[0].id;
  } catch (err: any) { error.value = err.response?.data?.detail || 'No se pudo cargar el catálogo.'; }
  finally { loadingCatalog.value = false; }
}

async function searchCorporateClients() {
  const current = ++clientSearchSequence;
  searchingClients.value = true;
  error.value = '';
  try {
    const result = await buscarClientesCorporativos(searchNit.value.trim());
    if (current !== clientSearchSequence) return;
    clientes.value = result;
    clientsSearched.value = true;
    if (result.length === 1) clienteSeleccionado.value = result[0].id;
    else if (!result.some(client => client.id === clienteSeleccionado.value)) clienteSeleccionado.value = '';
  } catch (err) { if (current === clientSearchSequence) error.value = errorB2B(err, 'No se pudieron buscar clientes corporativos.'); }
  finally { if (current === clientSearchSequence) searchingClients.value = false; }
}

async function loadRules() {
  loadingRules.value = true;
  rulesError.value = '';
  try { rules.value = await obtenerReglasB2B(); }
  catch (err) { rulesError.value = errorB2B(err, 'No se pudieron cargar los descuentos.'); }
  finally { loadingRules.value = false; }
}
function companyRegistered(client: ClienteCorporativo, created: boolean) {
  ++clientSearchSequence;
  searchingClients.value = false;
  clientes.value = [client, ...clientes.value.filter(item => item.id !== client.id)];
  clienteSeleccionado.value = client.id;
  searchNit.value = client.nit_ci;
  showCompanyForm.value = false;
  error.value = '';
  notify.success(created ? 'Empresa registrada y seleccionada para cotizar.' : 'La empresa ya estaba registrada. Quedó seleccionada para cotizar.');
}

function addLine() { lines.value.push({ variante_id: variantes.value[0]?.id || '', cantidad: 1 }); }
function removeLine(index: number) { if (lines.value.length > 1) lines.value.splice(index, 1); }

async function submitQuote() {
  error.value = '';
  success.value = '';
  if (!clienteSeleccionado.value) { error.value = 'Busca y selecciona un cliente corporativo.'; return; }
  if (!rules.value) { error.value = 'Carga las reglas de descuento antes de emitir la cotización.'; return; }
  if (!lines.value.length || lines.value.some(line => !line.variante_id || !Number.isInteger(Number(line.cantidad)) || Number(line.cantidad) < 1)) {
    error.value = 'Agrega productos y cantidades válidas para emitir la cotización.';
    return;
  }
  saving.value = true;
  try {
    const created = await emitirCotizacion({
      cliente_id: clienteSeleccionado.value,
      vigencia_dias: vigenciaDias.value,
      items: lines.value.map(line => ({ variante_id: line.variante_id, cantidad: Number(line.cantidad) })),
      configuracion_descuento_version: rules.value.version
    });
    success.value = `Cotización ${created.codigo_cotizacion} emitida para ${created.razon_social || created.nombre_cliente}.`;
    filters.cliente_id = created.cliente_id;
    filters.estado = '';
    page.value = 1;
    lines.value = [{ variante_id: variantes.value[0]?.id || '', cantidad: 1 }];
    await loadQuotes();
  } catch (err: any) { error.value = errorB2B(err, 'No se pudo emitir la cotización.'); if (err.response?.status === 409) await loadRules(); }
  finally { saving.value = false; }
}

async function loadQuotes() {
  loadingQuotes.value = true;
  error.value = '';
  try {
    const result = await listarCotizaciones({
      estado: filters.estado || undefined,
      cliente_id: filters.cliente_id || undefined,
      fecha_desde: filters.fecha_desde || undefined,
      fecha_hasta: filters.fecha_hasta || undefined,
      page: page.value,
      limit: 10
    });
    cotizaciones.value = result.items;
    total.value = result.total;
    pages.value = result.total_paginas;
    page.value = result.pagina;
  } catch (err: any) { error.value = err.response?.data?.detail || 'No se pudieron cargar las cotizaciones.'; }
  finally { loadingQuotes.value = false; }
}

function applyFilters() { page.value = 1; void loadQuotes(); }
function clearFilters() { filters.estado = ''; filters.cliente_id = ''; filters.fecha_desde = ''; filters.fecha_hasta = ''; applyFilters(); }

async function downloadPdf(quote: CotizacionB2B) {
  downloadingId.value = quote.id;
  error.value = '';
  try {
    const file = await descargarCotizacionPdf(quote.id);
    const url = URL.createObjectURL(file);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${quote.codigo_cotizacion}.pdf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (err: any) { error.value = err.response?.data?.detail || 'No se pudo descargar el PDF.'; }
  finally { downloadingId.value = ''; }
}

function money(value: number) { return new Intl.NumberFormat('es-BO', { style: 'currency', currency: 'BOB' }).format(Number(value || 0)); }
function dateLabel(value: string) { return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium' }).format(new Date(value)); }
function statusClass(state: string) {
  return ({
    emitida: 'bg-blue-50 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300',
    vencida: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    aprobada: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300',
    pendiente_aprobacion: 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
    rechazada: 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
    convertida: 'bg-purple-50 text-purple-800 dark:bg-purple-950/40 dark:text-purple-300'
  } as Record<string, string>)[state] || 'bg-slate-100 text-slate-700';
}
onMounted(() => { void loadCatalog(); void loadQuotes(); void loadRules(); });
</script>

<template>
  <section class="space-y-5">
    <div class="flex justify-end"><button type="button" :aria-expanded="showDiscounts" aria-controls="b2b-discount-settings" class="flex items-center gap-2 rounded-xl border border-indigo-200 px-3 py-2 text-xs font-bold text-indigo-800 hover:bg-indigo-50 dark:border-indigo-900 dark:text-indigo-300" @click="showDiscounts = !showDiscounts"><Settings2 class="h-4 w-4" /> {{ showDiscounts ? 'Ocultar configuración' : 'Configurar descuentos' }}</button></div>
    <B2BDiscountSettings v-if="rules" v-show="showDiscounts" id="b2b-discount-settings" :record="rules" @updated="rules = $event" />
    <p v-if="rulesError" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{{ rulesError }} <button type="button" :disabled="loadingRules" class="ml-2 font-bold underline" @click="loadRules">Reintentar</button></p>
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-6">
      <div class="flex items-start gap-3"><span class="rounded-xl bg-indigo-50 p-2.5 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"><FileText class="h-5 w-5" /></span><div><h2 class="text-lg font-extrabold text-slate-900 dark:text-white">Nueva cotización B2B</h2><p class="mt-1 text-sm text-slate-500">Emite proformas con precio por volumen y vigencia seleccionable.</p></div></div>
      <div class="mt-5 grid gap-4 border-t border-slate-100 pt-4 dark:border-slate-800 lg:grid-cols-2">
        <div class="space-y-2">
          <label for="quote-nit" class="block text-xs font-bold text-slate-700 dark:text-slate-300">Buscar empresa por NIT</label>
          <div class="flex gap-2"><input id="quote-nit" v-model="searchNit" class="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-white" placeholder="Ingresa el NIT" @keydown.enter.prevent="searchCorporateClients" /><button type="button" :disabled="searchingClients" class="inline-flex items-center gap-1.5 rounded-xl bg-indigo-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50" @click="searchCorporateClients"><Search class="h-3.5 w-3.5" />Buscar</button></div>
          <div class="flex flex-wrap items-center justify-between gap-2"><p class="text-[11px] text-slate-500">Busca un NIT o pulsa Buscar para ver las empresas registradas.</p><button type="button" class="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-700 dark:text-indigo-300" @click="showCompanyForm = true"><Building2 class="h-4 w-4" /> Registrar empresa</button></div>
          <p v-if="clientsSearched && !clientes.length && !searchingClients" class="text-xs text-slate-500">No encontramos una empresa con ese NIT. Puedes registrarla con el botón anterior.</p>
          <div v-if="clientes.length" class="max-h-40 space-y-1 overflow-auto rounded-xl border border-slate-200 p-2 dark:border-slate-700"><button v-for="client in clientes" :key="client.id" type="button" :class="['block w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800', clienteSeleccionado === client.id ? 'bg-indigo-50 dark:bg-indigo-950/40' : '']" @click="clienteSeleccionado = client.id"><strong>{{ client.razon_social || client.nombre_completo }}</strong><span class="ml-2 text-slate-500">NIT {{ client.nit_ci }}</span></button></div>
          <p v-if="selectedCustomer" class="text-xs font-semibold text-emerald-700 dark:text-emerald-300">Cliente: {{ selectedCustomer.razon_social || selectedCustomer.nombre_completo }} · NIT {{ selectedCustomer.nit_ci }}</p>
        </div>
        <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">Vigencia de la proforma<select v-model.number="vigenciaDias" class="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-white"><option :value="7">7 días</option><option :value="15">15 días</option><option :value="30">30 días</option></select></label>
      </div>
      <div class="mt-4 space-y-2">
        <div class="flex items-center justify-between"><h3 class="text-sm font-bold text-slate-800 dark:text-white">Productos</h3><button type="button" :disabled="loadingCatalog || !variantes.length" class="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200" @click="addLine"><Plus class="h-3.5 w-3.5" />Agregar línea</button></div>
        <div v-for="(line, index) in lines" :key="index" class="grid gap-2 rounded-xl border border-slate-100 p-3 dark:border-slate-800 sm:grid-cols-[1fr_120px_40px]">
          <select v-model="line.variante_id" :disabled="loadingCatalog" class="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950 dark:text-white"><option value="" disabled>{{ loadingCatalog ? 'Cargando productos…' : 'Selecciona producto' }}</option><option v-for="variant in variantes" :key="variant.id" :value="variant.id">{{ variant.nombre }} · {{ variant.sku }} · {{ money(variant.precio) }}</option></select>
          <input v-model.number="line.cantidad" type="number" min="1" max="100000" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950 dark:text-white" aria-label="Cantidad" />
          <button type="button" :disabled="lines.length === 1" class="flex items-center justify-center rounded-lg text-rose-600 hover:bg-rose-50 disabled:opacity-30 dark:hover:bg-rose-950/30" aria-label="Quitar línea" @click="removeLine(index)"><Trash2 class="h-4 w-4" /></button>
        </div>
        <div class="flex flex-wrap justify-end gap-x-5 gap-y-1 text-xs text-slate-500"><span>{{ totalUnidades }} unidades</span><span>Descuento por volumen: <strong>{{ rules ? `${discountPercent}%` : '—' }}</strong></span><span>Estimado: <strong class="text-slate-800 dark:text-white">{{ rules ? money(totalPreview) : '—' }}</strong></span></div>
        <p class="text-right text-[11px] text-slate-400">{{ discountSummary }} El precio final se calcula con la tarifa corporativa vigente.</p>
      </div>
      <div class="mt-4 flex justify-end"><button type="button" :disabled="saving || !variantes.length || !rules || loadingRules" class="rounded-xl bg-indigo-700 px-4 py-2.5 text-xs font-extrabold text-white hover:bg-indigo-800 disabled:opacity-50" @click="submitQuote">{{ saving ? 'Emitiendo…' : 'Emitir cotización' }}</button></div>
    </div>

    <p v-if="error" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200">{{ error }}</p>


    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><h2 class="text-lg font-extrabold text-slate-900 dark:text-white">Cotizaciones emitidas</h2><p class="mt-1 text-sm text-slate-500">Busca por estado, cliente o fecha de emisión y descarga la proforma.</p></div><button type="button" :disabled="loadingQuotes" class="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold dark:border-slate-700" @click="loadQuotes">Actualizar</button></div>
      <form class="mt-4 grid gap-2 border-t border-slate-100 pt-4 dark:border-slate-800 sm:grid-cols-2 lg:grid-cols-5" @submit.prevent="applyFilters">
        <select v-model="filters.estado" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950 dark:text-white"><option value="">Todos los estados</option><option value="emitida">Emitida</option><option value="vencida">Vencida</option><option value="aprobada">Aprobada</option><option value="pendiente_aprobacion">Pendiente de aprobación</option><option value="rechazada">Rechazada</option><option value="convertida">Convertida</option></select>
        <select v-model="filters.cliente_id" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950 dark:text-white"><option value="">Todos los clientes</option><option v-for="client in clientes" :key="client.id" :value="client.id">{{ client.razon_social || client.nombre_completo }} · {{ client.nit_ci }}</option></select>
        <label class="relative"><CalendarDays class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" /><input v-model="filters.fecha_desde" type="date" class="w-full rounded-lg border border-slate-200 bg-white py-2 pl-7 pr-2 text-xs dark:border-slate-700 dark:bg-slate-950 dark:text-white" aria-label="Fecha de emisión desde" /></label>
        <label class="relative"><CalendarDays class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" /><input v-model="filters.fecha_hasta" type="date" class="w-full rounded-lg border border-slate-200 bg-white py-2 pl-7 pr-2 text-xs dark:border-slate-700 dark:bg-slate-950 dark:text-white" aria-label="Fecha de emisión hasta" /></label>
        <div class="flex gap-2"><button type="submit" class="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-xs font-bold text-white dark:bg-slate-700">Filtrar</button><button type="button" class="rounded-lg px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" @click="clearFilters">Limpiar</button></div>
      </form>
      <div v-if="loadingQuotes" class="py-10 text-center text-sm text-slate-500">Cargando cotizaciones…</div>
      <div v-else-if="!cotizaciones.length" class="py-10 text-center text-sm text-slate-500">No hay cotizaciones para mostrar.</div>
      <div v-else class="mt-4 space-y-3">
        <article v-for="quote in cotizaciones" :key="quote.id" class="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
          <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><div class="flex flex-wrap items-center gap-2"><strong class="font-mono text-sm text-indigo-800 dark:text-indigo-300">{{ quote.codigo_cotizacion }}</strong><span :class="['rounded-full px-2.5 py-1 text-[11px] font-bold capitalize', statusClass(quote.estado)]">{{ quote.estado.replaceAll('_', ' ') }}</span></div><p class="mt-1 text-sm font-semibold text-slate-800 dark:text-white">{{ quote.razon_social || quote.nombre_cliente }} · NIT {{ quote.nit_ci }}</p><p class="mt-1 text-xs text-slate-500">Emitida {{ dateLabel(quote.created_at) }} · Vence {{ dateLabel(quote.vigencia_hasta) }} · {{ quote.vigencia_dias }} días</p></div><div class="flex items-center justify-between gap-4 sm:flex-col sm:items-end"><div class="text-right"><p class="text-xs text-slate-500">{{ quote.descuento_porcentaje }}% descuento · {{ money(quote.descuento_monto) }}</p><strong class="text-base text-slate-900 dark:text-white">{{ money(quote.total) }}</strong></div><button type="button" :disabled="downloadingId === quote.id" class="inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 px-3 py-2 text-xs font-bold text-indigo-800 disabled:opacity-50 dark:bg-indigo-950/40 dark:text-indigo-300" @click="downloadPdf(quote)"><Download class="h-3.5 w-3.5" />{{ downloadingId === quote.id ? 'Preparando…' : 'Descargar PDF' }}</button></div></div>
          <ul class="mt-3 space-y-1 border-t border-slate-100 pt-3 text-xs text-slate-600 dark:border-slate-800 dark:text-slate-300"><li v-for="item in quote.items" :key="item.variante_id">{{ item.cantidad }} × {{ item.nombre_producto }} ({{ item.sku }}) · {{ money(item.total_linea) }}</li></ul>
        </article>
        <div v-if="pages > 1" class="flex items-center justify-between pt-2"><button type="button" :disabled="page <= 1" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs disabled:opacity-40" @click="page--; loadQuotes()"><ChevronLeft class="h-4 w-4" />Anterior</button><span class="text-xs text-slate-500">Página {{ page }} de {{ pages }} · {{ total }} cotizaciones</span><button type="button" :disabled="page >= pages" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs disabled:opacity-40" @click="page++; loadQuotes()">Siguiente<ChevronRight class="h-4 w-4" /></button></div>
      </div>
    </div>
    <CorporateCustomerModal v-if="showCompanyForm" :initial-nit="searchNit" @close="showCompanyForm = false" @registered="companyRegistered" />
  </section>
</template>
