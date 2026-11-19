<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { Calculator, CheckCircle2, AlertTriangle, ShieldAlert, Printer, Loader2, X, EyeOff, Lock, Coins, Banknote } from 'lucide-vue-next';
import { arqueoCiegoApi } from '@/api/caja';
import { bs } from '@/lib/imprimir';
import { imprimirDocumento } from '@/lib/imprimir';
import { htmlReporteArqueo } from '@/lib/reportesCaja';
import type { ArqueoReporte } from '@/types';

/**
 * KAN-341 — Arqueo ciego. Esta pantalla NO consulta ni muestra el efectivo esperado ni los totales por método de pago:
 * el cajero solo declara cuántos billetes y monedas tiene. El cuadre se revela recién después de confirmar.
 */
const props = defineProps<{
  open: boolean;
  cajaId: string;
  cajeroNombre: string;
  sucursalNombre: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'closed', reporte: ArqueoReporte): void;
}>();

const BILLETES = [200, 100, 50, 20, 10];
const MONEDAS = [5, 2, 1, 0.5, 0.2, 0.1];

type Paso = 'declarar' | 'confirmar' | 'reporte';
const paso = ref<Paso>('declarar');
const cantidades = reactive<Record<string, number | ''>>({});
const observaciones = ref('');
const enviando = ref(false);
const errorMsg = ref('');
const yaCerrado = ref(false);
const reporte = ref<ArqueoReporte | null>(null);

const clave = (v: number) => v.toFixed(2);
const fmtDenom = (v: number) => (v >= 1 ? String(v) : v.toFixed(2).replace('.', ','));

function reiniciar() {
  [...BILLETES, ...MONEDAS].forEach((d) => (cantidades[clave(d)] = ''));
  observaciones.value = '';
  errorMsg.value = '';
  yaCerrado.value = false;
  reporte.value = null;
  paso.value = 'declarar';
}

watch(
  () => props.open,
  (abierto) => {
    if (abierto) reiniciar();
  },
  { immediate: true }
);

function cantidad(d: number): number {
  const n = Number(cantidades[clave(d)]);
  return Number.isInteger(n) && n > 0 ? n : 0;
}

const subtotal = (d: number) => Math.round(d * cantidad(d) * 100) / 100;
const totalBilletes = computed(() => BILLETES.reduce((s, d) => s + subtotal(d), 0));
const totalMonedas = computed(() => MONEDAS.reduce((s, d) => s + subtotal(d), 0));
const totalDeclarado = computed(() => Math.round((totalBilletes.value + totalMonedas.value) * 100) / 100);
const piezas = computed(() => [...BILLETES, ...MONEDAS].reduce((s, d) => s + cantidad(d), 0));

const invalidos = computed(() =>
  [...BILLETES, ...MONEDAS].filter((d) => {
    const raw = cantidades[clave(d)];
    if (raw === '' || raw === null || raw === undefined) return false;
    const n = Number(raw);
    return !Number.isInteger(n) || n < 0 || n > 100000;
  })
);

function irAConfirmar() {
  errorMsg.value = '';
  if (invalidos.value.length) {
    errorMsg.value = 'Las cantidades deben ser números enteros mayores o iguales a 0.';
    return;
  }
  paso.value = 'confirmar';
}

async function confirmar() {
  enviando.value = true;
  errorMsg.value = '';
  try {
    reporte.value = await arqueoCiegoApi(props.cajaId, {
      desglose: [...BILLETES, ...MONEDAS].map((d) => ({ denominacion: d, cantidad: cantidad(d) })),
      observaciones: observaciones.value.trim() || undefined
    });
    paso.value = 'reporte';
  } catch (err: any) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    if (status === 409) {
      yaCerrado.value = true;
      errorMsg.value = typeof detail === 'string' ? detail : 'El turno ya fue cerrado y no puede arquearse de nuevo.';
    } else {
      errorMsg.value = typeof detail === 'string' ? detail : 'No se pudo confirmar el arqueo. Inténtalo nuevamente.';
    }
    paso.value = 'declarar';
  } finally {
    enviando.value = false;
  }
}

function imprimir() {
  if (reporte.value) {
    imprimirDocumento(`Arqueo ${reporte.value.numero_reporte}`, htmlReporteArqueo(reporte.value, props.cajeroNombre, props.sucursalNombre));
  }
}

function finalizar() {
  if (reporte.value) emit('closed', reporte.value);
  else emit('close');
}

function cerrarPantalla() {
  if (enviando.value) return;
  if (paso.value === 'reporte') finalizar();
  else emit('close');
}

const resultadoTexto = computed(() => {
  const r = reporte.value;
  if (!r) return '';
  if (r.resultado === 'cuadrado') return 'Caja cuadrada';
  return r.resultado === 'sobrante' ? `Sobrante de ${bs(r.diferencia)}` : `Faltante de ${bs(Math.abs(Number(r.diferencia)))}`;
});
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm" data-testid="arqueo-ciego">
    <div class="relative w-full max-w-3xl max-h-[94vh] overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl flex flex-col">
      <!-- Encabezado -->
      <div class="px-6 py-4 bg-gradient-to-r from-slate-800 to-slate-900 text-white flex items-center justify-between shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center border border-white/20">
            <Calculator class="w-5 h-5 text-cyan-300" />
          </div>
          <div>
            <h3 class="text-base font-bold">Cierre de turno · Arqueo ciego</h3>
            <p class="text-xs text-slate-300">{{ cajeroNombre }} · {{ sucursalNombre }}</p>
          </div>
        </div>
        <button type="button" class="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10" title="Cerrar" @click="cerrarPantalla">
          <X class="w-5 h-5" />
        </button>
      </div>

      <div class="p-6 overflow-y-auto space-y-5">
        <!-- PASO 1: declarar -->
        <template v-if="paso === 'declarar'">
          <div class="flex items-start gap-3 p-3 rounded-xl bg-cyan-50 dark:bg-cyan-950/30 border border-cyan-200 dark:border-cyan-900 text-xs text-cyan-900 dark:text-cyan-200">
            <EyeOff class="w-4 h-4 mt-0.5 shrink-0" />
            <p>
              Cuenta el efectivo de tu gaveta y registra la <b>cantidad de cada denominación</b>. Por transparencia, el sistema no muestra el
              saldo esperado ni los totales por método de pago hasta que confirmes el arqueo.
            </p>
          </div>

          <div v-if="errorMsg" class="p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-xs text-red-700 dark:text-red-300 flex items-start gap-2" role="alert">
            <ShieldAlert class="w-4 h-4 shrink-0 mt-0.5" />
            <span>{{ errorMsg }}</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <section>
              <h4 class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-2">
                <Banknote class="w-4 h-4" /> Billetes
              </h4>
              <div class="space-y-2">
                <label v-for="d in BILLETES" :key="d" class="flex items-center gap-3 p-2 rounded-lg border border-slate-200 dark:border-slate-700">
                  <span class="w-20 text-sm font-bold text-slate-800 dark:text-slate-100">Bs. {{ fmtDenom(d) }}</span>
                  <span class="text-slate-400 text-xs">×</span>
                  <input v-model.number="cantidades[clave(d)]" type="number" min="0" step="1" inputmode="numeric" placeholder="0"
                    :aria-label="`Cantidad de billetes de ${d}`" :data-testid="`den-${clave(d)}`"
                    class="w-24 px-2 py-1.5 text-sm text-right font-mono bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-md focus:outline-none focus:border-cyan-500" />
                  <span class="ml-auto text-xs font-mono text-slate-500">{{ bs(subtotal(d)) }}</span>
                </label>
              </div>
            </section>
            <section>
              <h4 class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 mb-2">
                <Coins class="w-4 h-4" /> Monedas
              </h4>
              <div class="space-y-2">
                <label v-for="d in MONEDAS" :key="d" class="flex items-center gap-3 p-2 rounded-lg border border-slate-200 dark:border-slate-700">
                  <span class="w-20 text-sm font-bold text-slate-800 dark:text-slate-100">Bs. {{ fmtDenom(d) }}</span>
                  <span class="text-slate-400 text-xs">×</span>
                  <input v-model.number="cantidades[clave(d)]" type="number" min="0" step="1" inputmode="numeric" placeholder="0"
                    :aria-label="`Cantidad de monedas de ${d}`" :data-testid="`den-${clave(d)}`"
                    class="w-24 px-2 py-1.5 text-sm text-right font-mono bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-md focus:outline-none focus:border-cyan-500" />
                  <span class="ml-auto text-xs font-mono text-slate-500">{{ bs(subtotal(d)) }}</span>
                </label>
              </div>
            </section>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
            <div class="text-xs text-slate-500">{{ piezas }} piezas · billetes {{ bs(totalBilletes) }} · monedas {{ bs(totalMonedas) }}</div>
            <div class="text-right">
              <div class="text-[10px] uppercase tracking-wider text-slate-500">Total declarado</div>
              <div class="text-xl font-black font-mono text-slate-900 dark:text-white" data-testid="total-declarado">{{ bs(totalDeclarado) }}</div>
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">Observaciones (opcional)</label>
            <textarea v-model="observaciones" rows="2" maxlength="500" class="w-full px-3 py-2 text-sm bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg focus:outline-none focus:border-cyan-500" />
          </div>
        </template>

        <!-- PASO 2: confirmar -->
        <template v-else-if="paso === 'confirmar'">
          <div class="p-5 rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 space-y-3">
            <div class="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-bold text-sm"><Lock class="w-4 h-4" /> Confirmar y cerrar turno</div>
            <p class="text-sm text-slate-700 dark:text-slate-200">
              Declaras <b class="font-mono">{{ bs(totalDeclarado) }}</b> ({{ piezas }} piezas). Al confirmar, lo declarado queda
              <b>congelado</b>, el turno pasa a «cerrada» y <b>no podrá editarse ni arquearse otra vez</b>.
            </p>
          </div>
        </template>

        <!-- PASO 3: reporte -->
        <template v-else-if="paso === 'reporte' && reporte">
          <div
            class="p-4 rounded-xl border flex items-center gap-3"
            :class="reporte.resultado === 'cuadrado'
              ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-300 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
              : 'bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-300'"
            data-testid="resultado-arqueo"
          >
            <CheckCircle2 v-if="reporte.resultado === 'cuadrado'" class="w-6 h-6 shrink-0" />
            <AlertTriangle v-else class="w-6 h-6 shrink-0" />
            <div>
              <div class="font-bold">{{ resultadoTexto }}</div>
              <div class="text-xs opacity-80">Reporte {{ reporte.numero_reporte }} · turno cerrado<span v-if="reporte.con_diferencia"> «con diferencia» · Contabilidad notificada</span></div>
            </div>
          </div>
          <table class="w-full text-sm">
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr><td class="py-1.5 text-slate-500">Fondo inicial</td><td class="py-1.5 text-right font-mono">{{ bs(reporte.fondo_inicial) }}</td></tr>
              <tr><td class="py-1.5 text-slate-500">Ventas en efectivo</td><td class="py-1.5 text-right font-mono">{{ bs(reporte.ventas_efectivo) }}</td></tr>
              <tr><td class="py-1.5 text-slate-500">Entradas extraordinarias (+)</td><td class="py-1.5 text-right font-mono">{{ bs(reporte.entradas_extraordinarias) }}</td></tr>
              <tr><td class="py-1.5 text-slate-500">Retiros a bóveda (−)</td><td class="py-1.5 text-right font-mono">{{ bs(reporte.retiros_boveda) }}</td></tr>
              <tr class="font-bold"><td class="py-1.5">Total esperado</td><td class="py-1.5 text-right font-mono">{{ bs(reporte.total_esperado) }}</td></tr>
              <tr class="font-bold"><td class="py-1.5">Total declarado</td><td class="py-1.5 text-right font-mono">{{ bs(reporte.total_declarado) }}</td></tr>
              <tr class="font-black"><td class="py-1.5">Diferencia</td><td class="py-1.5 text-right font-mono" data-testid="diferencia">{{ bs(reporte.diferencia) }}</td></tr>
            </tbody>
          </table>
        </template>
      </div>

      <!-- Pie -->
      <div class="px-6 py-4 bg-slate-50 dark:bg-slate-800/80 border-t border-slate-200 dark:border-slate-700 flex flex-wrap justify-end gap-2 shrink-0">
        <template v-if="paso === 'declarar'">
          <button v-if="yaCerrado" type="button" class="px-4 py-2 text-xs font-bold bg-slate-800 text-white rounded-lg" @click="finalizar">Entendido</button>
          <template v-else>
            <button type="button" class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg" @click="emit('close')">Cancelar</button>
            <button type="button" data-testid="btn-continuar" class="px-4 py-2 text-xs font-bold bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg" @click="irAConfirmar">Continuar</button>
          </template>
        </template>
        <template v-else-if="paso === 'confirmar'">
          <button type="button" :disabled="enviando" class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg" @click="paso = 'declarar'">Revisar</button>
          <button type="button" data-testid="btn-confirmar" :disabled="enviando" class="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white rounded-lg disabled:opacity-50" @click="confirmar">
            <Loader2 v-if="enviando" class="w-3.5 h-3.5 animate-spin" />
            <Lock v-else class="w-3.5 h-3.5" />
            {{ enviando ? 'Confirmando...' : 'Confirmar y cerrar turno' }}
          </button>
        </template>
        <template v-else>
          <button type="button" class="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-100 rounded-lg" @click="imprimir">
            <Printer class="w-3.5 h-3.5" /> Imprimir reporte
          </button>
          <button type="button" class="px-4 py-2 text-xs font-bold bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg" @click="finalizar">Finalizar</button>
        </template>
      </div>
    </div>
  </div>
</template>
