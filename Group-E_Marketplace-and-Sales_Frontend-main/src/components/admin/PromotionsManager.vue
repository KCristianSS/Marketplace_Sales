<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  Tag, Plus, Edit3, Trash2, X, RefreshCw, Search, CheckCircle2, AlertCircle, Power, Loader2, Percent, Banknote,
} from 'lucide-vue-next';
import {
  listarCupones, crearCupon, actualizarCupon, eliminarCupon, mensajeDeError,
  type CuponAdmin, type EstadoVigencia, type TipoDescuento,
} from '@/api/cupones';

/**
 * RF-17 [FE]: panel administrativo de gestión y activación de promociones.
 * Permite crear, editar, activar/desactivar y eliminar cupones con vigencia,
 * monto mínimo de compra y límite de canjes. El backend valida todos los datos
 * y restringe estas operaciones a los roles administrador y gerente comercial.
 */
const cupones = ref<CuponAdmin[]>([]);
const cargando = ref(false);
const guardando = ref(false);
const errorMsg = ref('');
const okMsg = ref('');
const busqueda = ref('');
const filtroEstado = ref<'todos' | EstadoVigencia>('todos');

const ETIQUETAS_ESTADO: Record<EstadoVigencia, { texto: string; clase: string }> = {
  vigente: { texto: 'Vigente', clase: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400' },
  programado: { texto: 'Programado', clase: 'bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-400' },
  vencido: { texto: 'Vencido', clase: 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400' },
  agotado: { texto: 'Agotado', clase: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400' },
  inactivo: { texto: 'Inactivo', clase: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400' },
};

const cuponesFiltrados = computed(() => {
  const q = busqueda.value.trim().toLowerCase();
  return cupones.value.filter((c) => {
    const coincide = !q || c.codigo.toLowerCase().includes(q) || (c.descripcion ?? '').toLowerCase().includes(q);
    return coincide && (filtroEstado.value === 'todos' || c.estado_vigencia === filtroEstado.value);
  });
});

const resumen = computed(() => ({
  total: cupones.value.length,
  vigentes: cupones.value.filter((c) => c.estado_vigencia === 'vigente').length,
  canjes: cupones.value.reduce((acc, c) => acc + c.usos_actuales, 0),
}));

function avisar(tipo: 'ok' | 'error', texto: string) {
  okMsg.value = tipo === 'ok' ? texto : '';
  errorMsg.value = tipo === 'error' ? texto : '';
  window.setTimeout(() => { okMsg.value = ''; errorMsg.value = ''; }, 5000);
}

async function cargar() {
  cargando.value = true;
  try {
    cupones.value = await listarCupones();
  } catch (err) {
    avisar('error', mensajeDeError(err, 'No se pudieron cargar las promociones. Verifica tu sesión y permisos.'));
  } finally {
    cargando.value = false;
  }
}
onMounted(cargar);

// ---- Formulario crear / editar ----
const modalAbierto = ref(false);
const editando = ref<string | null>(null);
const errorForm = ref('');
const form = reactive({
  codigo: '',
  descripcion: '',
  tipo_descuento: 'porcentaje' as TipoDescuento,
  valor_descuento: 10 as number | null,
  monto_minimo: 0 as number | null,
  ilimitado: false,
  usos_maximos: 100 as number | null,
  fecha_inicio: '',
  fecha_fin: '',
  activo: true,
});

const aISODia = (yyyyMmDd: string, finDeDia: boolean) => {
  if (!yyyyMmDd) return null;
  const [y, m, d] = yyyyMmDd.split('-').map(Number);
  return (finDeDia ? new Date(y, m - 1, d, 23, 59, 59) : new Date(y, m - 1, d, 0, 0, 0)).toISOString();
};
const aInputDia = (iso: string | null) => {
  if (!iso) return '';
  const f = new Date(iso);
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, '0')}-${String(f.getDate()).padStart(2, '0')}`;
};
const formatearFecha = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('es-BO') : '—');

function abrirCrear() {
  editando.value = null;
  errorForm.value = '';
  Object.assign(form, {
    codigo: '', descripcion: '', tipo_descuento: 'porcentaje', valor_descuento: 10, monto_minimo: 0,
    ilimitado: false, usos_maximos: 100, fecha_inicio: aInputDia(new Date().toISOString()), fecha_fin: '', activo: true,
  });
  modalAbierto.value = true;
}

function abrirEditar(c: CuponAdmin) {
  editando.value = c.codigo;
  errorForm.value = '';
  Object.assign(form, {
    codigo: c.codigo, descripcion: c.descripcion ?? '', tipo_descuento: c.tipo_descuento,
    valor_descuento: c.valor_descuento, monto_minimo: c.monto_minimo,
    ilimitado: c.usos_maximos === null, usos_maximos: c.usos_maximos ?? 100,
    fecha_inicio: aInputDia(c.fecha_inicio), fecha_fin: aInputDia(c.fecha_fin), activo: c.activo,
  });
  modalAbierto.value = true;
}

function validarFormulario(): string {
  if (!editando.value && !/^[A-Za-z0-9_-]{3,50}$/.test(form.codigo.trim())) {
    return 'El código debe tener entre 3 y 50 caracteres (letras, números, guion o guion bajo).';
  }
  const valor = Number(form.valor_descuento);
  if (!(valor > 0)) return 'El valor del descuento debe ser mayor a 0.';
  if (form.tipo_descuento === 'porcentaje' && valor > 100) return 'Un descuento porcentual no puede superar el 100%.';
  if (Number(form.monto_minimo ?? 0) < 0) return 'El monto mínimo no puede ser negativo.';
  if (!form.ilimitado && !(Number(form.usos_maximos) >= 1)) return 'El límite de canjes debe ser al menos 1.';
  if (form.fecha_inicio && form.fecha_fin && form.fecha_fin < form.fecha_inicio) {
    return 'La fecha de fin debe ser posterior a la de inicio.';
  }
  return '';
}

async function guardar() {
  errorForm.value = validarFormulario();
  if (errorForm.value) return;
  guardando.value = true;
  const datos = {
    descripcion: form.descripcion.trim() || null,
    tipo_descuento: form.tipo_descuento,
    valor_descuento: Number(form.valor_descuento),
    monto_minimo: Number(form.monto_minimo ?? 0),
    usos_maximos: form.ilimitado ? null : Number(form.usos_maximos),
    fecha_inicio: aISODia(form.fecha_inicio, false),
    fecha_fin: aISODia(form.fecha_fin, true),
    activo: form.activo,
  };
  try {
    if (editando.value) {
      await actualizarCupon(editando.value, datos);
      avisar('ok', `Cupón ${editando.value} actualizado.`);
    } else {
      const creado = await crearCupon({ codigo: form.codigo.trim().toUpperCase(), ...datos });
      avisar('ok', `Cupón ${creado.codigo} creado.`);
    }
    modalAbierto.value = false;
    await cargar();
  } catch (err) {
    errorForm.value = mensajeDeError(err);
  } finally {
    guardando.value = false;
  }
}

async function alternarActivo(c: CuponAdmin) {
  try {
    await actualizarCupon(c.codigo, { activo: !c.activo });
    avisar('ok', `Cupón ${c.codigo} ${c.activo ? 'desactivado' : 'activado'}.`);
    await cargar();
  } catch (err) {
    avisar('error', mensajeDeError(err));
  }
}

const confirmandoEliminar = ref<string | null>(null);
async function eliminar(codigo: string) {
  try {
    await eliminarCupon(codigo);
    avisar('ok', `Cupón ${codigo} eliminado.`);
    confirmandoEliminar.value = null;
    await cargar();
  } catch (err) {
    avisar('error', mensajeDeError(err));
  }
}

const descripcionDescuento = (c: CuponAdmin) =>
  c.tipo_descuento === 'porcentaje' ? `${Number(c.valor_descuento)}%` : `Bs. ${Number(c.valor_descuento).toFixed(2)}`;
const porcentajeUso = (c: CuponAdmin) =>
  c.usos_maximos ? Math.min(100, Math.round((c.usos_actuales / c.usos_maximos) * 100)) : 0;
</script>

<template>
  <section class="space-y-5" data-testid="promotions-manager">
    <!-- Encabezado y resumen -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Tag class="w-5 h-5 text-blue-600" /> Promociones y Cupones (RF-17)
        </h2>
        <p class="text-xs text-slate-500 mt-0.5">
          {{ resumen.total }} cupones · {{ resumen.vigentes }} vigentes · {{ resumen.canjes }} canjes registrados
        </p>
      </div>
      <div class="flex gap-2">
        <button @click="cargar" :disabled="cargando" class="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': cargando }" /> Actualizar
        </button>
        <button @click="abrirCrear" class="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-blue-600 hover:bg-blue-500 text-white">
          <Plus class="w-3.5 h-3.5" /> Nueva promoción
        </button>
      </div>
    </div>

    <p v-if="okMsg" class="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-lg px-3 py-2" role="status">
      <CheckCircle2 class="w-4 h-4" /> {{ okMsg }}
    </p>
    <p v-if="errorMsg" class="flex items-center gap-1.5 text-xs font-semibold text-rose-700 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 rounded-lg px-3 py-2" role="alert">
      <AlertCircle class="w-4 h-4" /> {{ errorMsg }}
    </p>

    <!-- Filtros -->
    <div class="flex flex-col sm:flex-row gap-2">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input v-model="busqueda" type="text" placeholder="Buscar por código o descripción…"
               class="w-full pl-9 pr-3 py-2 text-xs bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500" />
      </div>
      <select v-model="filtroEstado" class="px-3 py-2 text-xs bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg">
        <option value="todos">Todos los estados</option>
        <option v-for="(e, clave) in ETIQUETAS_ESTADO" :key="clave" :value="clave">{{ e.texto }}</option>
      </select>
    </div>

    <!-- Tabla -->
    <div class="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-x-auto">
      <table class="w-full text-left text-xs">
        <thead class="bg-slate-50 dark:bg-slate-800/60 text-slate-500">
          <tr>
            <th class="px-4 py-2.5 font-semibold">Cupón</th>
            <th class="px-4 py-2.5 font-semibold">Descuento</th>
            <th class="px-4 py-2.5 font-semibold">Compra mínima</th>
            <th class="px-4 py-2.5 font-semibold">Canjes</th>
            <th class="px-4 py-2.5 font-semibold">Vigencia</th>
            <th class="px-4 py-2.5 font-semibold">Estado</th>
            <th class="px-4 py-2.5 font-semibold text-right">Acciones</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
          <tr v-if="cargando && cupones.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-slate-400"><Loader2 class="w-4 h-4 animate-spin inline mr-1" /> Cargando promociones…</td>
          </tr>
          <tr v-else-if="cuponesFiltrados.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-slate-400">No hay promociones que coincidan con el filtro.</td>
          </tr>
          <tr v-for="c in cuponesFiltrados" :key="c.codigo" class="hover:bg-slate-50 dark:hover:bg-slate-800/40">
            <td class="px-4 py-3">
              <p class="font-mono font-bold text-slate-800 dark:text-slate-100">{{ c.codigo }}</p>
              <p class="text-[11px] text-slate-400 max-w-[220px] truncate" :title="c.descripcion ?? ''">{{ c.descripcion || 'Sin descripción' }}</p>
            </td>
            <td class="px-4 py-3 font-bold text-slate-700 dark:text-slate-200">
              <span class="inline-flex items-center gap-1">
                <Percent v-if="c.tipo_descuento === 'porcentaje'" class="w-3 h-3 text-blue-500" />
                <Banknote v-else class="w-3 h-3 text-emerald-500" />
                {{ descripcionDescuento(c) }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ c.monto_minimo > 0 ? `Bs. ${c.monto_minimo.toFixed(2)}` : 'Sin mínimo' }}</td>
            <td class="px-4 py-3 w-36">
              <p class="text-slate-700 dark:text-slate-200 font-semibold">{{ c.usos_actuales }} / {{ c.usos_maximos ?? '∞' }}</p>
              <div v-if="c.usos_maximos" class="h-1.5 mt-1 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                <div class="h-full bg-blue-500" :style="{ width: porcentajeUso(c) + '%' }"></div>
              </div>
            </td>
            <td class="px-4 py-3 text-slate-600 dark:text-slate-300 whitespace-nowrap">{{ formatearFecha(c.fecha_inicio) }} → {{ formatearFecha(c.fecha_fin) }}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold" :class="ETIQUETAS_ESTADO[c.estado_vigencia].clase">
                {{ ETIQUETAS_ESTADO[c.estado_vigencia].texto }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center justify-end gap-1">
                <template v-if="confirmandoEliminar === c.codigo">
                  <span class="text-[11px] text-rose-600 font-semibold mr-1">¿Eliminar?</span>
                  <button @click="eliminar(c.codigo)" class="px-2 py-1 text-[11px] font-bold bg-rose-600 text-white rounded">Sí</button>
                  <button @click="confirmandoEliminar = null" class="px-2 py-1 text-[11px] font-bold border border-slate-300 dark:border-slate-600 rounded">No</button>
                </template>
                <template v-else>
                  <button @click="alternarActivo(c)" :title="c.activo ? 'Desactivar' : 'Activar'"
                          class="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                          :class="c.activo ? 'text-emerald-600' : 'text-slate-400'">
                    <Power class="w-4 h-4" />
                  </button>
                  <button @click="abrirEditar(c)" title="Editar" class="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"><Edit3 class="w-4 h-4" /></button>
                  <button @click="confirmandoEliminar = c.codigo" title="Eliminar" class="p-1.5 rounded-lg text-slate-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30"><Trash2 class="w-4 h-4" /></button>
                </template>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal crear / editar -->
    <div v-if="modalAbierto" class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" @keydown.esc="modalAbierto = false">
      <form @submit.prevent="guardar" class="bg-white dark:bg-slate-900 w-full max-w-lg rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
          <h3 class="text-sm font-bold text-slate-800 dark:text-white">{{ editando ? `Editar cupón ${editando}` : 'Nueva promoción' }}</h3>
          <button type="button" @click="modalAbierto = false" class="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-4 text-xs">
          <div class="grid grid-cols-2 gap-3">
            <label class="space-y-1 col-span-2 sm:col-span-1">
              <span class="font-semibold text-slate-600 dark:text-slate-300">Código *</span>
              <input v-model="form.codigo" :disabled="!!editando" maxlength="50" placeholder="NAVIDAD25"
                     class="w-full px-3 py-2 uppercase font-mono bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg disabled:opacity-60" />
            </label>
            <label class="space-y-1 col-span-2 sm:col-span-1">
              <span class="font-semibold text-slate-600 dark:text-slate-300">Tipo de descuento *</span>
              <select v-model="form.tipo_descuento" class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg">
                <option value="porcentaje">Porcentaje (%)</option>
                <option value="monto_fijo">Monto fijo (Bs.)</option>
              </select>
            </label>
          </div>

          <label class="space-y-1 block">
            <span class="font-semibold text-slate-600 dark:text-slate-300">Descripción</span>
            <input v-model="form.descripcion" maxlength="200" placeholder="Ej: 25% en toda la tienda por Navidad"
                   class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg" />
          </label>

          <div class="grid grid-cols-2 gap-3">
            <label class="space-y-1">
              <span class="font-semibold text-slate-600 dark:text-slate-300">Valor {{ form.tipo_descuento === 'porcentaje' ? '(%)' : '(Bs.)' }} *</span>
              <input v-model.number="form.valor_descuento" type="number" min="0.01" step="0.01"
                     class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg" />
            </label>
            <label class="space-y-1">
              <span class="font-semibold text-slate-600 dark:text-slate-300">Compra mínima (Bs.)</span>
              <input v-model.number="form.monto_minimo" type="number" min="0" step="0.01"
                     class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg" />
            </label>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label class="space-y-1">
              <span class="font-semibold text-slate-600 dark:text-slate-300">Vigente desde</span>
              <input v-model="form.fecha_inicio" type="date" class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg" />
            </label>
            <label class="space-y-1">
              <span class="font-semibold text-slate-600 dark:text-slate-300">Vigente hasta</span>
              <input v-model="form.fecha_fin" type="date" class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg" />
            </label>
          </div>

          <div class="space-y-1">
            <span class="font-semibold text-slate-600 dark:text-slate-300">Límite de canjes</span>
            <div class="flex items-center gap-3">
              <input v-model.number="form.usos_maximos" :disabled="form.ilimitado" type="number" min="1" step="1"
                     class="w-32 px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg disabled:opacity-50" />
              <label class="flex items-center gap-1.5 text-slate-600 dark:text-slate-300"><input v-model="form.ilimitado" type="checkbox" /> Ilimitado</label>
            </div>
          </div>

          <label class="flex items-center gap-2 text-slate-700 dark:text-slate-200 font-semibold">
            <input v-model="form.activo" type="checkbox" /> Promoción activa
          </label>

          <p v-if="errorForm" class="flex items-start gap-1.5 text-rose-600 font-semibold" role="alert"><AlertCircle class="w-4 h-4 shrink-0" /> {{ errorForm }}</p>
        </div>

        <div class="flex justify-end gap-2 px-5 py-4 border-t border-slate-100 dark:border-slate-800">
          <button type="button" @click="modalAbierto = false" class="px-4 py-2 text-xs font-semibold rounded-lg border border-slate-300 dark:border-slate-700">Cancelar</button>
          <button type="submit" :disabled="guardando" class="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-60">
            <Loader2 v-if="guardando" class="w-3.5 h-3.5 animate-spin" /> {{ editando ? 'Guardar cambios' : 'Crear promoción' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>
