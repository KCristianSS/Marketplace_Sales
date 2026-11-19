<script setup lang="ts">
import { useNotificationMessage } from '@/lib/feedback';
import { ref, computed, onMounted } from 'vue';
import { 
  getAdminUsuarios, 
  createAdminUsuario, 
  updateAdminUsuario, 
  deleteAdminUsuario,
  type UsuarioInterno 
} from '@/api/client';
import { 
  Users, 
  ShieldCheck, 
  Store, 
  Briefcase, 
  Plus, 
  Search, 
  Filter, 
  Edit3, 
  Trash2, 
  Key, 
  Copy, 
  Check, 
  AlertTriangle, 
  CheckCircle2, 
  RotateCcw, 
  Loader2, 
  X, 
  ShieldAlert, 
  Building2, 
  Lock, 
  Eye, 
  UserX, 
  UserCheck 
} from 'lucide-vue-next';

// Sucursales oficiales de MaxiConecta para asignación
const SUCURSALES_DISPONIBLES = [
  { id: 'SUC-01', nombre: 'Sucursal Central - La Paz (Av. Mariscal Santa Cruz)', ciudad: 'La Paz' },
  { id: 'SUC-02', nombre: 'Sucursal San Miguel - Calacoto (Calle 21)', ciudad: 'La Paz' },
  { id: 'SUC-03', nombre: 'Sucursal Equipetrol - Santa Cruz (Av. San Martín)', ciudad: 'Santa Cruz' },
  { id: 'SUC-04', nombre: 'Sucursal Cala Cala - Cochabamba (Av. América)', ciudad: 'Cochabamba' }
];

// Estado de la lista y filtros
const usuarios = ref<UsuarioInterno[]>([]);
const cargando = ref(true);
const filtroRol = ref<string>('todos');
const filtroEstado = ref<string>('todos');
const filtroSucursal = ref<string>('todas');
const busqueda = ref('');

// Modales
const modalCrearAbierto = ref(false);
const modalEditarAbierto = ref(false);
const modalCredencialAbierto = ref(false);
const modalConfirmarDesactivar = ref(false);

const guardando = ref(false);
const usuarioSeleccionado = ref<UsuarioInterno | null>(null);
const mensajeExito = useNotificationMessage<string | null>('success', null);
const mensajeError = useNotificationMessage<string | null>('error', null);

// Formulario de creación
const formCrear = ref({
  nombre_completo: '',
  email: '',
  rol: 'cajero',
  sucursal_id: 'SUC-01',
  debe_cambiar_password: true
});

// Formulario de edición
const formEditar = ref({
  id: '',
  nombre_completo: '',
  email: '',
  rol: 'cajero',
  sucursal_id: '',
  activo: true,
  debe_cambiar_password: true
});

// Credencial temporal recién creada
const credencialGenerada = ref<{
  nombre: string;
  email: string;
  rol: string;
  sucursal: string;
  passwordTemporal: string;
} | null>(null);

const copiado = ref(false);

// Métricas computadas
const totalColaboradores = computed(() => usuarios.value.length);
const totalActivos = computed(() => usuarios.value.filter(u => u.activo).length);
const totalCajeros = computed(() => usuarios.value.filter(u => u.rol === 'cajero' && u.activo).length);
const totalGerentes = computed(() => usuarios.value.filter(u => u.rol === 'gerente_comercial' && u.activo).length);
const totalAdmins = computed(() => usuarios.value.filter(u => u.rol === 'administrador' && u.activo).length);

// Lista filtrada
const usuariosFiltrados = computed(() => {
  return usuarios.value.filter(u => {
    if (filtroRol.value !== 'todos' && u.rol !== filtroRol.value) return false;
    if (filtroEstado.value === 'activos' && !u.activo) return false;
    if (filtroEstado.value === 'inactivos' && u.activo) return false;
    if (filtroSucursal.value !== 'todas' && u.sucursal_id !== filtroSucursal.value) return false;
    if (busqueda.value.trim()) {
      const q = busqueda.value.toLowerCase().trim();
      const matchNombre = u.nombre_completo.toLowerCase().includes(q);
      const matchEmail = u.email.toLowerCase().includes(q);
      if (!matchNombre && !matchEmail) return false;
    }
    return true;
  });
});

// Cargar usuarios desde la API
async function cargarUsuarios() {
  cargando.value = true;
  mensajeError.value = null;
  try {
    const data = await getAdminUsuarios();
    usuarios.value = data;
  } catch (err: any) {
    console.error('Error cargando usuarios internos:', err);
    mensajeError.value = err.response?.data?.detail || 'Error al conectar con el servicio de administración de usuarios.';
  } finally {
    cargando.value = false;
  }
}

// Abrir modal de creación
function abrirModalCrear() {
  formCrear.value = {
    nombre_completo: '',
    email: '',
    rol: 'cajero',
    sucursal_id: 'SUC-01',
    debe_cambiar_password: true
  };
  mensajeError.value = null;
  modalCrearAbierto.value = true;
}

// Guardar nuevo usuario
async function guardarNuevoUsuario() {
  if (!formCrear.value.nombre_completo.trim()) {
    mensajeError.value = 'El nombre completo del colaborador es obligatorio.';
    return;
  }
  if (!formCrear.value.email.trim() || !formCrear.value.email.includes('@')) {
    mensajeError.value = 'Debe ingresar un correo electrónico corporativo válido.';
    return;
  }
  if (formCrear.value.rol === 'cajero' && !formCrear.value.sucursal_id) {
    mensajeError.value = 'La asignación de sucursal física es obligatoria para el rol de Cajero.';
    return;
  }

  guardando.value = true;
  mensajeError.value = null;

  try {
    const sucursalObj = SUCURSALES_DISPONIBLES.find(s => s.id === formCrear.value.sucursal_id);
    const sucursalNombre = formCrear.value.rol === 'cajero' && sucursalObj 
      ? sucursalObj.nombre 
      : 'Acceso Corporativo Global';

    const resp = await createAdminUsuario({
      nombre_completo: formCrear.value.nombre_completo.trim(),
      email: formCrear.value.email.trim().toLowerCase(),
      rol: formCrear.value.rol,
      sucursal_id: formCrear.value.rol === 'cajero' ? formCrear.value.sucursal_id : null,
      sucursal_nombre: sucursalNombre,
      debe_cambiar_password: formCrear.value.debe_cambiar_password
    });

    modalCrearAbierto.value = false;

    // Mostrar modal con la credencial temporal
    credencialGenerada.value = {
      nombre: resp.nombre_completo,
      email: resp.email,
      rol: resp.rol,
      sucursal: resp.sucursal_nombre || 'Acceso Global',
      passwordTemporal: resp.password_temporal || ''
    };
    modalCredencialAbierto.value = true;

    mensajeExito.value = `Usuario ${resp.nombre_completo} creado exitosamente con contraseña temporal y auditoría registrada.`;
    await cargarUsuarios();

    setTimeout(() => {
      mensajeExito.value = null;
    }, 6000);
  } catch (err: any) {
    console.error('Error al crear usuario:', err);
    mensajeError.value = err.response?.data?.detail || err.message || 'Error al dar de alta el usuario interno.';
  } finally {
    guardando.value = false;
  }
}

// Abrir modal de edición
function abrirModalEditar(u: UsuarioInterno) {
  formEditar.value = {
    id: u.id,
    nombre_completo: u.nombre_completo,
    email: u.email,
    rol: u.rol,
    sucursal_id: u.sucursal_id || (u.rol === 'cajero' ? 'SUC-01' : ''),
    activo: u.activo,
    debe_cambiar_password: u.debe_cambiar_password
  };
  mensajeError.value = null;
  modalEditarAbierto.value = true;
}

// Guardar edición
async function guardarEdicion() {
  if (formEditar.value.rol === 'cajero' && !formEditar.value.sucursal_id) {
    mensajeError.value = 'El rol de cajero exige asignar una sucursal física.';
    return;
  }

  guardando.value = true;
  mensajeError.value = null;

  try {
    const sucursalObj = SUCURSALES_DISPONIBLES.find(s => s.id === formEditar.value.sucursal_id);
    const sucursalNombre = formEditar.value.rol === 'cajero' && sucursalObj 
      ? sucursalObj.nombre 
      : 'Acceso Corporativo Global';

    const resp = await updateAdminUsuario(formEditar.value.id, {
      nombre_completo: formEditar.value.nombre_completo.trim(),
      rol: formEditar.value.rol as any,
      sucursal_id: formEditar.value.rol === 'cajero' ? formEditar.value.sucursal_id : null,
      sucursal_nombre: sucursalNombre,
      activo: formEditar.value.activo,
      debe_cambiar_password: formEditar.value.debe_cambiar_password
    });

    modalEditarAbierto.value = false;
    mensajeExito.value = `Usuario ${resp.nombre_completo} actualizado correctamente. Operación auditada.`;
    await cargarUsuarios();

    setTimeout(() => {
      mensajeExito.value = null;
    }, 5000);
  } catch (err: any) {
    console.error('Error al editar usuario:', err);
    mensajeError.value = err.response?.data?.detail || err.message || 'Error al actualizar usuario interno.';
  } finally {
    guardando.value = false;
  }
}

// Confirmar desactivación (revoca sesión)
function solicitarDesactivar(u: UsuarioInterno) {
  usuarioSeleccionado.value = u;
  modalConfirmarDesactivar.value = true;
}

async function ejecutarDesactivacion() {
  if (!usuarioSeleccionado.value) return;
  guardando.value = true;
  try {
    const resp = await deleteAdminUsuario(usuarioSeleccionado.value.id);
    modalConfirmarDesactivar.value = false;
    mensajeExito.value = `El colaborador ${resp.nombre_completo} fue desactivado y su sesión activa se revocó de inmediato.`;
    await cargarUsuarios();

    setTimeout(() => {
      mensajeExito.value = null;
    }, 6000);
  } catch (err: any) {
    console.error('Error desactivando usuario:', err);
    mensajeError.value = err.response?.data?.detail || 'Error al desactivar al colaborador.';
  } finally {
    guardando.value = false;
    usuarioSeleccionado.value = null;
  }
}

// Reactivar usuario inactivo
async function reactivarUsuario(u: UsuarioInterno) {
  guardando.value = true;
  try {
    await updateAdminUsuario(u.id, { activo: true });
    mensajeExito.value = `Colaborador ${u.nombre_completo} reactivado exitosamente.`;
    await cargarUsuarios();
    setTimeout(() => {
      mensajeExito.value = null;
    }, 5000);
  } catch (err: any) {
    console.error('Error reactivando usuario:', err);
    mensajeError.value = err.response?.data?.detail || 'Error al reactivar usuario.';
  } finally {
    guardando.value = false;
  }
}

// Copiar contraseña temporal al portapapeles
function copiarCredencial() {
  if (!credencialGenerada.value) return;
  const texto = `Acceso MaxiConecta ERP:\nUsuario: ${credencialGenerada.value.email}\nContraseña Temporal: ${credencialGenerada.value.passwordTemporal}\nRol: ${credencialGenerada.value.rol.toUpperCase()}\n*Nota: Deberá cambiar su contraseña en el primer ingreso.*`;
  navigator.clipboard.writeText(texto);
  copiado.value = true;
  setTimeout(() => {
    copiado.value = false;
  }, 3000);
}

onMounted(() => {
  cargarUsuarios();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Header principal -->
    <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div class="flex items-start gap-4">
        <div class="w-12 h-12 rounded-xl bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0 border border-purple-100 dark:border-purple-900/50 shadow-sm">
          <ShieldCheck class="w-6 h-6" />
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h2 class="text-lg font-extrabold text-slate-900 dark:text-white">
              Gestión de Usuarios Internos y Roles
            </h2>
            <span class="text-[10px] font-extrabold tracking-wider uppercase px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300">
              RF-49 / KAN-421
            </span>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
            Control centralizado de acceso para Cajeros (POS), Gerentes Comerciales y Administradores. Altas con contraseña temporal, asignación de sucursal física y revocación inmediata de sesiones.
          </p>
        </div>
      </div>

      <!-- Botón de Alta -->
      <button
        @click="abrirModalCrear"
        class="px-4 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white text-xs font-extrabold rounded-xl shadow-md shadow-purple-500/20 flex items-center gap-2 transition-all hover:scale-[1.02] shrink-0"
      >
        <Plus class="w-4 h-4" /> Nuevo Colaborador
      </button>
    </div>

    <!-- KPIs rápidos de usuarios -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-white dark:bg-slate-900 rounded-xl p-4 border border-slate-200 dark:border-slate-800 shadow-xs">
        <span class="text-[10px] font-bold text-slate-400 uppercase block">Total Colaboradores</span>
        <div class="flex items-baseline justify-between mt-1">
          <span class="text-xl font-black text-slate-900 dark:text-white">{{ totalColaboradores }}</span>
          <span class="text-xs font-bold text-emerald-600">{{ totalActivos }} activos</span>
        </div>
      </div>

      <div class="bg-white dark:bg-slate-900 rounded-xl p-4 border border-slate-200 dark:border-slate-800 shadow-xs">
        <span class="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 uppercase block flex items-center gap-1">
          <Store class="w-3.5 h-3.5" /> Cajeros POS
        </span>
        <div class="flex items-baseline justify-between mt-1">
          <span class="text-xl font-black text-emerald-700 dark:text-emerald-300">{{ totalCajeros }}</span>
          <span class="text-[10px] text-slate-400">Asignados a tienda</span>
        </div>
      </div>

      <div class="bg-white dark:bg-slate-900 rounded-xl p-4 border border-slate-200 dark:border-slate-800 shadow-xs">
        <span class="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase block flex items-center gap-1">
          <Briefcase class="w-3.5 h-3.5" /> Gerentes Comerciales
        </span>
        <div class="flex items-baseline justify-between mt-1">
          <span class="text-xl font-black text-blue-700 dark:text-blue-300">{{ totalGerentes }}</span>
          <span class="text-[10px] text-slate-400">Precios y Reportes</span>
        </div>
      </div>

      <div class="bg-white dark:bg-slate-900 rounded-xl p-4 border border-slate-200 dark:border-slate-800 shadow-xs">
        <span class="text-[10px] font-bold text-purple-600 dark:text-purple-400 uppercase block flex items-center gap-1">
          <ShieldCheck class="w-3.5 h-3.5" /> Administradores
        </span>
        <div class="flex items-baseline justify-between mt-1">
          <span class="text-xl font-black text-purple-700 dark:text-purple-300">{{ totalAdmins }}</span>
          <span class="text-[10px] text-slate-400">Control Global</span>
        </div>
      </div>
    </div>






    <!-- Barra de Filtros y Búsqueda -->
    <div class="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 shadow-xs flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
      <div class="flex-1 relative">
        <Search class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          v-model="busqueda"
          type="text"
          placeholder="Buscar por nombre o correo electrónico corporativo..."
          class="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-hidden focus:border-purple-500"
        />
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <!-- Filtro Rol -->
        <select
          v-model="filtroRol"
          class="px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold focus:outline-hidden"
        >
          <option value="todos">Todos los Roles</option>
          <option value="cajero">Cajero POS</option>
          <option value="gerente_comercial">Gerente Comercial</option>
          <option value="administrador">Administrador</option>
        </select>

        <!-- Filtro Estado -->
        <select
          v-model="filtroEstado"
          class="px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold focus:outline-hidden"
        >
          <option value="todos">Todos los Estados</option>
          <option value="activos">Solo Activos</option>
          <option value="inactivos">Solo Inactivos</option>
        </select>

        <!-- Filtro Sucursal -->
        <select
          v-model="filtroSucursal"
          class="px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold focus:outline-hidden"
        >
          <option value="todas">Todas las Sucursales</option>
          <option v-for="suc in SUCURSALES_DISPONIBLES" :key="suc.id" :value="suc.id">
            {{ suc.ciudad }} - {{ suc.id }}
          </option>
        </select>

        <button
          @click="cargarUsuarios"
          :disabled="cargando"
          class="p-2 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-500 hover:text-slate-800 dark:hover:text-white transition-colors"
          title="Recargar lista"
        >
          <RotateCcw :class="['w-4 h-4', cargando ? 'animate-spin' : '']" />
        </button>
      </div>
    </div>

    <!-- Spinner de carga -->
    <div v-if="cargando" class="bg-white dark:bg-slate-900 rounded-2xl p-12 border border-slate-200 dark:border-slate-800 flex flex-col items-center justify-center space-y-3">
      <Loader2 class="w-8 h-8 text-purple-600 animate-spin" />
      <p class="text-xs font-semibold text-slate-500">Cargando directorio de usuarios internos...</p>
    </div>

    <!-- Tabla de Colaboradores -->
    <div v-else class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 text-slate-400 font-bold uppercase text-[10px]">
            <tr>
              <th class="px-5 py-3">Colaborador</th>
              <th class="px-4 py-3">Rol del Sistema</th>
              <th class="px-4 py-3">Sucursal Asignada</th>
              <th class="px-4 py-3">Estado de Cuenta</th>
              <th class="px-4 py-3">Seguridad</th>
              <th class="px-5 py-3 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
            <tr 
              v-for="u in usuariosFiltrados" 
              :key="u.id"
              :class="[
                'hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors',
                !u.activo ? 'opacity-60 bg-rose-50/20 dark:bg-rose-950/10' : ''
              ]"
            >
              <!-- Nombre y correo -->
              <td class="px-5 py-3.5">
                <div class="flex items-center gap-3">
                  <div 
                    :class="[
                      'w-9 h-9 rounded-xl flex items-center justify-center text-xs font-black shadow-xs shrink-0',
                      u.rol === 'administrador'
                        ? 'bg-purple-600 text-white'
                        : u.rol === 'gerente_comercial'
                        ? 'bg-blue-600 text-white'
                        : 'bg-emerald-600 text-white'
                    ]"
                  >
                    {{ u.nombre_completo.charAt(0).toUpperCase() }}
                  </div>
                  <div>
                    <span class="font-extrabold text-slate-900 dark:text-white block">
                      {{ u.nombre_completo }}
                    </span>
                    <span class="text-[11px] text-slate-400 font-mono">
                      {{ u.email }}
                    </span>
                  </div>
                </div>
              </td>

              <!-- Rol -->
              <td class="px-4 py-3.5">
                <span 
                  :class="[
                    'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-extrabold border uppercase tracking-wider',
                    u.rol === 'administrador'
                      ? 'bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800'
                      : u.rol === 'gerente_comercial'
                      ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800'
                      : 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                  ]"
                >
                  <ShieldCheck v-if="u.rol === 'administrador'" class="w-3 h-3" />
                  <Briefcase v-else-if="u.rol === 'gerente_comercial'" class="w-3 h-3" />
                  <Store v-else class="w-3 h-3" />
                  {{ u.rol.replace('_', ' ') }}
                </span>
              </td>

              <!-- Sucursal -->
              <td class="px-4 py-3.5">
                <div v-if="u.rol === 'cajero'" class="space-y-0.5">
                  <span class="font-extrabold text-slate-800 dark:text-slate-200 flex items-center gap-1">
                    <Building2 class="w-3.5 h-3.5 text-emerald-600" />
                    {{ u.sucursal_nombre || u.sucursal_id }}
                  </span>
                  <span class="text-[10px] text-slate-400 block font-mono">Código: {{ u.sucursal_id }}</span>
                </div>
                <div v-else class="text-slate-400 text-[11px] italic flex items-center gap-1">
                  <Building2 class="w-3.5 h-3.5 text-slate-400" /> Acceso Global / Todas las Sucursales
                </div>
              </td>

              <!-- Estado -->
              <td class="px-4 py-3.5">
                <div class="flex items-center gap-1.5">
                  <span 
                    :class="[
                      'w-2 h-2 rounded-full shrink-0',
                      u.activo ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
                    ]"
                  />
                  <span 
                    :class="[
                      'text-xs font-bold',
                      u.activo ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                    ]"
                  >
                    {{ u.activo ? 'Activo' : 'Desactivado' }}
                  </span>
                </div>
                <span v-if="u.sesion_revocada && !u.activo" class="text-[9px] text-rose-500 font-semibold block">
                  Sesión revocada
                </span>
              </td>

              <!-- Seguridad (Cambio de contraseña) -->
              <td class="px-4 py-3.5">
                <span 
                  v-if="u.debe_cambiar_password" 
                  class="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 rounded-md border border-amber-200 dark:border-amber-800"
                >
                  <Lock class="w-3 h-3" /> Cambio en 1er ingreso
                </span>
                <span v-else class="text-[10px] text-slate-400 flex items-center gap-1">
                  <CheckCircle2 class="w-3 h-3 text-slate-400" /> Contraseña establecida
                </span>
              </td>

              <!-- Acciones -->
              <td class="px-5 py-3.5 text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <button
                    @click="abrirModalEditar(u)"
                    class="p-1.5 text-slate-500 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                    title="Editar colaborador"
                  >
                    <Edit3 class="w-4 h-4" />
                  </button>

                  <button
                    v-if="u.activo"
                    @click="solicitarDesactivar(u)"
                    class="p-1.5 text-rose-500 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/50 rounded-lg transition-colors"
                    title="Desactivar y revocar sesión"
                  >
                    <UserX class="w-4 h-4" />
                  </button>

                  <button
                    v-else
                    @click="reactivarUsuario(u)"
                    class="p-1.5 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-950/50 rounded-lg transition-colors"
                    title="Reactivar usuario"
                  >
                    <UserCheck class="w-4 h-4" />
                  </button>
                </div>
              </td>
            </tr>

            <!-- Vacío -->
            <tr v-if="usuariosFiltrados.length === 0">
              <td colspan="6" class="px-6 py-10 text-center text-slate-400 text-xs">
                No se encontraron colaboradores internos que coincidan con los filtros aplicados.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pie informativo de auditoría -->
      <div class="p-3 bg-slate-50 dark:bg-slate-800/40 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
        <span class="flex items-center gap-1.5">
          <ShieldAlert class="w-3.5 h-3.5 text-purple-500" /> Todas las altas, cambios de rol y revocaciones quedan registradas en la tabla <code>audit_logs</code>.
        </span>
        <span>Mostrando {{ usuariosFiltrados.length }} de {{ totalColaboradores }} colaboradores</span>
      </div>
    </div>

    <!-- MODAL 1: ALTA DE NUEVO COLABORADOR -->
    <div 
      v-if="modalCrearAbierto" 
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-fadeIn"
    >
      <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full p-6 border border-slate-200 dark:border-slate-800 shadow-2xl space-y-5">
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-purple-600 text-white flex items-center justify-center">
              <Plus class="w-4 h-4" />
            </div>
            <div>
              <h3 class="text-sm font-extrabold text-slate-900 dark:text-white">Alta de Usuario Interno</h3>
              <p class="text-[11px] text-slate-400">Genera cuenta con contraseña temporal y auditoría</p>
            </div>
          </div>
          <button @click="modalCrearAbierto = false" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="space-y-4">
          <!-- Nombre Completo -->
          <div>
            <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">
              Nombre Completo <span class="text-rose-500">*</span>
            </label>
            <input
              v-model="formCrear.nombre_completo"
              type="text"
              placeholder="Ej. Roberto Morales Soliz"
              class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-hidden focus:border-purple-500"
            />
          </div>

          <!-- Correo Corporativo -->
          <div>
            <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">
              Correo Electrónico Corporativo <span class="text-rose-500">*</span>
            </label>
            <input
              v-model="formCrear.email"
              type="email"
              placeholder="ejemplo@maxiconecta.bo"
              class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-hidden focus:border-purple-500"
            />
          </div>

          <!-- Selección de Rol -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">
                Rol del Sistema <span class="text-rose-500">*</span>
              </label>
              <select
                v-model="formCrear.rol"
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white font-bold focus:outline-hidden"
              >
                <option value="cajero">Cajero (POS Terminal)</option>
                <option value="gerente_comercial">Gerente Comercial (ERP)</option>
                <option value="administrador">Administrador (Total)</option>
              </select>
            </div>

            <!-- Sucursal Física Asignada -->
            <div>
              <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">
                Sucursal Asignada <span v-if="formCrear.rol === 'cajero'" class="text-rose-500">*</span>
              </label>
              <select
                v-model="formCrear.sucursal_id"
                :disabled="formCrear.rol !== 'cajero'"
                :class="[
                  'w-full px-3 py-2 text-xs rounded-xl border font-bold focus:outline-hidden',
                  formCrear.rol !== 'cajero'
                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 border-slate-200 dark:border-slate-700 cursor-not-allowed'
                    : 'bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white border-slate-200 dark:border-slate-700'
                ]"
              >
                <option v-for="suc in SUCURSALES_DISPONIBLES" :key="suc.id" :value="suc.id">
                  {{ suc.nombre }}
                </option>
              </select>
              <p v-if="formCrear.rol !== 'cajero'" class="text-[10px] text-slate-400 mt-1">
                Los roles gerenciales y de administración tienen acceso a todas las sucursales.
              </p>
            </div>
          </div>

          <div class="rounded-xl border border-purple-100 bg-purple-50/60 p-3 text-xs text-slate-700 dark:border-purple-900/40 dark:bg-purple-950/30 dark:text-slate-300">
            <span class="block font-bold text-purple-900 dark:text-purple-300">Cambio de contraseña en el primer ingreso</span>
            El colaborador deberá cambiar la contraseña temporal al iniciar sesión.
          </div>
        </div>

        <div class="flex items-center justify-end gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
          <button
            @click="modalCrearAbierto = false"
            type="button"
            class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            Cancelar
          </button>
          <button
            @click="guardarNuevoUsuario"
            :disabled="guardando"
            type="button"
            class="px-5 py-2 text-xs font-extrabold bg-purple-600 hover:bg-purple-700 text-white rounded-xl shadow-md shadow-purple-500/20 flex items-center gap-2 transition-all"
          >
            <Loader2 v-if="guardando" class="w-4 h-4 animate-spin" />
            <span v-else>Generar Cuenta y Contraseña</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL 2: EDICIÓN DE COLABORADOR -->
    <div 
      v-if="modalEditarAbierto" 
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-fadeIn"
    >
      <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full p-6 border border-slate-200 dark:border-slate-800 shadow-2xl space-y-5">
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center">
              <Edit3 class="w-4 h-4" />
            </div>
            <div>
              <h3 class="text-sm font-extrabold text-slate-900 dark:text-white">Modificar Usuario Interno</h3>
              <p class="text-[11px] text-slate-400">Actualiza rol, sucursal o estado</p>
            </div>
          </div>
          <button @click="modalEditarAbierto = false" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="space-y-4">
          <div>
            <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">Nombre Completo</label>
            <input
              v-model="formEditar.nombre_completo"
              type="text"
              class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-hidden"
            />
          </div>

          <div>
            <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">Correo Electrónico (No editable)</label>
            <input
              :value="formEditar.email"
              disabled
              type="email"
              class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-400 font-mono cursor-not-allowed"
            />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">Rol</label>
              <select
                v-model="formEditar.rol"
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white font-bold focus:outline-hidden"
              >
                <option value="cajero">Cajero (POS Terminal)</option>
                <option value="gerente_comercial">Gerente Comercial (ERP)</option>
                <option value="administrador">Administrador (Total)</option>
              </select>
            </div>

            <div>
              <label class="text-[11px] font-bold text-slate-600 dark:text-slate-300 block mb-1">Sucursal Asignada</label>
              <select
                v-model="formEditar.sucursal_id"
                :disabled="formEditar.rol !== 'cajero'"
                :class="[
                  'w-full px-3 py-2 text-xs rounded-xl border font-bold focus:outline-hidden',
                  formEditar.rol !== 'cajero'
                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 border-slate-200 dark:border-slate-700 cursor-not-allowed'
                    : 'bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white border-slate-200 dark:border-slate-700'
                ]"
              >
                <option v-for="suc in SUCURSALES_DISPONIBLES" :key="suc.id" :value="suc.id">
                  {{ suc.nombre }}
                </option>
              </select>
            </div>
          </div>

          <!-- Estado y Revocación -->
          <div class="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-700">
            <div>
              <span class="text-xs font-bold text-slate-900 dark:text-white block">Estado de la Cuenta</span>
              <span class="text-[11px] text-slate-400">Si se desactiva, su sesión se revoca de inmediato.</span>
            </div>
            <button
              type="button"
              @click="formEditar.activo = !formEditar.activo"
              :class="[
                'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out',
                formEditar.activo ? 'bg-emerald-600' : 'bg-rose-600'
              ]"
            >
              <span
                :class="[
                  'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out',
                  formEditar.activo ? 'translate-x-5' : 'translate-x-0'
                ]"
              />
            </button>
          </div>
        </div>

        <div class="flex items-center justify-end gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
          <button
            @click="modalEditarAbierto = false"
            type="button"
            class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl"
          >
            Cancelar
          </button>
          <button
            @click="guardarEdicion"
            :disabled="guardando"
            type="button"
            class="px-5 py-2 text-xs font-extrabold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-md shadow-indigo-500/20 flex items-center gap-2"
          >
            <Loader2 v-if="guardando" class="w-4 h-4 animate-spin" />
            <span v-else>Guardar Cambios</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL 3: CREDENCIAL TEMPORAL GENERADA (ÉXITO) -->
    <div 
      v-if="modalCredencialAbierto && credencialGenerada" 
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-fadeIn"
    >
      <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 border border-emerald-200 dark:border-emerald-800 shadow-2xl space-y-4">
        <div class="w-12 h-12 rounded-2xl bg-emerald-100 dark:bg-emerald-950 text-emerald-600 flex items-center justify-center mx-auto">
          <Key class="w-6 h-6" />
        </div>

        <div class="text-center space-y-1">
          <h3 class="text-base font-extrabold text-slate-900 dark:text-white">
            ¡Usuario Interno Creado!
          </h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            Comparte estas credenciales temporales con el colaborador de forma segura.
          </p>
        </div>

        <div class="bg-slate-50 dark:bg-slate-800/60 rounded-xl p-4 border border-slate-200 dark:border-slate-700 space-y-2.5 text-xs font-mono">
          <div class="flex justify-between">
            <span class="text-slate-400">Colaborador:</span>
            <span class="font-bold text-slate-800 dark:text-slate-200">{{ credencialGenerada.nombre }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-400">Correo:</span>
            <span class="font-bold text-slate-800 dark:text-slate-200">{{ credencialGenerada.email }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-400">Rol:</span>
            <span class="font-bold uppercase text-purple-600">{{ credencialGenerada.rol }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-400">Sucursal:</span>
            <span class="font-bold text-slate-800 dark:text-slate-200">{{ credencialGenerada.sucursal }}</span>
          </div>
          <div class="pt-2 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <span class="text-slate-400">Contraseña Temp:</span>
            <span class="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 rounded font-black text-sm">
              {{ credencialGenerada.passwordTemporal }}
            </span>
          </div>
        </div>

        <div class="p-3 bg-amber-50 dark:bg-amber-950/40 rounded-xl border border-amber-200 dark:border-amber-900/40 text-[11px] text-amber-800 dark:text-amber-300 flex items-center gap-2">
          <AlertTriangle class="w-4 h-4 shrink-0" />
          <span>El sistema obligará a cambiar esta contraseña en el primer inicio de sesión.</span>
        </div>

        <div class="flex gap-2 pt-1">
          <button
            @click="copiarCredencial"
            type="button"
            class="flex-1 py-2 text-xs font-extrabold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-200 rounded-xl flex items-center justify-center gap-1.5 transition-colors"
          >
            <Check v-if="copiado" class="w-4 h-4 text-emerald-600" />
            <Copy v-else class="w-4 h-4" />
            {{ copiado ? '¡Copiado!' : 'Copiar Credencial' }}
          </button>

          <button
            @click="modalCredencialAbierto = false"
            type="button"
            class="px-5 py-2 text-xs font-extrabold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl shadow-md transition-colors"
          >
            Entendido
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL 4: CONFIRMAR DESACTIVACIÓN (REVOCACIÓN INMEDIATA) -->
    <div 
      v-if="modalConfirmarDesactivar && usuarioSeleccionado" 
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-fadeIn"
    >
      <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 border border-rose-200 dark:border-rose-900 shadow-2xl space-y-4">
        <div class="w-12 h-12 rounded-2xl bg-rose-100 dark:bg-rose-950 text-rose-600 flex items-center justify-center mx-auto">
          <UserX class="w-6 h-6" />
        </div>

        <div class="text-center space-y-1">
          <h3 class="text-base font-extrabold text-slate-900 dark:text-white">
            ¿Desactivar y Revocar Sesión?
          </h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            ¿Estás seguro de desactivar a <strong class="text-slate-800 dark:text-slate-200">{{ usuarioSeleccionado.nombre_completo }}</strong>?
          </p>
        </div>

        <div class="p-3 bg-rose-50 dark:bg-rose-950/40 rounded-xl border border-rose-200 dark:border-rose-900/40 text-[11px] text-rose-800 dark:text-rose-300 flex items-start gap-2">
          <ShieldAlert class="w-4 h-4 shrink-0 mt-0.5" />
          <span>Su sesión actual será revocada de inmediato en Supabase Auth y no podrá ingresar a ningún terminal o módulo del ERP. La acción quedará registrada en <code>audit_logs</code>.</span>
        </div>

        <div class="flex items-center justify-end gap-3 pt-2">
          <button
            @click="modalConfirmarDesactivar = false"
            type="button"
            class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl"
          >
            Cancelar
          </button>
          <button
            @click="ejecutarDesactivacion"
            :disabled="guardando"
            type="button"
            class="px-5 py-2 text-xs font-extrabold bg-rose-600 hover:bg-rose-700 text-white rounded-xl shadow-md shadow-rose-500/20 flex items-center gap-2"
          >
            <Loader2 v-if="guardando" class="w-4 h-4 animate-spin" />
            <span v-else>Sí, Desactivar y Revocar</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
