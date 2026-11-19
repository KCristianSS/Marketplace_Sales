<script setup lang="ts">
import { confirmAction, useNotificationMessage } from '@/lib/feedback';
import { computed, onMounted, ref } from 'vue';
import { Truck, Plus, Pencil, Save, RefreshCw, X } from 'lucide-vue-next';
import ShippingTracePanel from '@/components/orders/ShippingTracePanel.vue';
import {
  obtenerConfiguracionEnvios, guardarConfiguracionEnvios, mensajeErrorEnvios,
  type ConfiguracionEnvios, type RegistroEnvios, type ZonaEnvio,
} from '@/api/envios';

const registro = ref<RegistroEnvios | null>(null);
const config = ref<ConfiguracionEnvios | null>(null);
const original = ref('');
const cargando = ref(false);
const guardando = ref(false);
const error = ref('');
const exito = useNotificationMessage<string>('success', '');
const zona = ref<ZonaEnvio | null>(null);
const errorZona = ref('');
const busqueda = ref('');
const mostrarTrazabilidad = ref(false);
const hayCambios = computed(() => !!config.value && JSON.stringify(config.value) !== original.value);
const ciudades = computed(() => [...new Set(config.value?.zonas.map(z => z.ciudad) || [])].sort());
const zonasFiltradas = computed(() => config.value?.zonas.filter(z =>
  `${z.ciudad} ${z.nombre}`.toLocaleLowerCase().includes(busqueda.value.trim().toLocaleLowerCase())) || []);

function aplicar(datos: RegistroEnvios) {
  registro.value = datos;
  config.value = JSON.parse(JSON.stringify(datos.configuracion));
  original.value = JSON.stringify(config.value);
}

async function cargar() {
  if (hayCambios.value && !(await confirmAction('Se perderán los cambios de envíos que todavía no guardaste.', { title: '¿Recargar los envíos?', confirmLabel: 'Descartar y recargar', danger: true }))) return;
  cargando.value = true;
  error.value = '';
  exito.value = '';
  try {
    aplicar(await obtenerConfiguracionEnvios());
    zona.value = null;
  } catch (err) {
    error.value = mensajeErrorEnvios(err, 'No pudimos cargar la configuración de envíos.');
  } finally {
    cargando.value = false;
  }
}

async function guardar() {
  if (!registro.value || !config.value || zona.value) return;
  guardando.value = true;
  error.value = '';
  exito.value = '';
  try {
    aplicar(await guardarConfiguracionEnvios(registro.value.version, config.value));
    exito.value = 'Configuración guardada. Las nuevas cotizaciones ya utilizan estas reglas.';
  } catch (err) {
    error.value = mensajeErrorEnvios(err, 'No pudimos guardar. Tus cambios siguen disponibles para reintentar.');
  } finally {
    guardando.value = false;
  }
}

function editarZona(actual?: ZonaEnvio) {
  errorZona.value = '';
  zona.value = actual ? { ...actual } : {
    id: crypto.randomUUID(), ciudad: '', nombre: '', tarifa_base: 0, activa: true,
    estandar_habilitado: true, express_habilitado: false,
    plazo_estandar: 'Entrega en 24 a 48 horas hábiles', plazo_express: 'Entrega en menos de 4 horas hábiles',
  };
}

function aplicarZona() {
  if (!zona.value || !config.value) return;
  const nueva = { ...zona.value, ciudad: zona.value.ciudad.trim(), nombre: zona.value.nombre.trim(),
    plazo_estandar: zona.value.plazo_estandar.trim(), plazo_express: zona.value.plazo_express.trim() };
  if (config.value.zonas.some(z => z.id !== nueva.id && z.ciudad.toLocaleLowerCase() === nueva.ciudad.toLocaleLowerCase()
    && z.nombre.toLocaleLowerCase() === nueva.nombre.toLocaleLowerCase())) {
    errorZona.value = 'Ya existe una zona con ese nombre en esta ciudad.';
    return;
  }
  if (nueva.activa && !nueva.estandar_habilitado && !nueva.express_habilitado) {
    errorZona.value = 'Habilita al menos una modalidad o desactiva la zona.';
    return;
  }
  const indice = config.value.zonas.findIndex(z => z.id === nueva.id);
  if (indice >= 0) config.value.zonas[indice] = nueva;
  else config.value.zonas.push(nueva);
  zona.value = null;
  exito.value = '';
}

onMounted(cargar);
</script>

<template>
  <section class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Truck class="w-6 h-6 text-blue-600" /> Envíos y cobertura</h2>
        <p class="text-sm text-slate-500 mt-1">Configura los destinos, precios y plazos que se ofrecen en el checkout.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" :aria-expanded="mostrarTrazabilidad" aria-controls="shipping-trace" @click="mostrarTrazabilidad = !mostrarTrazabilidad" class="px-3 py-2 rounded-lg border border-blue-200 text-sm font-semibold text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-slate-800">{{ mostrarTrazabilidad ? 'Ocultar trazabilidad' : 'Ver trazabilidad' }}</button>
        <button type="button" :disabled="cargando || guardando" @click="cargar" class="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm disabled:opacity-50"><RefreshCw class="w-4 h-4" /> Recargar</button>
      </div>
    </div>
    <div v-if="mostrarTrazabilidad" id="shipping-trace"><ShippingTracePanel /></div>
    <p v-if="cargando" role="status" class="text-sm text-slate-500">Cargando configuración…</p>
    <p v-if="error" role="alert" class="p-3 rounded-xl bg-rose-50 text-rose-700 text-sm">{{ error }}</p>

    <p v-if="registro?.almacenamiento === 'memoria'" class="p-3 rounded-xl bg-amber-50 text-amber-800 text-sm">Modo local: la configuración se guarda en memoria y se pierde al reiniciar el servicio.</p>

    <form v-if="config" @submit.prevent="guardar" class="space-y-5">
      <fieldset :disabled="guardando || cargando" class="space-y-5">
        <div class="p-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl space-y-4">
          <h3 class="font-bold">Reglas generales</h3>
          <label class="flex items-center gap-2 text-sm"><input v-model="config.envio_gratis_habilitado" type="checkbox" /> Ofrecer envío gratis por monto de compra</label>
          <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <label class="text-sm space-y-1"><span>Monto mínimo para envío gratis (BOB)</span><input v-model.number="config.umbral_envio_gratis" :disabled="!config.envio_gratis_habilitado" required type="number" min="0" max="1000000" step="0.01" class="shipping-input" /></label>
            <label class="text-sm space-y-1"><span>Recargo express (BOB)</span><input v-model.number="config.recargo_express" required type="number" min="0" max="1000000" step="0.01" class="shipping-input" /></label>
            <label class="text-sm space-y-1"><span>Peso incluido en la tarifa (kg)</span><input v-model.number="config.peso_incluido_kg" required type="number" min="0" max="100000" step="0.001" class="shipping-input" /></label>
            <label class="text-sm space-y-1"><span>Recargo por kg adicional (BOB)</span><input v-model.number="config.recargo_por_kg" required type="number" min="0" max="1000000" step="0.01" class="shipping-input" /></label>
            <label class="text-sm space-y-1"><span>Peso estimado por unidad (kg)</span><input v-model.number="config.peso_estimado_por_unidad_kg" required type="number" min="0.001" max="100000" step="0.001" class="shipping-input" /></label>
          </div>
          <p class="text-xs text-slate-500">El mínimo de envío gratis se evalúa después del cupón y antes de puntos. La bonificación cubre también los recargos. El peso por unidad es una estimación mientras los productos no tengan peso registrado.</p>
        </div>

        <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden">
          <div class="p-4 flex flex-wrap items-center justify-between gap-3">
            <h3 class="font-bold">Zonas de entrega ({{ config.zonas.length }})</h3>
            <div class="flex flex-wrap gap-2">
              <input v-model="busqueda" aria-label="Buscar ciudad o zona" placeholder="Buscar ciudad o zona" class="shipping-input !w-auto" />
              <button type="button" @click="editarZona()" :disabled="!!zona" class="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm flex items-center gap-1 disabled:opacity-50"><Plus class="w-4 h-4" /> Agregar zona</button>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
              <thead class="bg-slate-50 dark:bg-slate-800 text-xs text-slate-500"><tr><th class="p-3">Ciudad y zona</th><th class="p-3">Tarifa base</th><th class="p-3">Modalidades y plazos</th><th class="p-3">Cobertura</th><th class="p-3">Acción</th></tr></thead>
              <tbody>
                <tr v-for="item in zonasFiltradas" :key="item.id" class="border-t border-slate-100 dark:border-slate-800">
                  <td class="p-3"><span class="font-semibold">{{ item.ciudad }}</span><br /><span class="text-slate-500">{{ item.nombre }}</span></td>
                  <td class="p-3 whitespace-nowrap">BOB {{ item.tarifa_base.toFixed(2) }}</td>
                  <td class="p-3 text-xs"><p v-if="item.estandar_habilitado">Estándar: {{ item.plazo_estandar }}</p><p v-if="item.express_habilitado">Express: {{ item.plazo_express }}</p></td>
                  <td class="p-3"><span :class="item.activa ? 'text-emerald-600' : 'text-slate-500'">{{ item.activa ? 'Activa' : 'Desactivada' }}</span></td>
                  <td class="p-3"><button type="button" @click="editarZona(item)" :disabled="!!zona" :aria-label="`Editar ${item.nombre}, ${item.ciudad}`" class="text-blue-600 flex gap-1 items-center disabled:opacity-50"><Pencil class="w-4 h-4" /> Editar</button></td>
                </tr>
                <tr v-if="!zonasFiltradas.length"><td colspan="5" class="p-6 text-center text-slate-500">No hay zonas que coincidan.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <p class="text-xs text-slate-500">{{ hayCambios ? 'Tienes cambios sin guardar.' : 'Configuración al día.' }} Las cotizaciones emitidas conservan su precio hasta vencer.</p>
          <button type="submit" :disabled="!hayCambios || !!zona || guardando" class="px-4 py-2.5 rounded-xl bg-blue-600 text-white font-semibold flex gap-2 items-center disabled:opacity-50"><Save class="w-4 h-4" /> {{ guardando ? 'Guardando…' : 'Guardar configuración' }}</button>
        </div>
      </fieldset>
    </form>

    <div v-if="zona" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" @keydown.esc="zona = null">
      <form @submit.prevent="aplicarZona" role="dialog" aria-modal="true" aria-labelledby="shipping-zone-title" class="w-full max-w-xl max-h-[90vh] overflow-y-auto bg-white dark:bg-slate-900 p-6 rounded-2xl space-y-4">
        <div class="flex justify-between items-center"><h3 id="shipping-zone-title" class="text-lg font-bold">Zona de entrega</h3><button type="button" aria-label="Cerrar edición" @click="zona = null"><X class="w-5 h-5" /></button></div>
        <p v-if="errorZona" role="alert" class="text-sm text-rose-600">{{ errorZona }}</p>
        <div class="grid sm:grid-cols-2 gap-4">
          <label class="text-sm">Ciudad<input v-model="zona.ciudad" list="shipping-cities" required minlength="2" maxlength="100" class="shipping-input" /><datalist id="shipping-cities"><option v-for="ciudad in ciudades" :key="ciudad" :value="ciudad" /></datalist></label>
          <label class="text-sm">Nombre de la zona<input v-model="zona.nombre" required minlength="2" maxlength="150" class="shipping-input" /></label>
          <label class="text-sm">Tarifa base (BOB)<input v-model.number="zona.tarifa_base" required type="number" min="0" max="1000000" step="0.01" class="shipping-input" /></label>
          <label class="flex items-center gap-2 text-sm"><input v-model="zona.activa" type="checkbox" /> Zona con cobertura activa</label>
        </div>
        <label class="flex items-center gap-2 text-sm"><input v-model="zona.estandar_habilitado" type="checkbox" /> Habilitar estándar</label>
        <label class="block text-sm">Plazo estándar<input v-model="zona.plazo_estandar" required minlength="3" maxlength="160" class="shipping-input" /></label>
        <label class="flex items-center gap-2 text-sm"><input v-model="zona.express_habilitado" type="checkbox" /> Habilitar express</label>
        <label class="block text-sm">Plazo express<input v-model="zona.plazo_express" required minlength="3" maxlength="160" class="shipping-input" /></label>
        <p class="text-xs text-slate-500">Express suma el recargo de las reglas generales. Desactivar una zona la retira de los destinos disponibles para nuevas cotizaciones.</p>
        <div class="flex justify-end gap-3"><button type="button" @click="zona = null" class="px-3 py-2 border rounded-lg">Cancelar</button><button type="submit" class="px-3 py-2 rounded-lg bg-blue-600 text-white">Aplicar a la configuración</button></div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.shipping-input { @apply block w-full mt-1 px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white; }
</style>
