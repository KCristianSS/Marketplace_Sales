<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import {
  Truck,
  Store,
  MapPin,
  CheckCircle2,
  Clock,
  Phone,
  Info,
  Zap,
  ShieldCheck,
  Navigation,
  ChevronRight,
  Building2,
  RefreshCw
} from 'lucide-vue-next';
import { apiClient } from '@/api/client';
import { obtenerOpcionesEnvio, mensajeErrorEnvios, type OpcionesEnvio } from '@/api/envios';
import type {
  TipoDespacho,
  SucursalRetiro,
  CalculoFleteResponse,
  SeleccionEntregaData
} from '@/types';

const props = defineProps<{
  subtotal: number;
  modelValue?: SeleccionEntregaData;
  reservaId?: string | null;
  puntosCanjeados?: number;
  cupon?: string | null;
  bloqueado?: boolean;
  initialData?: Partial<SeleccionEntregaData>;
  direccionGuardada?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', data: SeleccionEntregaData): void;
  (e: 'validation-change', isValid: boolean): void;
}>();

// Estado de modalidad
const initialDeliveryData = props.modelValue || props.initialData;
const tipoDespacho = ref<TipoDespacho>(initialDeliveryData?.tipo_despacho || 'domicilio');

// Estado para Envío a Domicilio
const ciudadDomicilio = ref(initialDeliveryData?.ciudad || '');
const zonaDomicilio = ref(initialDeliveryData?.zona || '');
const direccionExacta = ref(initialDeliveryData?.direccion_exacta || '');
const referenciaEntrega = ref(initialDeliveryData?.referencia_entrega || '');
const tipoEnvio = ref<'estandar' | 'express_mismo_dia'>(initialDeliveryData?.tipo_envio || 'estandar');
const errorFlete = ref('');
let solicitud = 0;
let temporizador: ReturnType<typeof setTimeout> | undefined;
let vencimiento: ReturnType<typeof setTimeout> | undefined;

const fleteCalculado = ref<CalculoFleteResponse | null>(null);
const isLoadingFlete = ref(false);

const opciones = ref<OpcionesEnvio | null>(null);
const cargandoOpciones = ref(false);
const errorOpciones = ref('');
let intervaloOpciones: ReturnType<typeof setInterval> | undefined;
let desmontado = false;
const ciudadesDisponibles = computed(() => [...new Set(opciones.value?.zonas.map(z => z.ciudad) || [])].sort());
const zonasDisponibles = computed(() => opciones.value?.zonas.filter(z => z.ciudad === ciudadDomicilio.value).map(z => z.nombre) || []);
const zonaActiva = computed(() => opciones.value?.zonas.find(z => z.ciudad === ciudadDomicilio.value && z.nombre === zonaDomicilio.value));

watch(ciudadDomicilio, () => {
  zonaDomicilio.value = '';
}, { flush: 'sync' });
watch(zonaActiva, destino => {
  if (!destino) return;
  if (tipoEnvio.value === 'estandar' && !destino.estandar_habilitado) tipoEnvio.value = 'express_mismo_dia';
  else if (tipoEnvio.value === 'express_mismo_dia' && !destino.express_habilitado) tipoEnvio.value = 'estandar';
}, { flush: 'sync' });

async function cargarOpciones() {
  if (cargandoOpciones.value || props.bloqueado) return;
  cargandoOpciones.value = true;
  errorOpciones.value = '';
  try {
    const nuevas = await obtenerOpcionesEnvio();
    if (desmontado || props.bloqueado) return;
    if (nuevas.version === opciones.value?.version) return;
    const ciudadAnterior = ciudadDomicilio.value;
    const zonaAnterior = zonaDomicilio.value;
    opciones.value = nuevas;
    ciudadDomicilio.value = nuevas.zonas.find(z => z.ciudad.toLocaleLowerCase() === ciudadAnterior.trim().toLocaleLowerCase())?.ciudad || '';
    zonaDomicilio.value = nuevas.zonas.find(z => z.ciudad === ciudadDomicilio.value && z.nombre.toLocaleLowerCase() === zonaAnterior.trim().toLocaleLowerCase())?.nombre || '';
    programarCotizacion();
  } catch (err) {
    if (desmontado || props.bloqueado) return;
    opciones.value = null;
    errorOpciones.value = mensajeErrorEnvios(err, 'No pudimos cargar los destinos de entrega. Intenta nuevamente.');
    programarCotizacion();
  } finally {
    cargandoOpciones.value = false;
  }
}

// Estado para Retiro en Sucursal
const filtroCiudadSucursal = ref('Todas');
const sucursales = ref<SucursalRetiro[]>([]);
const sucursalSeleccionada = ref<SucursalRetiro | null>(null);
const isLoadingSucursales = ref(false);

// Cargar sucursales habilitadas (Subtarea 2)
async function cargarSucursales() {
  isLoadingSucursales.value = true;
  try {
    const res = await apiClient.get<SucursalRetiro[]>('/api/v1/ordenes/sucursales/habilitadas-retiro');
    sucursales.value = res.data;
    if (res.data.length > 0 && !sucursalSeleccionada.value) {
      sucursalSeleccionada.value = res.data[0];
    }
  } catch (err) {
    console.warn('Error cargando sucursales de retiro:', err);
  } finally {
    isLoadingSucursales.value = false;
  }
}

// Sucursales filtradas
const sucursalesFiltradas = computed(() => {
  if (filtroCiudadSucursal.value === 'Todas') {
    return sucursales.value;
  }
  return sucursales.value.filter(s => s.ciudad.toLowerCase() === filtroCiudadSucursal.value.toLowerCase());
});

// Algoritmo de cálculo de costo de flete (Subtarea 1)
function programarCotizacion() {
  if (props.bloqueado) return;
  solicitud++;
  clearTimeout(temporizador);
  clearTimeout(vencimiento);
  fleteCalculado.value = null;
  errorFlete.value = '';
  isLoadingFlete.value = tipoDespacho.value === 'domicilio' && !!zonaActiva.value && direccionExacta.value.trim().length >= 5;
  emitirCambios();
  if (isLoadingFlete.value) temporizador = setTimeout(calcularFlete, 300);
}

async function calcularFlete() {
  clearTimeout(temporizador);
  if (props.bloqueado) return;
  if (!zonaActiva.value || direccionExacta.value.trim().length < 5) { programarCotizacion(); return; }
  const id = ++solicitud;
  fleteCalculado.value = null;
  errorFlete.value = '';
  isLoadingFlete.value = true;
  emitirCambios();
  try {
    const { data } = await apiClient.post<CalculoFleteResponse>('/api/v1/ordenes/flete/calcular', {
      ciudad: ciudadDomicilio.value,
      zona: zonaDomicilio.value,
      direccion: direccionExacta.value.trim(),
      referencia: referenciaEntrega.value.trim(),
      subtotal_productos: props.subtotal,
      reserva_id: props.reservaId,
      puntos_canjeados: props.puntosCanjeados || 0,
      cupon: props.cupon,
      tipo_envio: tipoEnvio.value
    });
    if (id !== solicitud) return;
    fleteCalculado.value = {
      ...data,
      costo_flete: Number(data.costo_flete),
      costo_original: Number(data.costo_original),
      umbral_flete_gratis: Number(data.umbral_flete_gratis),
      total: Number(data.total),
    };
    if (data.expira_en) vencimiento = setTimeout(() => {
      solicitud++;
      fleteCalculado.value = null;
      errorFlete.value = 'La cotización venció. Vuelve a cotizar para continuar.';
      emitirCambios();
    }, Math.max(0, data.expira_en * 1000 - Date.now()));
  } catch (err: any) {
    if (id !== solicitud) return;
    errorFlete.value = typeof err.response?.data?.detail === 'string'
      ? err.response.data.detail : 'No pudimos cotizar el envío. Intenta nuevamente.';
  } finally {
    if (id === solicitud) {
      isLoadingFlete.value = false;
      emitirCambios();
    }
  }
}

// Validación de paso
const esValido = computed(() => {
  if (tipoDespacho.value === 'domicilio') {
    return direccionExacta.value.trim().length >= 5 && !isLoadingFlete.value && !!fleteCalculado.value?.cotizacion_flete && Number(fleteCalculado.value.expira_en) * 1000 > Date.now();
  } else {
    return sucursalSeleccionada.value !== null;
  }
});

function emitirCambios() {
  const data: SeleccionEntregaData = {
    cotizacion_flete: fleteCalculado.value?.cotizacion_flete,
    total_cotizado: fleteCalculado.value?.total,
    tipo_despacho: tipoDespacho.value,
    ciudad: ciudadDomicilio.value,
    zona: zonaDomicilio.value,
    direccion_exacta: direccionExacta.value,
    referencia_entrega: referenciaEntrega.value,
    tipo_envio: tipoEnvio.value,
    costo_flete: tipoDespacho.value === 'domicilio' ? Number(fleteCalculado.value?.costo_flete) || 0 : 0,
    flete_gratis: tipoDespacho.value === 'domicilio' ? (fleteCalculado.value?.flete_gratis || false) : true,
    tiempo_estimado: tipoDespacho.value === 'domicilio'
      ? (fleteCalculado.value?.tiempo_estimado || '')
      : (sucursalSeleccionada.value?.tiempo_preparacion || 'Listo en 2 horas'),
    sucursal_seleccionada: tipoDespacho.value === 'retiro_sucursal' ? sucursalSeleccionada.value : null
  };

  emit('update:modelValue', data);
  emit('validation-change', esValido.value);
}

watch([tipoDespacho, ciudadDomicilio, zonaDomicilio, direccionExacta, referenciaEntrega, tipoEnvio,
  () => props.subtotal, () => props.reservaId, () => props.puntosCanjeados, () => props.cupon], programarCotizacion, { flush: 'sync' });
watch(sucursalSeleccionada, emitirCambios);
onMounted(() => {
  cargarSucursales();
  cargarOpciones();
  intervaloOpciones = setInterval(() => { if (!props.bloqueado) cargarOpciones(); }, 30000);
  programarCotizacion();
});
onBeforeUnmount(() => {
  desmontado = true;
  clearInterval(intervaloOpciones);
  solicitud++;
  clearTimeout(temporizador);
  clearTimeout(vencimiento);
  emit('validation-change', false);
});
</script>

<template>
  <div class="space-y-6">
    <h4 class="text-base font-bold text-slate-900 dark:text-white">¿Cómo deseas recibir tus productos?</h4>

    <!-- Pestañas Selectoras de Modalidad (Subtarea 3) -->
    <div class="grid grid-cols-2 gap-3 p-1.5 bg-slate-100 dark:bg-slate-800/80 rounded-2xl">
      <button
        type="button"
        @click="tipoDespacho = 'domicilio';"
        :class="[
          'py-3 px-4 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2.5 transition-all',
          tipoDespacho === 'domicilio'
            ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-md border border-slate-200 dark:border-slate-700'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
        ]"
      >
        <Truck class="w-4 h-4 sm:w-5 sm:h-5" />
        <div class="text-left">
          <span class="block">Envío a Domicilio</span>
          <span class="block text-[10px] font-normal opacity-75">
            {{ fleteCalculado ? (fleteCalculado.flete_gratis ? '¡Flete Gratis!' : `BOB ${fleteCalculado.costo_flete.toFixed(2)}`) : 'Selecciona tu destino para cotizar' }}
          </span>
        </div>
      </button>

      <button
        type="button"
        @click="tipoDespacho = 'retiro_sucursal'; emitirCambios();"
        :class="[
          'py-3 px-4 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2.5 transition-all',
          tipoDespacho === 'retiro_sucursal'
            ? 'bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-400 shadow-md border border-slate-200 dark:border-slate-700'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
        ]"
      >
        <Store class="w-4 h-4 sm:w-5 sm:h-5" />
        <div class="text-left">
          <span class="block">Retiro en Sucursal</span>
          <span class="block text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
            ¡100% GRATIS • En 2 hrs!
          </span>
        </div>
      </button>
    </div>

    <!-- PANEL 1: ENVÍO A DOMICILIO -->
    <div v-if="tipoDespacho === 'domicilio'" class="space-y-5 animate-in fade-in duration-200">
      <div class="p-4 bg-blue-50/50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/40 rounded-2xl flex items-start gap-3">
        <Info class="w-5 h-5 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
        <div class="text-xs text-slate-700 dark:text-slate-300 space-y-1">
          <p class="font-bold text-blue-900 dark:text-blue-200">
            Cotización de entrega
          </p>
          <p>
            {{ direccionGuardada ? (zonaActiva ? 'Usaremos la ubicación guardada en tu libreta para calcular el envío.' : 'Edita tu dirección en Mi cuenta para seleccionar una zona de entrega disponible.') : 'Selecciona tu ciudad y zona para conocer el costo y el plazo estimado de entrega antes de pagar.' }}
          </p>
        </div>
      </div>

      <p v-if="cargandoOpciones && !opciones" role="status" class="text-sm text-slate-500">Cargando destinos disponibles...</p>
      <div v-if="errorOpciones" role="alert" class="text-sm text-rose-600">
        <p>{{ errorOpciones }}</p>
        <button type="button" @click="cargarOpciones" class="underline">Volver a cargar destinos</button>
      </div>
      <p v-else-if="opciones && !opciones.zonas.length" class="text-sm text-amber-700">Por el momento no hay zonas habilitadas para entrega a domicilio. Puedes elegir retiro en sucursal.</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <!-- Selector de Ciudad -->
        <div v-if="!direccionGuardada" class="space-y-1.5">
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
            Ciudad / Departamento:
          </label>
          <select
            v-model="ciudadDomicilio"
            class="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-white font-medium focus:ring-2 focus:ring-blue-500"
          >
            <option disabled value="">Selecciona una ciudad</option>
            <option v-for="ciudad in ciudadesDisponibles" :key="ciudad" :value="ciudad">{{ ciudad }}</option>
          </select>
        </div>

        <!-- Selector de Zona -->
        <div v-if="!direccionGuardada" class="space-y-1.5">
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
            Zona de Entrega:
          </label>
          <select
            v-model="zonaDomicilio"
            class="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-white font-medium focus:ring-2 focus:ring-blue-500"
          >
            <option disabled value="">Selecciona tu zona</option>
            <option v-for="z in zonasDisponibles" :key="z" :value="z">
              {{ z }}
            </option>
          </select>
        </div>
      </div>

      <!-- Dirección exacta y referencia -->
      <div v-if="!direccionGuardada" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="space-y-1.5">
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
            Dirección exacta (Calle, N°, Edificio/Piso):
          </label>
          <input
            v-model="direccionExacta"
            type="text"
            placeholder="Ej. Av. 6 de Agosto #2450, Dpto 4B"
            class="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div class="space-y-1.5">
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
            Referencia de entrega:
          </label>
          <input
            v-model="referenciaEntrega"
            type="text"
            placeholder="Ej. Frente a Farmacia Chavez, rejas negras"
            class="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <!-- Opciones de Velocidad de Despacho -->
      <div class="space-y-2">
        <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
          Tipo de servicio de envío:
        </label>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            type="button"
            @click="tipoEnvio = 'estandar';"
            :disabled="!zonaActiva?.estandar_habilitado"
            :aria-pressed="tipoEnvio === 'estandar'"
            :class="[
              'p-3.5 rounded-xl border cursor-pointer flex items-center justify-between transition-all disabled:opacity-50 disabled:cursor-not-allowed',
              tipoEnvio === 'estandar'
                ? 'border-blue-600 bg-blue-50/50 dark:bg-blue-950/40 text-blue-900 dark:text-blue-100 shadow-sm'
                : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
            ]"
          >
            <div class="flex items-center gap-3">
              <Clock class="w-5 h-5 text-blue-600 dark:text-blue-400" />
              <div>
                <p class="text-xs font-bold">Envío Estándar</p>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">{{ zonaActiva?.estandar_habilitado ? zonaActiva.plazo_estandar : 'No disponible en esta zona' }}</p>
              </div>
            </div>
            <span class="text-xs font-extrabold text-blue-700 dark:text-blue-300">
              {{ tipoEnvio === 'estandar' && fleteCalculado ? (fleteCalculado.flete_gratis ? 'GRATIS' : `BOB ${fleteCalculado.costo_flete.toFixed(2)}`) : 'Cotizar' }}
            </span>
          </button>

          <button
            type="button"
            @click="tipoEnvio = 'express_mismo_dia';"
            :disabled="!zonaActiva?.express_habilitado"
            :aria-pressed="tipoEnvio === 'express_mismo_dia'"
            :class="[
              'p-3.5 rounded-xl border cursor-pointer flex items-center justify-between transition-all disabled:opacity-50 disabled:cursor-not-allowed',
              tipoEnvio === 'express_mismo_dia'
                ? 'border-amber-500 bg-amber-50/50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100 shadow-sm'
                : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
            ]"
          >
            <div class="flex items-center gap-3">
              <Zap class="w-5 h-5 text-amber-600 dark:text-amber-400" />
              <div>
                <p class="text-xs font-bold">Express Mismo Día</p>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">{{ zonaActiva?.express_habilitado ? zonaActiva.plazo_express : 'No disponible en esta zona' }}</p>
              </div>
            </div>
            <span class="text-xs font-extrabold text-amber-700 dark:text-amber-400">
              {{ tipoEnvio === 'express_mismo_dia' && fleteCalculado ? (fleteCalculado.flete_gratis ? 'GRATIS' : `BOB ${fleteCalculado.costo_flete.toFixed(2)}`) : 'Cotizar' }}
            </span>
          </button>
        </div>
      </div>

      <p v-if="isLoadingFlete" role="status" aria-live="polite" class="text-sm text-blue-600">Cotizando envío...</p>
      <div v-if="errorFlete" role="alert" class="text-sm text-rose-600 space-y-2">
        <p>{{ errorFlete }}</p>
        <button type="button" @click="calcularFlete" class="underline font-semibold">Volver a cotizar</button>
      </div>
      <!-- Tarjeta Resumen del Flete Calculado -->
      <div v-if="fleteCalculado" class="p-4 bg-slate-50 dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Truck class="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <span class="text-xs font-bold text-slate-800 dark:text-slate-200">
              Resumen de Tarifa de Despacho ({{ fleteCalculado.ciudad }} - {{ fleteCalculado.zona }}):
            </span>
          </div>
          <div class="text-right">
            <span v-if="fleteCalculado.flete_gratis" class="text-sm font-black text-emerald-600 dark:text-emerald-400">
              BOB 0.00 (FLETE GRATIS)
            </span>
            <span v-else class="text-sm font-black text-blue-600 dark:text-blue-400">
              BOB {{ fleteCalculado.costo_flete.toFixed(2) }}
            </span>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] text-slate-600 dark:text-slate-400 pt-2 border-t border-slate-200 dark:border-slate-700">
          <div>
            <span class="block text-slate-400">Tarifa Base:</span>
            <span class="font-semibold">BOB {{ fleteCalculado.desglose.tarifa_base_zona.toFixed(2) }}</span>
          </div>
          <div>
            <span class="block text-slate-400">Tiempo estimado:</span>
            <span class="font-semibold text-slate-900 dark:text-white">{{ fleteCalculado.tiempo_estimado }}</span>
          </div>
          <div>
            <span class="block text-slate-400">Peso estimado:</span>
            <span class="font-semibold">{{ fleteCalculado.desglose.peso_estimado_kg }} kg</span>
          </div>
          <div>
            <span class="block text-slate-400">Estado Promoción:</span>
            <span :class="fleteCalculado.flete_gratis ? 'text-emerald-600 font-bold' : 'text-slate-500'">
              {{ fleteCalculado.flete_gratis ? '100% Bonificado' : 'Tarifa Normal' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- PANEL 2: RETIRO EN SUCURSAL CON MAPA INTERACTIVO (Subtarea 4) -->
    <div v-else class="space-y-5 animate-in fade-in duration-200">
      <!-- Banner Click and Collect -->
      <div class="p-4 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 rounded-2xl flex items-start gap-3">
        <Store class="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
        <div class="text-xs text-slate-700 dark:text-slate-300 space-y-1">
          <p class="font-bold text-emerald-900 dark:text-emerald-200">
            Retiro en Tienda Física (Click & Collect - KAN-27):
          </p>
          <p>
            Sin costo de flete. Te enviaremos un <strong>Código QR único</strong> para retirar tu pedido presentando tu documento en mostrador de caja.
          </p>
        </div>
      </div>

      <!-- Filtro de Ciudad para Sucursales -->
      <div class="flex items-center gap-2 overflow-x-auto pb-1">
        <span class="text-xs font-bold text-slate-500 whitespace-nowrap">Filtrar ciudad:</span>
        <button
          v-for="c in ['Todas', 'La Paz', 'El Alto', 'Santa Cruz', 'Cochabamba']"
          :key="c"
          type="button"
          @click="filtroCiudadSucursal = c"
          :class="[
            'px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all',
            filtroCiudadSucursal === c
              ? 'bg-emerald-600 text-white shadow-sm'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200'
          ]"
        >
          {{ c }}
        </button>
      </div>

      <!-- VISUALIZADOR DE MAPA INTERACTIVO DE TIENDAS (Subtarea 4) -->
      <div class="border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden bg-slate-900 relative">
        <div class="p-3 bg-slate-800 border-b border-slate-700 flex justify-between items-center text-xs text-white">
          <span class="font-bold flex items-center gap-1.5">
            <Navigation class="w-4 h-4 text-emerald-400" />
            Mapa de Cobertura y Sucursales con Stock Físico (Bolivia)
          </span>
          <span class="text-[11px] text-emerald-400 font-semibold flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            {{ sucursalesFiltradas.length }} sucursales operativas
          </span>
        </div>

        <!-- Lienzo de Mapa SVG Interactivo -->
        <div class="h-48 sm:h-56 w-full relative bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center overflow-hidden">
          <!-- Cuadrícula esquemática de calles del mapa -->
          <svg class="absolute inset-0 w-full h-full opacity-20" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <pattern id="mapGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#60a5fa" stroke-width="0.8" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#mapGrid)" />
            <!-- Vías principales estilizadas -->
            <path d="M 0 100 Q 200 40 450 120 T 900 160" fill="none" stroke="#38bdf8" stroke-width="2.5" opacity="0.6" />
            <path d="M 250 0 L 280 250" fill="none" stroke="#38bdf8" stroke-width="2" opacity="0.5" />
            <path d="M 520 0 Q 500 120 540 250" fill="none" stroke="#38bdf8" stroke-width="2" opacity="0.5" />
          </svg>

          <!-- Marcadores / Pines de Sucursal en el Mapa -->
          <div class="relative w-full h-full max-w-2xl px-6 py-4 flex items-center justify-around z-10">
            <div
              v-for="(suc, idx) in sucursalesFiltradas"
              :key="suc.id"
              @click="sucursalSeleccionada = suc"
              :class="[
                'group flex flex-col items-center cursor-pointer transition-all transform',
                sucursalSeleccionada?.id === suc.id
                  ? 'scale-125 z-20'
                  : 'opacity-70 hover:opacity-100 hover:scale-110'
              ]"
            >
              <div
                :class="[
                  'w-9 h-9 rounded-full flex items-center justify-center shadow-lg border-2 transition-all',
                  sucursalSeleccionada?.id === suc.id
                    ? 'bg-emerald-500 border-white text-white ring-4 ring-emerald-500/40'
                    : 'bg-slate-700 border-slate-500 text-emerald-300'
                ]"
              >
                <MapPin class="w-5 h-5" />
              </div>
              <span class="mt-1 px-2 py-0.5 rounded bg-black/80 text-[10px] font-bold text-white whitespace-nowrap shadow">
                {{ suc.nombre.replace('Sucursal ', '') }}
              </span>
            </div>
          </div>

          <!-- Coordenadas GPS del punto seleccionado -->
          <div v-if="sucursalSeleccionada" class="absolute bottom-2 left-3 bg-black/70 backdrop-blur-sm px-2.5 py-1 rounded-lg text-[10px] text-slate-300 flex items-center gap-2">
            <span class="text-emerald-400 font-bold">GPS:</span>
            <span>Lat: {{ sucursalSeleccionada.coordenadas.lat }}</span>
            <span>Lng: {{ sucursalSeleccionada.coordenadas.lng }}</span>
          </div>
        </div>
      </div>

      <!-- Lista de Selección de Sucursales -->
      <div class="space-y-2.5 max-h-64 overflow-y-auto pr-1">
        <div
          v-for="s in sucursalesFiltradas"
          :key="s.id"
          @click="sucursalSeleccionada = s"
          :class="[
            'p-3.5 rounded-2xl border cursor-pointer transition-all flex items-start justify-between gap-3',
            sucursalSeleccionada?.id === s.id
              ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/40 shadow-sm ring-1 ring-emerald-500'
              : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/60 hover:border-slate-300'
          ]"
        >
          <div class="flex items-start gap-3">
            <div
              :class="[
                'w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5',
                sucursalSeleccionada?.id === s.id
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-500'
              ]"
            >
              <Building2 class="w-4 h-4" />
            </div>

            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <h5 class="text-xs font-bold text-slate-900 dark:text-white">
                  {{ s.nombre }}
                </h5>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                  Stock Inmediato
                </span>
              </div>
              <p class="text-xs text-slate-600 dark:text-slate-400 flex items-center gap-1">
                <MapPin class="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>{{ s.direccion }}</span>
              </p>
              <div class="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 pt-0.5">
                <span class="flex items-center gap-1">
                  <Clock class="w-3 h-3 text-emerald-600" />
                  {{ s.horario_atencion }}
                </span>
                <span class="flex items-center gap-1">
                  <Phone class="w-3 h-3 text-slate-400" />
                  {{ s.telefono }}
                </span>
              </div>
            </div>
          </div>

          <div class="text-right shrink-0">
            <span class="inline-block px-2.5 py-1 rounded-lg bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200 font-extrabold text-[11px]">
              GRATIS
            </span>
            <span class="block text-[10px] text-slate-400 mt-1">
              {{ s.tiempo_preparacion }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
