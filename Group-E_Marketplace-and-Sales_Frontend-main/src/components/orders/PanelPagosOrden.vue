<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { AlertTriangle, CheckCircle2, Clock3, CreditCard, History, Loader2, RefreshCw, RotateCcw, ShieldAlert, XCircle } from 'lucide-vue-next';
import { pagosApi } from '@/api/pagos';
import { bs, fechaHora } from '@/lib/imprimir';
import type { MetodoPagoOrden, PagoOrden, PagosOrdenResumen } from '@/types';

/**
 * KAN-54 — Panel de pagos de una orden (detalle de la orden y POS).
 * La orden queda apta para preparación solo cuando la suma de pagos aprobados iguala su total.
 */
const props = withDefaults(
  defineProps<{
    ordenId: string;
    /** El personal (cajero/administrador) puede registrar pagos; el resto solo consulta. */
    puedeRegistrar?: boolean;
    /** Muestra los botones de simulación de la pasarela (QA/demo). */
    mostrarSimulacion?: boolean;
  }>(),
  { puedeRegistrar: false, mostrarSimulacion: false }
);

const emit = defineEmits<{ (e: 'actualizado', resumen: PagosOrdenResumen): void }>();

const METODOS: { id: MetodoPagoOrden; etiqueta: string }[] = [
  { id: 'efectivo', etiqueta: 'Efectivo' },
  { id: 'tarjeta', etiqueta: 'Tarjeta' },
  { id: 'qr', etiqueta: 'QR' },
  { id: 'transferencia', etiqueta: 'Transferencia' },
  { id: 'pasarela', etiqueta: 'Pasarela online' }
];

const resumen = ref<PagosOrdenResumen | null>(null);
const cargando = ref(false);
const enviando = ref(false);
const error = ref('');
const aviso = ref('');
const reintentoDe = ref<string | null>(null);
const form = reactive<{ metodo: MetodoPagoOrden; monto: number | ''; recibido: number | '' }>({ metodo: 'efectivo', monto: '', recibido: '' });

const saldo = computed(() => Number(resumen.value?.saldo_pendiente ?? 0));
const total = computed(() => Number(resumen.value?.total ?? 0));
const aprobado = computed(() => Number(resumen.value?.total_aprobado ?? 0));
const pendiente = computed(() => Number(resumen.value?.total_pendiente ?? 0));
const porCubrir = computed(() => Math.max(Math.round((total.value - aprobado.value - pendiente.value) * 100) / 100, 0));
const pctAprobado = computed(() => (total.value > 0 ? Math.min((aprobado.value / total.value) * 100, 100) : 0));
const ordenPendiente = computed(() => resumen.value?.estado_orden === 'pendiente');
const cambio = computed(() => (form.metodo === 'efectivo' && form.recibido && form.monto ? Math.max(Number(form.recibido) - Number(form.monto), 0) : 0));

const ESTADO_PAGO: Record<string, { texto: string; clase: string }> = {
  pendiente: { texto: 'Pendiente', clase: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300' },
  aprobado: { texto: 'Aprobado', clase: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300' },
  rechazado: { texto: 'Rechazado', clase: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300' },
  reembolsado: { texto: 'Reembolsado', clase: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200' }
};

function msg(err: any, fallback: string): string {
  const d = err?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
}

async function cargar() {
  if (!props.ordenId) return;
  cargando.value = true;
  error.value = '';
  try {
    resumen.value = await pagosApi.pagosDeOrden(props.ordenId);
    if (!form.monto || Number(form.monto) > porCubrir.value) form.monto = porCubrir.value || '';
    emit('actualizado', resumen.value);
  } catch (err) {
    error.value = msg(err, 'No se pudieron cargar los pagos de la orden.');
  } finally {
    cargando.value = false;
  }
}

async function registrar() {
  error.value = '';
  aviso.value = '';
  const monto = Number(form.monto);
  if (!monto || monto <= 0) {
    error.value = 'Indica un monto mayor a 0.';
    return;
  }
  if (monto > porCubrir.value + 0.0001) {
    error.value = `El monto excede lo que falta cubrir (${bs(porCubrir.value)}).`;
    return;
  }
  if (form.metodo === 'efectivo' && form.recibido && Number(form.recibido) < monto) {
    error.value = 'El monto recibido es menor al monto del pago.';
    return;
  }
  enviando.value = true;
  try {
    const r = await pagosApi.registrarPagoOrden({
      orden_id: props.ordenId,
      metodo: form.metodo,
      monto,
      monto_recibido: form.metodo === 'efectivo' && form.recibido ? Number(form.recibido) : undefined,
      reintento_de: reintentoDe.value || undefined
    });
    aviso.value =
      r.pago.estado === 'aprobado'
        ? `Pago en efectivo registrado${Number(r.cambio) > 0 ? ` · cambio ${bs(r.cambio)}` : ''}.`
        : 'Pago registrado: queda pendiente hasta la confirmación de la pasarela.';
    reintentoDe.value = null;
    form.recibido = '';
    form.monto = '';
    await cargar();
  } catch (err) {
    error.value = msg(err, 'No se pudo registrar el pago.');
  } finally {
    enviando.value = false;
  }
}

function reintentar(p: PagoOrden) {
  reintentoDe.value = p.id;
  form.monto = Number(p.monto);
  form.metodo = p.metodo === 'efectivo' ? 'tarjeta' : 'efectivo';
  form.recibido = '';
  aviso.value = `Reintento del pago rechazado de ${bs(p.monto)}: elige otro medio y registra.`;
}

async function simular(p: PagoOrden, resultado: 'aprobado' | 'rechazado') {
  if (!p.transaccion_id) return;
  error.value = '';
  try {
    await pagosApi.simularWebhook(p.transaccion_id, resultado, resultado === 'rechazado' ? 'Fondos insuficientes (simulado)' : undefined);
    await cargar();
  } catch (err) {
    error.value = msg(err, 'No se pudo simular la respuesta de la pasarela.');
  }
}

const historialOrdenado = computed(() => [...(resumen.value?.historial ?? [])].reverse());
const etiquetaHist = (h: { tipo: string; estado_anterior?: string | null; estado_nuevo: string }) =>
  h.tipo === 'orden' ? `Orden → ${h.estado_nuevo}` : `${h.estado_anterior ? h.estado_anterior.replace('reembolso:', 'reembolso ') + ' → ' : ''}${h.estado_nuevo.replace('reembolso:', 'reembolso ')}`;

onMounted(cargar);
watch(() => props.ordenId, () => { resumen.value = null; form.monto = ''; cargar(); });
defineExpose({ cargar });
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900" data-testid="panel-pagos">
    <header class="mb-3 flex items-center justify-between gap-2">
      <h4 class="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-white"><CreditCard class="h-4 w-4 text-blue-600" /> Pagos de la orden</h4>
      <button type="button" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" @click="cargar">
        <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': cargando }" /> Actualizar
      </button>
    </header>

    <div v-if="cargando && !resumen" class="flex items-center justify-center gap-2 py-6 text-xs text-slate-400"><Loader2 class="h-4 w-4 animate-spin" /> Cargando pagos…</div>

    <template v-if="resumen">
      <!-- Estado y saldo -->
      <div class="mb-3 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
        <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span class="font-mono font-bold text-slate-700 dark:text-slate-200">{{ resumen.codigo_orden }}</span>
          <span
            v-if="resumen.apta_para_preparacion"
            class="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 font-bold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
            data-testid="orden-apta"
          ><CheckCircle2 class="h-3.5 w-3.5" /> {{ resumen.estado_orden === 'entregada' ? 'Pago completo · entregada' : 'Pago completo · apta para preparación' }}</span>
          <span v-else class="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 font-bold text-amber-800 dark:bg-amber-950/60 dark:text-amber-300" data-testid="orden-no-apta">
            <Clock3 class="h-3.5 w-3.5" /> Pendiente de pago
          </span>
        </div>
        <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"><div class="h-full bg-emerald-500 transition-all" :style="{ width: pctAprobado + '%' }" /></div>
        <div class="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
          <div><span class="block text-slate-500">Total</span><b class="font-mono">{{ bs(resumen.total) }}</b></div>
          <div><span class="block text-slate-500">Aprobado</span><b class="font-mono text-emerald-700 dark:text-emerald-300">{{ bs(resumen.total_aprobado) }}</b></div>
          <div><span class="block text-slate-500">Saldo</span><b class="font-mono" data-testid="saldo-pendiente">{{ bs(resumen.saldo_pendiente) }}</b></div>
        </div>
      </div>

      <!-- Lista de pagos -->
      <div v-if="resumen.pagos.length === 0" class="rounded-xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-400 dark:border-slate-700">Aún no hay pagos registrados.</div>
      <ul v-else class="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
        <li v-for="p in resumen.pagos" :key="p.id" class="flex flex-wrap items-center justify-between gap-2 p-3 text-xs" :data-testid="`pago-${p.estado}`">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-bold capitalize text-slate-800 dark:text-slate-100">{{ p.metodo }}</span>
              <span class="rounded-full px-2 py-0.5 text-[10px] font-bold" :class="ESTADO_PAGO[p.estado]?.clase">{{ ESTADO_PAGO[p.estado]?.texto || p.estado }}</span>
              <span v-if="p.intento > 1" class="text-[10px] text-slate-400">intento {{ p.intento }}</span>
            </div>
            <p class="mt-0.5 truncate font-mono text-[10px] text-slate-400">{{ p.transaccion_id }}</p>
            <p v-if="p.motivo_rechazo" class="mt-0.5 flex items-center gap-1 text-[11px] text-rose-600 dark:text-rose-400"><XCircle class="h-3 w-3" /> {{ p.motivo_rechazo }}</p>
            <p v-if="Number(p.monto_reembolsado) > 0" class="mt-0.5 text-[11px] text-slate-500">Reembolsado {{ bs(p.monto_reembolsado) }}</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="font-mono font-bold">{{ bs(p.monto) }}</span>
            <button v-if="puedeRegistrar && p.estado === 'rechazado' && ordenPendiente" type="button" class="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-2.5 py-1 font-bold text-white hover:bg-rose-500" data-testid="btn-reintentar" @click="reintentar(p)">
              <RotateCcw class="h-3 w-3" /> Reintentar
            </button>
            <template v-if="mostrarSimulacion && puedeRegistrar && p.estado === 'pendiente'">
              <button type="button" class="rounded-lg border border-emerald-300 px-2 py-1 font-semibold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300" title="Simula el aviso de la pasarela" data-testid="btn-sim-aprobar" @click="simular(p, 'aprobado')">Simular aprobado</button>
              <button type="button" class="rounded-lg border border-rose-300 px-2 py-1 font-semibold text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300" @click="simular(p, 'rechazado')">Simular rechazo</button>
            </template>
          </div>
        </li>
      </ul>

      <!-- Registrar pago -->
      <form v-if="puedeRegistrar && ordenPendiente" class="mt-3 space-y-2 rounded-xl border border-slate-200 p-3 dark:border-slate-800" @submit.prevent="registrar">
        <div class="flex items-center justify-between text-xs">
          <span class="font-bold text-slate-700 dark:text-slate-200">{{ reintentoDe ? 'Reintentar con otro medio' : 'Registrar pago' }}</span>
          <span class="text-slate-500">Falta cubrir <b class="font-mono">{{ bs(porCubrir) }}</b></span>
        </div>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <select v-model="form.metodo" class="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" data-testid="pago-metodo">
            <option v-for="m in METODOS" :key="m.id" :value="m.id">{{ m.etiqueta }}</option>
          </select>
          <input v-model.number="form.monto" type="number" step="0.01" min="0.01" placeholder="Monto Bs." class="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" data-testid="pago-monto" />
          <input v-if="form.metodo === 'efectivo'" v-model.number="form.recibido" type="number" step="0.01" min="0" placeholder="Recibido Bs. (opc.)" class="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
        </div>
        <p v-if="cambio > 0" class="text-xs text-slate-500">Cambio a entregar: <b class="font-mono">{{ bs(cambio) }}</b></p>
        <p v-if="form.metodo === 'efectivo'" class="text-[11px] text-slate-400">El pago en efectivo solo se registra con una caja abierta.</p>
        <button type="submit" :disabled="enviando || porCubrir <= 0" class="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-600 disabled:opacity-50" data-testid="btn-registrar-pago">
          <Loader2 v-if="enviando" class="h-3.5 w-3.5 animate-spin" /> {{ enviando ? 'Registrando…' : 'Registrar pago' }}
        </button>
      </form>

      <div v-if="aviso" class="mt-2 rounded-lg bg-emerald-50 p-2 text-xs text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300" role="status">{{ aviso }}</div>

      <!-- Historial -->
      <details class="mt-3 text-xs">
        <summary class="flex cursor-pointer items-center gap-1.5 font-bold text-slate-600 dark:text-slate-300"><History class="h-3.5 w-3.5" /> Historial de pagos ({{ resumen.historial.length }})</summary>
        <ul class="mt-2 space-y-1.5">
          <li v-for="(h, i) in historialOrdenado" :key="i" class="flex items-start justify-between gap-2 rounded-lg bg-slate-50 p-2 dark:bg-slate-800/50">
            <span><b class="capitalize">{{ h.metodo || 'orden' }}</b> · {{ etiquetaHist(h) }}<span v-if="h.motivo" class="text-slate-400"> — {{ h.motivo }}</span></span>
            <span class="shrink-0 text-[10px] text-slate-400">{{ fechaHora(h.created_at) }}</span>
          </li>
        </ul>
      </details>
    </template>

    <div v-if="error" class="mt-2 flex items-start gap-2 rounded-lg bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300" role="alert">
      <ShieldAlert v-if="!resumen" class="h-4 w-4 shrink-0" /><AlertTriangle v-else class="h-4 w-4 shrink-0" /><span>{{ error }}</span>
    </div>
  </section>
</template>
