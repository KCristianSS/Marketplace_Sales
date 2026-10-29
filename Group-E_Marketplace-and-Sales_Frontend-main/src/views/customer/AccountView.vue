<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { apiClient } from '@/api/client';
import type { DireccionCliente } from '@/types';
import OrderHistoryPanel from '@/components/orders/OrderHistoryPanel.vue';
import { 
  User, 
  Mail, 
  Phone, 
  Sparkles, 
  ShoppingBag, 
  Package, 
  CheckCircle2, 
  Clock, 
  ChevronRight, 
  LogOut,
  ShieldCheck,
  Store,
  MapPin,
  Plus,
  Pencil,
  Trash2,
  Star,
  LocateFixed,
  Loader2,
  X,
  Save
} from 'lucide-vue-next';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const activeTab = ref<'perfil' | 'direcciones' | 'pedidos' | 'puntos'>('perfil');

const fidelidad = ref({ puntos_saldo: 0, regla_acumulacion_bob: 10, valor_punto_bob: 0.5 });

async function cargarFidelidad() {
  const clienteId = authStore.user?.id;
  fidelidad.value.puntos_saldo = authStore.pointsBalance;
  if (!clienteId) return;
  try {
    const { data } = await apiClient.get(`/api/v1/clientes/${clienteId}/fidelidad/puntos`);
    fidelidad.value = {
      puntos_saldo: Math.max(0, Number(data?.puntos_saldo) || 0),
      regla_acumulacion_bob: Math.max(1, Number(data?.regla_acumulacion_bob) || 10),
      valor_punto_bob: Math.max(0.01, Number(data?.valor_punto_bob) || 0.5)
    };
  } catch {
    // Keep the profile balance when the loyalty service is unreachable.
  }
}

const direcciones = ref<DireccionCliente[]>([]);
const cargandoDirecciones = ref(false);
const guardandoDireccion = ref(false);
const eliminandoDireccionId = ref<string | null>(null);
const direccionEditandoId = ref<string | null>(null);
const mostrarFormularioDireccion = ref(false);
const errorDireccion = ref('');
const mensajeDireccion = ref('');
const formularioDireccion = ref({
  direccion: '',
  referencia: '',
  ciudad: '',
  latitud: null as number | null,
  longitud: null as number | null,
  es_predeterminada: false
});

async function cargarDirecciones() {
  const clienteId = authStore.user?.id;
  if (!clienteId) return;
  cargandoDirecciones.value = true;
  errorDireccion.value = '';
  try {
    const { data } = await apiClient.get<DireccionCliente[]>(`/api/v1/clientes/${clienteId}/direcciones`);
    direcciones.value = data;
  } catch (error: any) {
    errorDireccion.value = error.response?.data?.detail || 'No se pudieron cargar tus direcciones.';
  } finally {
    cargandoDirecciones.value = false;
  }
}

function nuevaDireccion() {
  direccionEditandoId.value = null;
  mostrarFormularioDireccion.value = true;
  formularioDireccion.value = {
    direccion: '', referencia: '', ciudad: '', latitud: null, longitud: null,
    es_predeterminada: direcciones.value.length === 0
  };
  errorDireccion.value = '';
  mensajeDireccion.value = '';
}

function editarDireccion(direccion: DireccionCliente) {
  direccionEditandoId.value = direccion.id;
  mostrarFormularioDireccion.value = true;
  formularioDireccion.value = {
    direccion: direccion.direccion,
    referencia: direccion.referencia || '',
    ciudad: direccion.ciudad,
    latitud: direccion.latitud ?? null,
    longitud: direccion.longitud ?? null,
    es_predeterminada: direccion.es_predeterminada
  };
  errorDireccion.value = '';
  mensajeDireccion.value = '';
}

async function guardarDireccion() {
  const clienteId = authStore.user?.id;
  if (!clienteId) return;
  const form = formularioDireccion.value;
  if ((form.latitud === null) !== (form.longitud === null)) {
    errorDireccion.value = 'Ingresa latitud y longitud, o deja ambos campos vacíos.';
    return;
  }
  guardandoDireccion.value = true;
  errorDireccion.value = '';
  mensajeDireccion.value = '';
  const payload = {
    ...form,
    direccion: form.direccion.trim(),
    referencia: form.referencia.trim() || null,
    ciudad: form.ciudad.trim()
  };
  try {
    if (direccionEditandoId.value) {
      await apiClient.patch(`/api/v1/clientes/${clienteId}/direcciones/${direccionEditandoId.value}`, payload);
      mensajeDireccion.value = 'Dirección actualizada.';
    } else {
      await apiClient.post(`/api/v1/clientes/${clienteId}/direcciones`, payload);
      mensajeDireccion.value = 'Dirección guardada.';
    }
    direccionEditandoId.value = null;
    mostrarFormularioDireccion.value = false;
    formularioDireccion.value = { direccion: '', referencia: '', ciudad: '', latitud: null, longitud: null, es_predeterminada: false };
    await cargarDirecciones();
  } catch (error: any) {
    errorDireccion.value = error.response?.data?.detail || 'No se pudo guardar la dirección.';
  } finally {
    guardandoDireccion.value = false;
  }
}

async function marcarDireccionPredeterminada(direccion: DireccionCliente) {
  const clienteId = authStore.user?.id;
  if (!clienteId) return;
  try {
    await apiClient.patch(`/api/v1/clientes/${clienteId}/direcciones/${direccion.id}`, { es_predeterminada: true });
    await cargarDirecciones();
    mensajeDireccion.value = 'Dirección predeterminada actualizada.';
  } catch (error: any) {
    errorDireccion.value = error.response?.data?.detail || 'No se pudo actualizar la dirección predeterminada.';
  }
}

async function eliminarDireccion(direccion: DireccionCliente) {
  const clienteId = authStore.user?.id;
  if (!clienteId || !confirm(`¿Eliminar la dirección "${direccion.direccion}"?`)) return;
  eliminandoDireccionId.value = direccion.id;
  try {
    await apiClient.delete(`/api/v1/clientes/${clienteId}/direcciones/${direccion.id}`);
    await cargarDirecciones();
    mensajeDireccion.value = 'Dirección eliminada.';
  } catch (error: any) {
    errorDireccion.value = error.response?.data?.detail || 'No se pudo eliminar la dirección.';
  } finally {
    eliminandoDireccionId.value = null;
  }
}

function usarUbicacionActual() {
  if (!navigator.geolocation) {
    errorDireccion.value = 'Este navegador no permite obtener la ubicación.';
    return;
  }
  navigator.geolocation.getCurrentPosition(
    position => {
      formularioDireccion.value.latitud = Number(position.coords.latitude.toFixed(7));
      formularioDireccion.value.longitud = Number(position.coords.longitude.toFixed(7));
      errorDireccion.value = '';
    },
    () => { errorDireccion.value = 'No se pudo obtener la ubicación. Revisa los permisos del navegador.'; },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

onMounted(async () => {
  if (route.query.tab === 'pedidos') activeTab.value = 'pedidos';
  if (!authStore.isAuthenticated) return;
  await authStore.fetchProfile();
  await Promise.all([cargarDirecciones(), cargarFidelidad()]);
});

function handleLogout() {
  authStore.logout();
  router.push('/marketplace');
}
</script>

<template>
  <div class="space-y-6">
    <!-- Encabezado de Perfil / Bienvenida -->
    <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div class="flex items-center gap-4">
        <div class="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white text-2xl font-black shadow-md">
          {{ authStore.user?.nombre_completo.charAt(0).toUpperCase() || 'U' }}
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-xl font-extrabold text-slate-900 dark:text-white">
              {{ authStore.user?.nombre_completo || 'Mi Cuenta' }}
            </h1>
            <span 
              :class="[
                'text-[10px] uppercase tracking-wider font-extrabold px-2 py-0.5 rounded-full border',
                authStore.userRole === 'administrador' 
                  ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 border-indigo-200 dark:border-indigo-800'
                  : authStore.userRole === 'cajero'
                  ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 border-emerald-200 dark:border-emerald-800'
                  : 'bg-blue-50 dark:bg-blue-950/60 text-blue-600 border-blue-200 dark:border-blue-800'
              ]"
            >
              {{ authStore.userRole }}
            </span>
          </div>
          <p class="text-xs text-slate-400 font-medium mt-0.5">
            {{ authStore.user?.email }}
          </p>
        </div>
      </div>

      <!-- Tarjeta Resumen de Puntos y Acciones -->
      <div class="flex items-center gap-3">
        <!-- Saldo de Puntos -->
        <div class="px-4 py-2 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 border border-amber-200/80 dark:border-amber-900/50 rounded-xl flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-amber-500 text-white flex items-center justify-center shadow-sm">
            <Sparkles class="w-4 h-4" />
          </div>
          <div>
            <span class="text-[10px] text-amber-700 dark:text-amber-400 font-bold uppercase tracking-wider block">Puntos Acumulados</span>
            <span class="text-base font-black text-amber-900 dark:text-amber-300">{{ authStore.pointsBalance }} pts</span>
          </div>
        </div>

        <!-- Botón Cerrar Sesión -->
        <button
          @click="handleLogout"
          class="px-3.5 py-2 text-xs font-bold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50 border border-rose-200 dark:border-rose-900/60 rounded-xl flex items-center gap-1.5 transition-colors"
        >
          <LogOut class="w-3.5 h-3.5" /> Salir
        </button>
      </div>
    </div>

    <!-- Navegación por pestañas -->
    <div class="flex border-b border-slate-200 dark:border-slate-800 gap-6 text-sm font-bold">
      <button
        @click="activeTab = 'perfil'"
        :class="[
          'pb-3 border-b-2 transition-colors flex items-center gap-2',
          activeTab === 'perfil'
            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
        ]"
      >
        <User class="w-4 h-4" /> Datos Personales
      </button>

      <button
        @click="activeTab = 'direcciones'"
        :class="[
          'pb-3 border-b-2 transition-colors flex items-center gap-2',
          activeTab === 'direcciones'
            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
        ]"
      >
        <MapPin class="w-4 h-4" /> Direcciones
        <span class="text-[10px] px-1.5 py-0.2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-full font-extrabold">{{ direcciones.length }}</span>
      </button>

      <button
        @click="activeTab = 'pedidos'"
        :class="[
          'pb-3 border-b-2 transition-colors flex items-center gap-2',
          activeTab === 'pedidos'
            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
        ]"
      >
        <Package class="w-4 h-4" /> Mis Compras y Pedidos
      </button>

      <button
        @click="activeTab = 'puntos'"
        :class="[
          'pb-3 border-b-2 transition-colors flex items-center gap-2',
          activeTab === 'puntos'
            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
        ]"
      >
        <Sparkles class="w-4 h-4" /> Fidelización y Beneficios
      </button>
    </div>

    <!-- Contenido de las pestañas -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- PESTAÑA: DATOS PERSONALES -->
      <div v-if="activeTab === 'perfil'" class="lg:col-span-2 space-y-6">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 space-y-4">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">Información de la Cuenta</h3>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl space-y-1">
              <span class="text-[10px] font-bold text-slate-400 uppercase">Nombre Completo</span>
              <p class="text-xs font-semibold text-slate-800 dark:text-slate-200">{{ authStore.user?.nombre_completo }}</p>
            </div>

            <div class="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl space-y-1">
              <span class="text-[10px] font-bold text-slate-400 uppercase">Correo Electrónico</span>
              <p class="text-xs font-semibold text-slate-800 dark:text-slate-200">{{ authStore.user?.email }}</p>
            </div>

            <div class="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl space-y-1">
              <span class="text-[10px] font-bold text-slate-400 uppercase">Teléfono</span>
              <p class="text-xs font-semibold text-slate-800 dark:text-slate-200">{{ authStore.user?.telefono || 'No registrado' }}</p>
            </div>

            <div class="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl space-y-1">
              <span class="text-[10px] font-bold text-slate-400 uppercase">Tipo de Cliente</span>
              <p class="text-xs font-semibold text-slate-800 dark:text-slate-200 capitalize">{{ authStore.user?.tipo_cliente || 'Retail' }}</p>
            </div>
          </div>
        </div>

        <!-- Atajos de Rol Interno si es Colaborador -->
        <div v-if="authStore.userRole !== 'cliente'" class="bg-slate-900 text-white rounded-2xl p-5 shadow-lg space-y-3">
          <div class="flex items-center gap-2">
            <ShieldCheck class="w-5 h-5 text-indigo-400" />
            <h4 class="text-sm font-bold">Herramientas Asignadas por Rol ({{ authStore.userRole }})</h4>
          </div>
          <p class="text-xs text-slate-300">
            Tu cuenta posee privilegios internos en el ERP MaxiConecta. Puedes acceder a los módulos de trabajo autorizados:
          </p>
          <div class="flex flex-wrap gap-2 pt-1">
            <router-link
              v-if="authStore.hasRole(['cajero', 'administrador'])"
              to="/pos"
              class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg flex items-center gap-1.5"
            >
              <Store class="w-3.5 h-3.5" /> Ir a Terminal POS
            </router-link>

            <router-link
              v-if="authStore.hasRole(['administrador', 'gerente_comercial'])"
              to="/admin"
              class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg flex items-center gap-1.5"
            >
              <ShieldCheck class="w-3.5 h-3.5" /> Ir a Panel Administrativo
            </router-link>
          </div>
        </div>
      </div>

      <!-- PESTAÑA: MIS PEDIDOS -->
      <div v-else-if="activeTab === 'direcciones'" class="lg:col-span-2 space-y-4">
        <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <header class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
                <MapPin class="h-4 w-4 text-blue-600" /> Mis direcciones de entrega
              </h3>
              <p class="mt-1 text-xs text-slate-500">Guarda referencias y coordenadas para agilizar tus entregas.</p>
            </div>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-700"
              @click="nuevaDireccion"
            >
              <Plus class="h-4 w-4" /> Nueva dirección
            </button>
          </header>

          <p v-if="errorDireccion" role="alert" class="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
            {{ errorDireccion }}
          </p>
          <p v-if="mensajeDireccion" role="status" class="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
            {{ mensajeDireccion }}
          </p>

          <form v-if="mostrarFormularioDireccion || !direcciones.length" class="mb-5 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50" @submit.prevent="guardarDireccion">
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label class="space-y-1 sm:col-span-2">
                <span class="block text-xs font-semibold text-slate-700 dark:text-slate-300">Dirección *</span>
                <input v-model="formularioDireccion.direccion" required minlength="3" maxlength="255" placeholder="Calle, avenida y número" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
              </label>
              <label class="space-y-1">
                <span class="block text-xs font-semibold text-slate-700 dark:text-slate-300">Ciudad *</span>
                <input v-model="formularioDireccion.ciudad" required minlength="2" maxlength="100" placeholder="La Paz" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
              </label>
              <label class="space-y-1">
                <span class="block text-xs font-semibold text-slate-700 dark:text-slate-300">Referencia</span>
                <input v-model="formularioDireccion.referencia" maxlength="500" placeholder="Edificio, piso, timbre o punto de referencia" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
              </label>
              <label class="space-y-1">
                <span class="block text-xs font-semibold text-slate-700 dark:text-slate-300">Latitud</span>
                <input v-model.number="formularioDireccion.latitud" type="number" min="-90" max="90" step="0.0000001" placeholder="-16.5000000" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
              </label>
              <label class="space-y-1">
                <span class="block text-xs font-semibold text-slate-700 dark:text-slate-300">Longitud</span>
                <input v-model.number="formularioDireccion.longitud" type="number" min="-180" max="180" step="0.0000001" placeholder="-68.1500000" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
              </label>
            </div>
            <div class="flex flex-col gap-3 border-t border-slate-200 pt-3 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
              <div class="flex flex-wrap items-center gap-4">
                <label class="inline-flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <input v-model="formularioDireccion.es_predeterminada" type="checkbox" class="rounded border-slate-300 text-blue-600" />
                  Dirección predeterminada
                </label>
                <button type="button" class="inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:underline dark:text-blue-400" @click="usarUbicacionActual">
                  <LocateFixed class="h-3.5 w-3.5" /> Usar mi ubicación
                </button>
              </div>
              <div class="flex justify-end gap-2">
                <button v-if="direcciones.length" type="button" class="rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-white dark:hover:bg-slate-700" @click="mostrarFormularioDireccion = false; direccionEditandoId = null; formularioDireccion = { direccion: '', referencia: '', ciudad: '', latitud: null, longitud: null, es_predeterminada: false }">Cancelar</button>
                <button type="submit" :disabled="guardandoDireccion" class="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50">
                  <Loader2 v-if="guardandoDireccion" class="h-3.5 w-3.5 animate-spin" />
                  <Save v-else class="h-3.5 w-3.5" />
                  {{ guardandoDireccion ? 'Guardando...' : direccionEditandoId ? 'Guardar cambios' : 'Guardar dirección' }}
                </button>
              </div>
            </div>
          </form>

          <div v-if="cargandoDirecciones" class="flex items-center justify-center gap-2 py-8 text-xs text-slate-500">
            <Loader2 class="h-4 w-4 animate-spin" /> Cargando direcciones...
          </div>
          <div v-else-if="direcciones.length" class="divide-y divide-slate-100 dark:divide-slate-800">
            <article v-for="direccion in direcciones" :key="direccion.id" class="flex flex-col gap-3 py-4 first:pt-0 sm:flex-row sm:items-start sm:justify-between">
              <div class="flex min-w-0 gap-3">
                <span class="mt-0.5 rounded-lg bg-blue-50 p-2 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"><MapPin class="h-4 w-4" /></span>
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <h4 class="text-sm font-bold text-slate-900 dark:text-white">{{ direccion.direccion }}</h4>
                    <span v-if="direccion.es_predeterminada" class="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"><Star class="h-3 w-3 fill-current" /> Predeterminada</span>
                  </div>
                  <p class="mt-0.5 text-xs text-slate-600 dark:text-slate-300">{{ direccion.ciudad }}</p>
                  <p v-if="direccion.referencia" class="mt-1 text-xs text-slate-500">Referencia: {{ direccion.referencia }}</p>
                  <p v-if="direccion.latitud !== null && direccion.longitud !== null" class="mt-1 text-[11px] font-mono text-slate-400">{{ direccion.latitud }}, {{ direccion.longitud }}</p>
                </div>
              </div>
              <div class="flex flex-wrap items-center gap-1 sm:justify-end">
                <button v-if="!direccion.es_predeterminada" type="button" class="rounded-md px-2 py-1.5 text-[11px] font-semibold text-amber-700 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-950/30" @click="marcarDireccionPredeterminada(direccion)">Hacer predeterminada</button>
                <button type="button" class="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-blue-700 dark:hover:bg-slate-800" title="Editar dirección" @click="editarDireccion(direccion)"><Pencil class="h-4 w-4" /></button>
                <button type="button" :disabled="eliminandoDireccionId === direccion.id" class="rounded-md p-2 text-rose-500 hover:bg-rose-50 disabled:opacity-50 dark:hover:bg-rose-950/30" title="Eliminar dirección" @click="eliminarDireccion(direccion)"><Trash2 class="h-4 w-4" /></button>
              </div>
            </article>
          </div>
          <div v-else class="rounded-xl border border-dashed border-slate-300 px-4 py-8 text-center text-xs text-slate-500 dark:border-slate-700">
            Aún no tienes direcciones guardadas. Registra una para tus entregas.
          </div>
        </section>
      </div>

      <!-- PESTAÑA: MIS PEDIDOS -->
      <div v-else-if="activeTab === 'pedidos'" class="lg:col-span-2 space-y-4">
        <OrderHistoryPanel :page-size="8" />
      </div>

      <!-- PESTAÑA: PUNTOS Y BENEFICIOS -->
      <div v-else class="lg:col-span-2 space-y-4">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 space-y-4">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">Programa de Fidelización MaxiPuntos</h3>
          
          <div class="p-4 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/40 dark:to-orange-950/40 border border-amber-200/70 rounded-xl flex items-center justify-between">
            <div>
              <span class="text-xs font-bold text-amber-900 dark:text-amber-200">Tu Saldo Disponible</span>
              <p class="text-2xl font-black text-amber-600">{{ fidelidad.puntos_saldo }} Puntos</p>
              <p class="text-[11px] text-amber-700 dark:text-amber-300 mt-1">Equivalente a BOB {{ (fidelidad.puntos_saldo * fidelidad.valor_punto_bob).toFixed(2) }} de descuento directo en checkout.</p>
            </div>
            <Sparkles class="w-10 h-10 text-amber-500 opacity-75" />
          </div>

          <div class="space-y-2 pt-2">
            <h4 class="text-xs font-bold text-slate-700 dark:text-slate-300">¿Cómo funcionan tus puntos?</h4>
            <ul class="text-xs text-slate-500 space-y-1.5 list-disc list-inside">
              <li>Ganas 1 punto por cada BOB {{ fidelidad.regla_acumulacion_bob }} de compra confirmada.</li>
              <li>Cada punto vale BOB {{ fidelidad.valor_punto_bob.toFixed(2) }} y lo canjeas al pagar en el checkout.</li>
              <li>Al registrarte recibes una bonificación de bienvenida de 50 puntos.</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Panel Lateral Informativo -->
      <div class="space-y-4">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 space-y-3">
          <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400">Seguridad & Sesión</h4>
          <div class="space-y-2 text-xs">
            <div class="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
              <span class="text-slate-400">Estado:</span>
              <span class="text-emerald-600 font-bold flex items-center gap-1">
                <CheckCircle2 class="w-3 h-3" /> Conectado (JWT)
              </span>
            </div>
            <div class="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
              <span class="text-slate-400">Rol:</span>
              <span class="font-bold capitalize">{{ authStore.userRole }}</span>
            </div>
            <div class="flex justify-between py-1">
              <span class="text-slate-400">Protección:</span>
              <span class="text-slate-600 dark:text-slate-300 font-medium">Supabase Auth / RBAC</span>
            </div>
          </div>
        </div>

        <div class="bg-blue-50 dark:bg-blue-950/40 rounded-2xl p-5 border border-blue-100 dark:border-blue-900/50 space-y-2">
          <h4 class="text-xs font-bold text-blue-900 dark:text-blue-300 flex items-center gap-1.5">
            <ShoppingBag class="w-4 h-4" /> ¿Deseas seguir comprando?
          </h4>
          <p class="text-[11px] text-blue-700 dark:text-blue-400">
            Explora las novedades y ofertas en tecnología de nuestro catálogo oficial.
          </p>
          <router-link
            to="/marketplace"
            class="inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-800 dark:text-blue-400 pt-1"
          >
            Ir al Marketplace <ChevronRight class="w-3.5 h-3.5" />
          </router-link>
        </div>
      </div>
    </div>

  </div>
</template>
