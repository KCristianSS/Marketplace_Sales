<script setup lang="ts">
import { useNotificationMessage } from '@/lib/feedback';
import { computed, onMounted, reactive, ref } from 'vue';
import { AlertTriangle, ArrowLeft, CheckCircle2, Loader2, Printer, RefreshCw, RotateCcw, Search, Undo2 } from 'lucide-vue-next';
import { obtenerHistorialOrdenes } from '@/api/ordenes';
import { pagosApi } from '@/api/pagos';
import { reembolsosApi } from '@/api/reembolsos';
import { bs, fechaHora, imprimirDocumento } from '@/lib/imprimir';
import { htmlComprobanteEgreso } from '@/lib/reportesCaja';
import type { EstadoReembolso, PagosOrdenResumen, Reembolso } from '@/types';

/** KAN-55 — Gestión de reembolsos totales o parciales de pagos aprobados (administrador). */

const ESTADOS: { id: '' | EstadoReembolso; etiqueta: string }[] = [
  { id: '', etiqueta: 'Todos' },
  { id: 'solicitado', etiqueta: 'Solicitado' },
  { id: 'procesando', etiqueta: 'Procesando' },
  { id: 'completado', etiqueta: 'Completado' },
  { id: 'fallido', etiqueta: 'Fallido' }
];
const CLASE_ESTADO: Record<string, string> = {
  solicitado: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  procesando: 'bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300',
  completado: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
  fallido: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300'
};

// ---------------------------------------------------------------- listado
const items = ref<Reembolso[]>([]);
const total = ref(0);
const pagina = ref(1);
const limite = 10;
const cargando = ref(false);
const errorLista = ref('');
const filtros = reactive<{ estado: '' | EstadoReembolso; orden_id: string }>({ estado: '', orden_id: '' });
const totalPaginas = computed(() => Math.max(Math.ceil(total.value / limite), 1));

async function cargar() {
  cargando.value = true;
  errorLista.value = '';
  try {
    const r = await reembolsosApi.listar({ estado: filtros.estado, orden_id: filtros.orden_id.trim() || undefined, page: pagina.value, limit: limite });
    items.value = r.items;
    total.value = r.total;
  } catch (err: any) {
    errorLista.value = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'No se pudo cargar el listado de reembolsos.';
  } finally {
    cargando.value = false;
  }
}
function filtrar() { pagina.value = 1; cargar(); }
function irA(p: number) { pagina.value = Math.min(Math.max(p, 1), totalPaginas.value); cargar(); }

// ---------------------------------------------------------------- solicitud
const codigoBusqueda = ref('');
const buscando = ref(false);
const ordenPagos = ref<PagosOrdenResumen | null>(null);
const errorSolicitud = ref('');
const exito = useNotificationMessage<string>('success', '');
const enviando = ref(false);
const pantallaConfirmacion = ref(false);
const comprobantes = ref<Reembolso[]>([]);
const comprobanteVisible = ref<Reembolso | null>(null);
const form = reactive<{ pagoId: string; monto: number | ''; motivo: string; simularFallo: boolean }>({ pagoId: '', monto: '', motivo: '', simularFallo: false });

const tramosReembolsables = computed(() => (ordenPagos.value?.pagos ?? []).filter((p) => p.metodo !== 'vale' && (p.estado === 'aprobado' || p.estado === 'reembolsado')));
const tieneVale = computed(() => (ordenPagos.value?.pagos ?? []).some(p => p.metodo === 'vale' && (p.estado === 'aprobado' || p.estado === 'reembolsado')));
const saldoOrden = computed(() => tramosReembolsables.value.reduce((s, p) => s + Number(p.saldo_reembolsable), 0));
const saldoSeleccion = computed(() => {
  if (!form.pagoId) return saldoOrden.value;
  return Number(tramosReembolsables.value.find((p) => p.id === form.pagoId)?.saldo_reembolsable ?? 0);
});

function mensaje(err: any, fallback: string) {
  const d = err?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return 'Revisa los datos: el motivo es obligatorio (mínimo 3 caracteres) y el monto debe ser mayor a 0.';
  return fallback;
}

async function buscarOrden() {
  errorSolicitud.value = '';
  exito.value = '';
  ordenPagos.value = null;
  const q = codigoBusqueda.value.trim();
  if (!q) return;
  buscando.value = true;
  try {
    const esUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(q);
    let ordenId = q;
    if (!esUuid) {
      const r = await obtenerHistorialOrdenes({ codigo_orden: q, limit: 1 } as any);
      if (!r.items.length) throw Object.assign(new Error('x'), { response: { data: { detail: 'No se encontró una orden con ese código.' } } });
      ordenId = r.items[0].id;
    }
    ordenPagos.value = await pagosApi.pagosDeOrden(ordenId);
    form.pagoId = '';
    form.monto = '';
    if (!tramosReembolsables.value.length) errorSolicitud.value = tieneVale.value ? 'Los pagos con vale no están disponibles para reembolso desde esta pantalla.' : 'La orden no tiene pagos aprobados para reembolsar.';
  } catch (err) {
    errorSolicitud.value = mensaje(err, 'No se pudo consultar la orden.');
  } finally {
    buscando.value = false;
  }
}

async function solicitar() {
  if (!ordenPagos.value) return;
  errorSolicitud.value = '';
  exito.value = '';
  if (form.motivo.trim().length < 3) { errorSolicitud.value = 'El motivo es obligatorio (mínimo 3 caracteres).'; return; }
  const monto = form.monto === '' ? undefined : Number(form.monto);
  if (monto !== undefined && (monto <= 0 || monto > saldoSeleccion.value + 0.0001)) {
    errorSolicitud.value = `El monto debe ser mayor a 0 y no exceder el saldo reembolsable (${bs(saldoSeleccion.value)}).`;
    return;
  }
  pantallaConfirmacion.value = true;
}

async function confirmarReembolso() {
  if (!ordenPagos.value || enviando.value) return;
  const monto = form.monto === '' ? undefined : Number(form.monto);
  enviando.value = true;
  try {
    const r = await reembolsosApi.solicitar({
      pago_id: form.pagoId || undefined,
      orden_id: form.pagoId ? undefined : ordenPagos.value.orden_id,
      monto,
      motivo: form.motivo.trim(),
      simular_fallo: false
    });
    comprobantes.value = r.reembolsos.filter(item => item.estado === 'completado');
    pantallaConfirmacion.value = false;
    comprobanteVisible.value = comprobantes.value[0] || null;
    exito.value = r.fallidos
      ? `${r.completados} completado(s) y ${r.fallidos} fallido(s). Revisa el historial para reintentar.`
      : `Reembolso registrado por ${bs(r.monto_total)}.`;
    form.monto = ''; form.motivo = ''; form.simularFallo = false;
    ordenPagos.value = await pagosApi.pagosDeOrden(ordenPagos.value.orden_id);
    await cargar();
  } catch (err) {
    errorSolicitud.value = mensaje(err, 'No se pudo solicitar el reembolso.');
  } finally {
    enviando.value = false;
  }
}

// ---------------------------------------------------------------- reintento / comprobante
const reintentando = ref<string | null>(null);
const errorFila = ref('');
async function reintentar(r: Reembolso) {
  reintentando.value = r.id;
  errorFila.value = '';
  try {
    await reembolsosApi.reintentar(r.id);
    await cargar();
  } catch (err) {
    errorFila.value = mensaje(err, 'No se pudo reintentar el reembolso.');
  } finally {
    reintentando.value = null;
  }
}
function imprimirEgreso(r: Reembolso) {
  imprimirDocumento(`Comprobante ${r.numero_comprobante}`, htmlComprobanteEgreso(r));
}

onMounted(cargar);
</script>

<template>
  <main class="mx-auto max-w-6xl space-y-6 p-4 sm:p-6" data-testid="reembolsos-view">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <router-link to="/admin" class="mb-1 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline dark:text-blue-300"><ArrowLeft class="h-3.5 w-3.5" /> Panel administrativo</router-link>
        <h1 class="flex items-center gap-2 text-xl font-extrabold text-slate-900 dark:text-white"><Undo2 class="h-5 w-5 text-rose-600" /> Reembolsos</h1>
        <p class="text-sm text-slate-500">Reintegra el dinero al cliente por el mismo medio de pago, con trazabilidad completa.</p>
      </div>
    </header>

    <!-- Solicitud -->
    <section class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h2 class="mb-3 text-sm font-bold text-slate-800 dark:text-white">Solicitar reembolso</h2>
      <form class="flex flex-col gap-2 sm:flex-row" @submit.prevent="buscarOrden">
        <input v-model="codigoBusqueda" type="text" placeholder="Código de la orden (ORD-…) o ID" data-testid="rb-buscar" class="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
        <button type="submit" :disabled="buscando" class="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white hover:bg-slate-700 disabled:opacity-50">
          <Loader2 v-if="buscando" class="h-3.5 w-3.5 animate-spin" /><Search v-else class="h-3.5 w-3.5" /> Buscar orden
        </button>
      </form>

      <div v-if="ordenPagos && tramosReembolsables.length" class="mt-4 space-y-3">
        <p v-if="tieneVale" class="text-xs text-amber-700">Los pagos con vale no están incluidos en el saldo reembolsable.</p>
        <div class="text-xs text-slate-500">Orden <b class="font-mono text-slate-800 dark:text-slate-100">{{ ordenPagos.codigo_orden }}</b> · total {{ bs(ordenPagos.total) }} · saldo reembolsable <b class="font-mono" data-testid="rb-saldo">{{ bs(saldoOrden) }}</b></div>
        <div class="grid gap-2 sm:grid-cols-2">
          <label class="flex cursor-pointer items-center justify-between gap-2 rounded-xl border p-3 text-xs" :class="form.pagoId === '' ? 'border-rose-400 bg-rose-50 dark:bg-rose-950/20' : 'border-slate-200 dark:border-slate-700'">
            <span class="flex items-center gap-2"><input v-model="form.pagoId" type="radio" value="" /> <b>Pagos disponibles</b> <span class="text-slate-500">(se reparte por tramo y medio)</span></span>
            <span class="font-mono">{{ bs(saldoOrden) }}</span>
          </label>
          <label v-for="p in tramosReembolsables" :key="p.id" class="flex cursor-pointer items-center justify-between gap-2 rounded-xl border p-3 text-xs" :class="form.pagoId === p.id ? 'border-rose-400 bg-rose-50 dark:bg-rose-950/20' : 'border-slate-200 dark:border-slate-700'">
            <span class="flex items-center gap-2"><input v-model="form.pagoId" type="radio" :value="p.id" :disabled="Number(p.saldo_reembolsable) <= 0" /> <b class="capitalize">{{ p.metodo }}</b> <span class="text-slate-500">pagado {{ bs(p.monto) }}</span></span>
            <span class="font-mono">{{ bs(p.saldo_reembolsable) }}</span>
          </label>
        </div>
        <div class="grid gap-2 sm:grid-cols-3">
          <input v-model.number="form.monto" type="number" step="0.01" min="0.01" :placeholder="`Monto (vacío = ${bs(saldoSeleccion)})`" data-testid="rb-monto" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          <input v-model="form.motivo" type="text" maxlength="255" placeholder="Motivo del reembolso *" data-testid="rb-motivo" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm sm:col-span-2 dark:border-slate-700 dark:bg-slate-950" />
        </div>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <span class="text-xs text-slate-500">En el siguiente paso podrás revisar los datos.</span>
          <button type="button" :disabled="enviando || saldoSeleccion <= 0" data-testid="rb-solicitar" class="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50" @click="solicitar">
            <Loader2 v-if="enviando" class="h-3.5 w-3.5 animate-spin" /> {{ enviando ? 'Procesando…' : 'Solicitar reembolso' }}
          </button>
        </div>
      </div>

      <p v-if="errorSolicitud" class="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300" role="alert"><AlertTriangle class="h-4 w-4 shrink-0" /> {{ errorSolicitud }}</p>

    </section>

    <!-- Listado -->
    <section class="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4 dark:border-slate-800">
        <h2 class="text-sm font-bold text-slate-800 dark:text-white">Historial de reembolsos <span class="font-normal text-slate-400">({{ total }})</span></h2>
        <div class="flex flex-wrap items-center gap-2">
          <select v-model="filtros.estado" class="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-950" data-testid="rb-filtro-estado" @change="filtrar">
            <option v-for="e in ESTADOS" :key="e.id" :value="e.id">{{ e.etiqueta }}</option>
          </select>
          <input v-model="filtros.orden_id" type="text" placeholder="ID de orden" class="w-44 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-950" @keyup.enter="filtrar" />
          <button type="button" class="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="Actualizar" @click="cargar"><RefreshCw class="h-4 w-4" :class="{ 'animate-spin': cargando }" /></button>
        </div>
      </div>
      <p v-if="errorLista" class="p-4 text-xs text-red-600">{{ errorLista }}</p>
      <p v-if="errorFila" class="px-4 pt-3 text-xs text-red-600" role="alert">{{ errorFila }}</p>
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-xs">
          <thead class="bg-slate-50 text-slate-500 dark:bg-slate-800/60"><tr><th class="px-4 py-2.5">Fecha</th><th class="px-4 py-2.5">Orden</th><th class="px-4 py-2.5">Medio</th><th class="px-4 py-2.5 text-right">Monto</th><th class="px-4 py-2.5">Estado</th><th class="px-4 py-2.5">Motivo</th><th class="px-4 py-2.5 text-right">Acciones</th></tr></thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-if="!cargando && !items.length"><td colspan="7" class="px-4 py-8 text-center text-slate-400">No hay reembolsos con esos filtros.</td></tr>
            <tr v-for="r in items" :key="r.id" :data-testid="`rb-fila-${r.estado}`">
              <td class="px-4 py-3 text-slate-500">{{ fechaHora(r.created_at) }}</td>
              <td class="px-4 py-3 font-mono font-bold text-emerald-800 dark:text-emerald-300">{{ r.codigo_orden || r.orden_id.slice(0, 8) }}</td>
              <td class="px-4 py-3 capitalize">{{ r.metodo }}</td>
              <td class="px-4 py-3 text-right font-mono font-bold">{{ bs(r.monto) }}</td>
              <td class="px-4 py-3">
                <span class="rounded-full px-2 py-0.5 text-[10px] font-bold" :class="CLASE_ESTADO[r.estado]">{{ r.estado }}</span>
                <span v-if="r.intento > 1" class="ml-1 text-[10px] text-slate-400">intento {{ r.intento }}</span>
                <p v-if="r.error" class="mt-1 max-w-xs text-[11px] text-rose-600 dark:text-rose-400">{{ r.error }}</p>
              </td>
              <td class="max-w-[200px] truncate px-4 py-3 text-slate-600 dark:text-slate-300" :title="r.motivo">{{ r.motivo }}</td>
              <td class="px-4 py-3 text-right">
                <button v-if="r.estado === 'fallido' && r.metodo !== 'vale'" type="button" :disabled="reintentando === r.id" data-testid="rb-reintentar" class="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-2.5 py-1 font-bold text-white hover:bg-rose-500 disabled:opacity-50" @click="reintentar(r)">
                  <Loader2 v-if="reintentando === r.id" class="h-3 w-3 animate-spin" /><RotateCcw v-else class="h-3 w-3" /> Reintentar
                </button>
                <button v-else-if="r.estado === 'completado'" type="button" class="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1 font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200" @click="comprobantes = [r]; comprobanteVisible = r">
                  <Printer class="h-3 w-3" /> Ver comprobante
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex items-center justify-between border-t border-slate-100 p-3 text-xs text-slate-500 dark:border-slate-800">
        <span>Página {{ pagina }} de {{ totalPaginas }}</span>
        <div class="flex gap-2"><button type="button" :disabled="pagina <= 1" class="rounded-lg border px-3 py-1 disabled:opacity-40" @click="irA(pagina - 1)">Anterior</button><button type="button" :disabled="pagina >= totalPaginas" class="rounded-lg border px-3 py-1 disabled:opacity-40" @click="irA(pagina + 1)">Siguiente</button></div>
      </div>
    </section>
    <div v-if="pantallaConfirmacion" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" role="dialog" aria-modal="true" aria-label="Confirmar reembolso">
      <div class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900">
        <p class="text-xs font-bold uppercase tracking-wide text-rose-600">Reembolso</p>
        <h2 class="mt-2 text-xl font-bold text-slate-900 dark:text-white">Confirmar reembolso</h2>
        <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">Orden {{ ordenPagos?.codigo_orden }} · {{ form.pagoId ? tramosReembolsables.find(p => p.id === form.pagoId)?.metodo : 'Pagos disponibles' }}</p>
        <div class="my-5 rounded-xl bg-slate-50 p-4 dark:bg-slate-800"><p class="text-xs text-slate-500">Monto del reembolso</p><p class="mt-1 text-2xl font-bold text-slate-900 dark:text-white">{{ bs(form.monto === '' ? saldoSeleccion : form.monto) }}</p><p class="mt-2 text-xs text-slate-500">{{ form.motivo }}</p></div>
        <p class="text-xs text-slate-500">Se solicitará el reembolso por los medios seleccionados.</p>
        <p v-if="errorSolicitud" class="mt-3 text-xs text-red-600" role="alert">{{ errorSolicitud }}</p>
        <div class="mt-5 flex justify-end gap-2"><button type="button" :disabled="enviando" class="rounded-lg border px-4 py-2 text-sm" @click="pantallaConfirmacion = false">Volver</button><button type="button" :disabled="enviando" class="rounded-lg bg-rose-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50" @click="confirmarReembolso">{{ enviando ? 'Procesando…' : 'Confirmar reembolso' }}</button></div>
      </div>
    </div>
    <div v-if="comprobanteVisible" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" role="dialog" aria-modal="true" aria-label="Comprobante de reembolso">
      <div class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900">
        <p class="text-xs font-bold uppercase tracking-wide text-emerald-700">Comprobante</p>
        <h2 class="mt-2 text-xl font-bold text-slate-900 dark:text-white">Reembolso registrado</h2>
        <div v-if="comprobantes.length > 1" class="mt-3 flex flex-wrap gap-2"><button v-for="c in comprobantes" :key="c.id" type="button" class="rounded-lg border px-2 py-1 text-xs" @click="comprobanteVisible = c">{{ c.metodo }} · {{ bs(c.monto) }}</button></div>
        <dl class="mt-5 space-y-3 rounded-xl bg-slate-50 p-4 text-sm dark:bg-slate-800"><div class="flex justify-between gap-4"><dt>Número</dt><dd class="font-mono">{{ comprobanteVisible.numero_comprobante || comprobanteVisible.id }}</dd></div><div class="flex justify-between gap-4"><dt>Orden</dt><dd>{{ comprobanteVisible.codigo_orden || comprobanteVisible.orden_id }}</dd></div><div class="flex justify-between gap-4"><dt>Medio</dt><dd class="capitalize">{{ comprobanteVisible.metodo }}</dd></div><div class="flex justify-between gap-4"><dt>Monto</dt><dd class="font-bold">{{ bs(comprobanteVisible.monto) }}</dd></div><div class="flex justify-between gap-4"><dt>Motivo</dt><dd class="text-right">{{ comprobanteVisible.motivo }}</dd></div></dl>
        <div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded-lg border px-4 py-2 text-sm" @click="comprobanteVisible = null">Cerrar</button><button type="button" class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-bold text-white" @click="imprimirEgreso(comprobanteVisible)">Imprimir</button></div>
      </div>
    </div>
  </main>
</template>
