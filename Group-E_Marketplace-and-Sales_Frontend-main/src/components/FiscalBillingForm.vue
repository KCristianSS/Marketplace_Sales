<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { apiClient } from '@/api/client';
import type { DatosFiscales, PerfilFiscal, TipoDocumentoFiscal, ValidacionNitResponse } from '@/types';
import { 
  FileText, 
  CheckCircle2, 
  AlertTriangle, 
  Search, 
  UserCheck, 
  Bookmark, 
  Sparkles,
  Building,
  Mail,
  ShieldCheck,
  RefreshCw
} from 'lucide-vue-next';

const props = withDefaults(defineProps<{
  modelValue?: DatosFiscales;
  compact?: boolean;
  context?: 'web' | 'pos';
}>(), {
  compact: false,
  context: 'web'
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: DatosFiscales): void;
  (e: 'validation-change', isValid: boolean): void;
}>();

// Estado local reactivo
const modalidad = ref<'con_factura' | 'sin_factura'>(props.modelValue?.modalidad || 'con_factura');
const tipoDocumento = ref<TipoDocumentoFiscal>(props.modelValue?.tipo_documento || 'NIT');
const nitCi = ref(props.modelValue?.nit_ci || '');
const razonSocial = ref(props.modelValue?.razon_social || '');
const emailFacturacion = ref(props.modelValue?.email_facturacion || '');
const guardarPerfil = ref(props.modelValue?.guardar_perfil ?? true);

// Estado de validación fiscal
const isValidating = ref(false);
const validationResult = ref<ValidacionNitResponse | null>(null);
const validationError = ref('');
const savedProfiles = ref<PerfilFiscal[]>([]);
const isLoadingProfiles = ref(false);

// Cargar perfiles guardados
async function loadSavedProfiles() {
  isLoadingProfiles.value = true;
  try {
    const res = await apiClient.get('/v1/facturacion/perfiles-fiscales');
    savedProfiles.value = Array.isArray(res.data) ? res.data : [];
  } catch (err) {
    console.warn('No se pudieron cargar perfiles fiscales guardados:', err);
  } finally {
    isLoadingProfiles.value = false;
  }
}

// Aplicar perfil fiscal guardado
function applyProfile(profile: PerfilFiscal) {
  modalidad.value = 'con_factura';
  tipoDocumento.value = profile.tipo_documento;
  nitCi.value = profile.nit_ci;
  razonSocial.value = profile.razon_social;
  if (profile.email_facturacion) {
    emailFacturacion.value = profile.email_facturacion;
  }
  validationResult.value = {
    valido: true,
    nit_ci: profile.nit_ci,
    razon_social: profile.razon_social,
    estado: 'ACTIVO',
    mensaje: 'Perfil fiscal verificado.'
  };
  validationError.value = '';
}

// Validación de NIT con el servicio fiscal (KAN-365)
async function validarNitFiscal() {
  if (modalidad.value === 'sin_factura') {
    validationResult.value = {
      valido: true,
      nit_ci: '0',
      razon_social: 'CONSUMIDOR FINAL',
      estado: 'ACTIVO'
    };
    return;
  }

  const clean = nitCi.value.trim();
  if (!clean) {
    validationError.value = 'Ingresa un número de NIT o CI.';
    validationResult.value = null;
    return;
  }

  isValidating.value = true;
  validationError.value = '';
  try {
    const res = await apiClient.post<ValidacionNitResponse>('/v1/facturacion/validar-nit', {
      nit_ci: clean,
      tipo_documento: tipoDocumento.value
    });

    validationResult.value = res.data;
    if (res.data.valido) {
      if (res.data.razon_social && (!razonSocial.value || razonSocial.value === 'CONSUMIDOR FINAL')) {
        razonSocial.value = res.data.razon_social;
      }
    } else {
      validationError.value = res.data.mensaje || 'No se pudieron validar los datos fiscales.';
    }
  } catch (err: any) {
    validationError.value = err.response?.data?.mensaje || 'Error al consultar la validación preliminar.';
    validationResult.value = null;
  } finally {
    isValidating.value = false;
  }
}

// Al cambiar a "sin_factura", colocar automáticamente Consumidor Final
watch(modalidad, (newMod) => {
  if (newMod === 'sin_factura') {
    nitCi.value = '0';
    razonSocial.value = 'CONSUMIDOR FINAL';
    tipoDocumento.value = 'CI';
    validationResult.value = {
      valido: true,
      nit_ci: '0',
      razon_social: 'CONSUMIDOR FINAL',
      estado: 'ACTIVO'
    };
    validationError.value = '';
  } else {
    if (nitCi.value === '0') {
      nitCi.value = '';
      razonSocial.value = '';
      tipoDocumento.value = 'NIT';
      validationResult.value = null;
    }
  }
  emitData();
});

// Comprobar validez global del formulario
const isFormValid = computed(() => {
  if (modalidad.value === 'sin_factura') return true;
  return nitCi.value.trim().length >= 4 && razonSocial.value.trim().length >= 3;
});

function emitData() {
  const current: DatosFiscales = {
    modalidad: modalidad.value,
    tipo_documento: tipoDocumento.value,
    nit_ci: modalidad.value === 'sin_factura' ? '0' : nitCi.value.trim(),
    razon_social: modalidad.value === 'sin_factura' ? 'CONSUMIDOR FINAL' : razonSocial.value.trim().toUpperCase(),
    email_facturacion: emailFacturacion.value.trim() || undefined,
    guardar_perfil: guardarPerfil.value
  };
  emit('update:modelValue', current);
  emit('validation-change', isFormValid.value);
}

watch([tipoDocumento, nitCi, razonSocial, emailFacturacion, guardarPerfil], () => {
  emitData();
});

onMounted(() => {
  loadSavedProfiles();
  emitData();
});
</script>

<template>
  <div class="space-y-4 text-slate-800 dark:text-slate-200">
    <!-- Header del Componente Fiscal -->
    <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-2.5">
      <div class="flex items-center gap-2">
        <div class="p-1.5 rounded-lg bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400">
          <FileText class="w-4 h-4" />
        </div>
        <div>
          <h4 class="text-xs font-bold text-slate-900 dark:text-white">Datos para factura electrónica</h4>
          <p class="text-[10px] text-slate-400">La autorización final depende del servicio de facturación.</p>
        </div>
      </div>
      <span class="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded-full">
        <ShieldCheck class="w-3 h-3" /> Validación preliminar
      </span>
    </div>

    <!-- Selector de Modalidad: Con Factura vs Sin Factura / Consumidor Final -->
    <div class="grid grid-cols-2 gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl">
      <button
        type="button"
        @click="modalidad = 'con_factura'"
        :class="[
          'py-2 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5',
          modalidad === 'con_factura'
            ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
        ]"
      >
        <Building class="w-3.5 h-3.5" />
        <span>Factura con NIT / CI</span>
      </button>

      <button
        type="button"
        @click="modalidad = 'sin_factura'"
        :class="[
          'py-2 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5',
          modalidad === 'sin_factura'
            ? 'bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-400 shadow-sm'
            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
        ]"
      >
        <UserCheck class="w-3.5 h-3.5" />
        <span>Sin Factura (Consumidor Final)</span>
      </button>
    </div>

    <!-- Accesos Rápidos de Perfiles Guardados (si existen y estamos en modo con factura) -->
    <div v-if="modalidad === 'con_factura' && savedProfiles.length > 0" class="space-y-1.5">
      <div class="flex items-center justify-between text-[11px] text-slate-500 font-semibold">
        <span class="flex items-center gap-1"><Bookmark class="w-3 h-3 text-blue-500" /> Perfiles fiscales frecuentes:</span>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="profile in savedProfiles"
          :key="profile.id"
          type="button"
          @click="applyProfile(profile)"
          :class="[
            'px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-colors flex items-center gap-1.5',
            nitCi === profile.nit_ci
              ? 'bg-blue-50 dark:bg-blue-950/40 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
              : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-blue-400'
          ]"
        >
          <span class="font-mono font-bold">{{ profile.nit_ci }}</span>
          <span class="text-slate-400">·</span>
          <span class="truncate max-w-[140px]">{{ profile.razon_social }}</span>
        </button>
      </div>
    </div>

    <!-- Campos de Formulario (Modo Nominado) -->
    <div v-if="modalidad === 'con_factura'" class="space-y-3">
      <!-- Fila 1: Tipo Documento + Número NIT/CI -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <div>
          <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
            Tipo Documento
          </label>
          <select
            v-model="tipoDocumento"
            class="w-full px-2.5 py-2 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500 font-semibold"
          >
            <option value="NIT">NIT (Empresas / Profesionales)</option>
            <option value="CI">CI (Cédula de Identidad)</option>
            <option value="CEX">CEX (Extranjería)</option>
            <option value="PAS">PAS (Pasaporte)</option>
          </select>
        </div>

        <div class="sm:col-span-2">
          <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
            Número de {{ tipoDocumento }} *
          </label>
          <div class="flex gap-1.5">
            <input
              v-model="nitCi"
              @blur="validarNitFiscal"
              @keyup.enter="validarNitFiscal"
              type="text"
              required
              placeholder="Ej. 1020304050"
              class="flex-1 px-3 py-2 text-xs font-mono font-bold bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
            />
            <button
              type="button"
              @click="validarNitFiscal"
              :disabled="isValidating || !nitCi.trim()"
              class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold flex items-center gap-1 shrink-0 disabled:opacity-50"
              title="Validar datos fiscales disponibles"
            >
              <RefreshCw v-if="isValidating" class="w-3.5 h-3.5 animate-spin" />
              <Search v-else class="w-3.5 h-3.5" />
              <span class="hidden sm:inline">Validar</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Alerta / Badge de Validación Fiscal -->
      <div v-if="validationResult?.valido && nitCi !== '0'" class="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 text-[11px] text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
        <CheckCircle2 class="w-4 h-4 text-emerald-600 shrink-0" />
        <div class="flex-1">
          <span class="font-bold">Resultado preliminar:</span>
          <span> {{ validationResult.mensaje || 'Registrado en el Padrón Nacional.' }}</span>
        </div>
      </div>

      <div v-else-if="validationError" class="p-2.5 rounded-lg bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800 text-[11px] text-rose-700 dark:text-rose-300 flex items-center gap-2">
        <AlertTriangle class="w-4 h-4 text-rose-600 shrink-0" />
        <span>{{ validationError }}</span>
      </div>

      <!-- Fila 2: Razón Social / Nombre -->
      <div>
        <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1">
          Razón Social o Nombre Legal Completo *
        </label>
        <input
          v-model="razonSocial"
          type="text"
          required
          placeholder="Ej. EMPRESA MINERA SAN CRISTÓBAL S.A."
          class="w-full px-3 py-2 text-xs font-bold uppercase bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
        />
      </div>

      <!-- Fila 3: Email Facturación + Checkbox Guardar -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        <div>
          <label class="block text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-1 flex items-center gap-1">
            <Mail class="w-3 h-3 text-slate-400" /> Correo para Factura Electrónica
          </label>
          <input
            v-model="emailFacturacion"
            type="email"
            placeholder="facturacion@empresa.com"
            class="w-full px-3 py-2 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
          />
        </div>

        <div class="flex items-center pt-5">
          <label class="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer select-none">
            <input
              v-model="guardarPerfil"
              type="checkbox"
              class="w-4 h-4 text-blue-600 rounded border-slate-300 dark:border-slate-700 focus:ring-blue-500"
            />
            <span>Guardar perfil para futuras compras</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Modo Sin Factura / Consumidor Final -->
    <div v-else class="p-4 bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900 rounded-xl space-y-2">
      <div class="flex items-start gap-2.5">
        <CheckCircle2 class="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
        <div class="text-xs">
          <p class="font-bold text-emerald-900 dark:text-emerald-200">Emisión a Consumidor Final (Control Tributario)</p>
          <p class="text-[11px] text-emerald-700 dark:text-emerald-400 mt-0.5">
            Se usará NIT <strong>0</strong> a nombre de <strong>CONSUMIDOR FINAL</strong>. La factura solo se considerará autorizada tras la respuesta del servicio fiscal.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
