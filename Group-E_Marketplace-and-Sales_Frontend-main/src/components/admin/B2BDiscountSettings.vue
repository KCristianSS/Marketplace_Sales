<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Plus, RefreshCw, Save, Trash2 } from 'lucide-vue-next';
import { errorB2B, guardarReglasB2B, obtenerReglasB2B, type ConfiguracionDescuentosB2B, type ReglasDescuentosB2B } from '@/api/cotizaciones';
import { confirmAction, notify } from '@/lib/feedback';

const props = defineProps<{ record: ReglasDescuentosB2B }>();
const emit = defineEmits<{ updated: [record: ReglasDescuentosB2B] }>();
const version = ref(props.record.version);
const draft = ref<ConfiguracionDescuentosB2B>({ habilitado: true, escalas: [] });
const original = ref('');
const saving = ref(false);
const loading = ref(false);
const error = ref('');
const dirty = computed(() => JSON.stringify(draft.value) !== original.value);
function apply(record: ReglasDescuentosB2B) {
  version.value = record.version;
  draft.value = JSON.parse(JSON.stringify(record.configuracion));
  original.value = JSON.stringify(draft.value);
}
apply(props.record);
watch(() => props.record.version, () => { if (!dirty.value) apply(props.record); });
async function reload() {
  if (dirty.value && !(await confirmAction('Se descartarán las escalas que todavía no guardaste.', { title: '¿Recargar descuentos?', confirmLabel: 'Descartar y recargar', danger: true }))) return;
  loading.value = true;
  error.value = '';
  try { const record = await obtenerReglasB2B(); apply(record); emit('updated', record); }
  catch (err) { error.value = errorB2B(err, 'No se pudieron cargar los descuentos.'); }
  finally { loading.value = false; }
}
async function save() {
  if (saving.value || !dirty.value) return;
  error.value = '';
  const sorted = [...draft.value.escalas].sort((a, b) => a.minimo_unidades - b.minimo_unidades);
  if (sorted.some(e => !Number.isInteger(e.minimo_unidades) || e.minimo_unidades < 1 || e.minimo_unidades > 10000000 || typeof e.descuento_porcentaje !== 'number' || !Number.isFinite(e.descuento_porcentaje) || e.descuento_porcentaje < 0 || e.descuento_porcentaje > 100)) {
    error.value = 'Usa cantidades enteras positivas y descuentos entre 0 y 100%.'; return;
  }
  if (new Set(sorted.map(e => e.minimo_unidades)).size !== sorted.length) { error.value = 'No repitas la cantidad mínima entre escalas.'; return; }
  if (sorted.some((e, i) => i > 0 && e.descuento_porcentaje < sorted[i - 1].descuento_porcentaje)) { error.value = 'El descuento no puede disminuir cuando aumenta la cantidad mínima.'; return; }
  saving.value = true;
  try {
    const record = await guardarReglasB2B(version.value, { habilitado: draft.value.habilitado, escalas: sorted });
    apply(record); emit('updated', record);
    notify.success('Descuentos guardados. Las nuevas cotizaciones utilizarán estas escalas.');
  } catch (err) { error.value = errorB2B(err, 'No se pudieron guardar los descuentos.'); }
  finally { saving.value = false; }
}
</script>

<template>
  <form class="space-y-4 rounded-2xl border border-indigo-200 bg-white p-5 dark:border-indigo-900 dark:bg-slate-900" aria-label="Configuración de descuentos B2B" @submit.prevent="save">
    <header class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="font-bold">Descuentos por volumen</h3><p class="mt-1 text-xs leading-5 text-slate-500">Se aplica la escala de mayor cantidad mínima que alcance el pedido. Las cotizaciones ya emitidas conservan sus precios.</p></div><button type="button" :disabled="saving || loading" class="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold disabled:opacity-40" @click="reload"><RefreshCw class="h-4 w-4" /> Recargar reglas</button></header>
    <fieldset :disabled="saving || loading" class="space-y-4">
      <label class="flex items-center gap-2 text-sm"><input v-model="draft.habilitado" type="checkbox" /> Aplicar descuentos por volumen</label>
      <div class="space-y-2"><div v-for="(tier, index) in draft.escalas" :key="index" class="grid grid-cols-[1fr_1fr_auto] items-end gap-3"><label class="text-xs font-semibold">Desde (unidades)<input v-model.number="tier.minimo_unidades" required type="number" min="1" max="10000000" step="1" :aria-label="`Cantidad mínima de escala ${index + 1}`" class="tier-input" /></label><label class="text-xs font-semibold">Descuento (%)<input v-model.number="tier.descuento_porcentaje" required type="number" min="0" max="100" step="0.01" :aria-label="`Descuento de escala ${index + 1}`" class="tier-input" /></label><button type="button" :aria-label="`Quitar escala ${index + 1}`" class="rounded-lg p-2 text-rose-600 hover:bg-rose-50" @click="draft.escalas.splice(index, 1)"><Trash2 class="h-4 w-4" /></button></div></div>
      <p v-if="!draft.escalas.length" class="text-sm text-slate-500">Sin escalas, las cotizaciones no tendrán descuento por volumen.</p>
      <button type="button" :disabled="draft.escalas.length >= 50" class="flex items-center gap-2 text-xs font-bold text-indigo-700 disabled:opacity-40 dark:text-indigo-300" @click="draft.escalas.push({ minimo_unidades: 1, descuento_porcentaje: 0 })"><Plus class="h-4 w-4" /> Agregar escala</button>
      <p v-if="!draft.habilitado" class="text-xs text-amber-700">Los descuentos están desactivados. Las escalas se conservarán para cuando vuelvas a activarlos.</p>
    </fieldset>
    <p v-if="error" role="alert" class="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{{ error }}</p>
    <div class="flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-slate-500">{{ dirty ? 'Tienes cambios sin guardar.' : 'Reglas al día.' }}</p><button type="submit" :disabled="!dirty || saving || loading" class="flex items-center gap-2 rounded-xl bg-indigo-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50"><Save class="h-4 w-4" /> {{ saving ? 'Guardando…' : 'Guardar descuentos' }}</button></div>
  </form>
</template>

<style scoped>
.tier-input { @apply mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950; }
</style>
