<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import {
  Truck,
  Store,
  MapPin,
  CheckCircle2,
  Clock,
  Phone,
  Info,
  Sparkles,
  Zap,
  ShieldCheck,
  Navigation,
  ChevronRight,
  Building2,
  RefreshCw
} from 'lucide-vue-next';
import { apiClient } from '@/api/client';
import type {
  TipoDespacho,
  SucursalRetiro,
  CalculoFleteResponse,
  SeleccionEntregaData
} from '@/types';

const props = defineProps<{
  subtotal: number;
  initialData?: Partial<SeleccionEntregaData>;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', data: SeleccionEntregaData): void;
  (e: 'validation-change', isValid: boolean): void;
}>();

// Estado de modalidad
const tipoDespacho = ref<TipoDespacho>(props.initialData?.tipo_despacho || 'domicilio');

// Estado para Envío a Domicilio
const ciudadDomicilio = ref('La Paz');
const zonaDomicilio = ref('Centro');
const direccionExacta = ref(props.initialData?.direccion_exacta || '');
const referenciaEntrega = ref(props.initialData?.referencia_entrega || '');
const tipoEnvio = ref<'estandar' | 'express_mismo_dia'>(props.initialData?.tipo_envio || 'estandar');
const pesoEstimado = ref(1.5); // kg promedio

const fleteCalculado = ref<CalculoFleteResponse | null>(null);
const isLoadingFlete = ref(false);

// Opciones de zonas según la ciudad
const ZONAS_POR_CIUDAD: Record<string, string[]> = {
  'La Paz': [
    'Centro',
    'Miraflores',
    'Sopocachi',
    'San Pedro',
    'Zona Sur (Calacoto / San Miguel)',
    'Achumani / Irpavi / Cota Cota',
    'Periférica / Laderas'
  ],
  'El Alto': [
    'Ceja',
    'Ciudad Satélite',
    'Villa Adela',
    'Rio Seco'
  ],
  'Santa Cruz': [
    '1er a 4to Anillo',
    'Equipetrol',
    'Urubó',
    '5to a 8vo Anillo',
    'Plan 3000'
  ],
  'Cochabamba': [
    'Centro / El Prado',
    'Cala Cala / Recoleta',
    'Zona Sur',
    'Sacaba / Quillacollo'
  ],
  'Sucre': ['Centro Histórico', 'Zona Alta', 'Rumi Rumi'],
  'Tarija': ['Centro', 'San Roque', 'Tomatitas'],
  'Oruro': ['Centro', 'Socavón', 'Zona Norte']
};

const zonasDisponibles = computed(() => {
  return ZONAS_POR_CIUDAD[ciudadDomicilio.value] || ['Centro', 'Periférica'];
});

// Saved addresses use free-text city names, so match them to a known city before seeding the selects.
const ciudadInicial = Object.keys(ZONAS_POR_CIUDAD).find(
  (ciudad) => ciudad.toLowerCase() === (props.initialData?.ciudad || '').trim().toLowerCase()
) || 'La Paz';
ciudadDomicilio.value = ciudadInicial;
zonaDomicilio.value = ZONAS_POR_CIUDAD[ciudadInicial].includes(props.initialData?.zona || '')
  ? props.initialData!.zona!
  : ZONAS_POR_CIUDAD[ciudadInicial][0];

// Cuando cambia la ciudad, reajustar zona por defecto
watch(ciudadDomicilio, (nuevaCiudad) => {
  const zonas = ZONAS_POR_CIUDAD[nuevaCiudad] || ['Centro'];
  zonaDomicilio.value = zonas[0];
  calcularFlete();
});

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
async function calcularFlete() {
  if (tipoDespacho.value !== 'domicilio') return;
  isLoadingFlete.value = true;
  try {
    const res = await apiClient.post<CalculoFleteResponse>('/api/v1/ordenes/flete/calcular', {
      ciudad: ciudadDomicilio.value,
      zona: zonaDomicilio.value,
      subtotal_productos: props.subtotal,
      peso_estimado_kg: pesoEstimado.value,
      tipo_envio: tipoEnvio.value
    });
    fleteCalculado.value = res.data;
  } catch (err) {
    console.warn('Error calculando flete:', err);
  } finally {
    isLoadingFlete.value = false;
    emitirCambios();
  }
}

// Validación de paso
const esValido = computed(() => {
  if (tipoDespacho.value === 'domicilio') {
    return direccionExacta.value.trim().length >= 5 && fleteCalculado.value !== null;
  } else {
    return sucursalSeleccionada.value !== null;
  }
});

function emitirCambios() {
  const data: SeleccionEntregaData = {
    tipo_despacho: tipoDespacho.value,
    ciudad: ciudadDomicilio.value,
    zona: zonaDomicilio.value,
    direccion_exacta: direccionExacta.value,
    referencia_entrega: referenciaEntrega.value,
    tipo_envio: tipoEnvio.value,
    costo_flete: tipoDespacho.value === 'domicilio' ? Number(fleteCalculado.value?.costo_flete) || 0 : 0,
    flete_gratis: tipoDespacho.value === 'domicilio' ? (fleteCalculado.value?.flete_gratis || false) : true,
    tiempo_estimado: tipoDespacho.value === 'domicilio'
      ? (fleteCalculado.value?.tiempo_estimado || '24 a 48 horas')
      : (sucursalSeleccionada.value?.tiempo_preparacion || 'Listo en 2 horas'),
    sucursal_seleccionada: tipoDespacho.value === 'retiro_sucursal' ? sucursalSeleccionada.value : null
  };

  emit('update:modelValue', data);
  emit('validation-change', esValido.value);
}

watch([tipoDespacho, zonaDomicilio, direccionExacta, referenciaEntrega, tipoEnvio, sucursalSeleccionada], () => {
  emitirCambios();
});

watch(() => props.subtotal, () => {
  calcularFlete();
});

onMounted(() => {
  cargarSucursales();
  calcularFlete();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Encabezado de Selección con Badge de Trazabilidad Jira -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
      <div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-950/80 dark:text-blue-300">
            RF-15 / US-15
          </span>
          <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
            Paso 1 de 2: Modalidad de Entrega (KAN-31)
          </span>
        </div>
        <h4 class="text-base font-bold text-slate-900 dark:text-white mt-1">
          ¿Cómo deseas recibir tus productos?
        </h4>
      </div>

      <!-- Indicador de Flete Gratis -->
      <div v-if="subtotal >= 500" class="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl text-emerald-700 dark:text-emerald-300 text-xs font-bold">
        <Sparkles class="w-3.5 h-3.5" />
        <span>¡Calificas para Flete GRATIS! (Subtotal ≥ 500 BOB)</span>
      </div>
      <div v-else class="text-right text-[11px] text-slate-500">
        Agrega <span class="font-bold text-blue-600">BOB {{ (500 - subtotal).toFixed(2) }}</span> más para flete gratis
      </div>
    </div>

    <!-- Pestañas Selectoras de Modalidad (Subtarea 3) -->
    <div class="grid grid-cols-2 gap-3 p-1.5 bg-slate-100 dark:bg-slate-800/80 rounded-2xl">
      <button
        type="button"
        @click="tipoDespacho = 'domicilio'; calcularFlete();"
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
            {{ fleteCalculado?.flete_gratis ? '¡Flete Gratis!' : `Desde BOB 15.00` }}
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
            Algoritmo de cálculo dinámico de flete (RF-15):
          </p>
          <p>
            El costo de entrega se calcula automáticamente según la matriz por departamento, zona urbana seleccionada, peso estimado y tiempo de despacho.
          </p>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <!-- Selector de Ciudad -->
        <div class="space-y-1.5">
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
            Ciudad / Departamento:
          </label>
          <select
            v-model="ciudadDomicilio"
            class="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-white font-medium focus:ring-2 focus:ring-blue-500"
          >
            <option value="La Paz">La Paz</option>
            <option value="El Alto">El Alto</option>
            <option value="Santa Cruz">Santa Cruz</option>
            <option value="Cochabamba">Cochabamba</option>
            <option value="Sucre">Sucre</option>
            <option value="Tarija">Tarija</option>
            <option value="Oruro">Oruro</option>
          </select>
        </div>

        <!-- Selector de Zona -->
        <div class="space-y-1.5">
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300">
            Zona de Entrega:
          </label>
          <select
            v-model="zonaDomicilio"
            @change="calcularFlete"
            class="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-white font-medium focus:ring-2 focus:ring-blue-500"
          >
            <option v-for="z in zonasDisponibles" :key="z" :value="z">
              {{ z }}
            </option>
          </select>
        </div>
      </div>

      <!-- Dirección exacta y referencia -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
          <label
            @click="tipoEnvio = 'estandar'; calcularFlete();"
            :class="[
              'p-3.5 rounded-xl border cursor-pointer flex items-center justify-between transition-all',
              tipoEnvio === 'estandar'
                ? 'border-blue-600 bg-blue-50/50 dark:bg-blue-950/40 text-blue-900 dark:text-blue-100 shadow-sm'
                : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
            ]"
          >
            <div class="flex items-center gap-3">
              <Clock class="w-5 h-5 text-blue-600 dark:text-blue-400" />
              <div>
                <p class="text-xs font-bold">Envío Estándar</p>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">Entrega en 24 a 48 horas hábiles</p>
              </div>
            </div>
            <span class="text-xs font-extrabold text-blue-700 dark:text-blue-300">
              {{ fleteCalculado?.flete_gratis ? 'GRATIS' : (fleteCalculado?.desglose.tarifa_base_zona.toFixed(2) + ' BOB') }}
            </span>
          </label>

          <label
            @click="tipoEnvio = 'express_mismo_dia'; calcularFlete();"
            :class="[
              'p-3.5 rounded-xl border cursor-pointer flex items-center justify-between transition-all',
              tipoEnvio === 'express_mismo_dia'
                ? 'border-amber-500 bg-amber-50/50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100 shadow-sm'
                : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
            ]"
          >
            <div class="flex items-center gap-3">
              <Zap class="w-5 h-5 text-amber-600 dark:text-amber-400" />
              <div>
                <p class="text-xs font-bold">Express Mismo Día</p>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">Menos de 4 horas hábiles</p>
              </div>
            </div>
            <span class="text-xs font-extrabold text-amber-700 dark:text-amber-400">
              +15.00 BOB
            </span>
          </label>
        </div>
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
            <span class="block text-slate-400">Distancia aprox:</span>
            <span class="font-semibold">{{ fleteCalculado.desglose.distancia_estimada_km }} km</span>
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
