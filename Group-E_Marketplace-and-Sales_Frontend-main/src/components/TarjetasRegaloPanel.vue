<script setup lang="ts">
import { confirmAction, useNotificationMessage } from '@/lib/feedback';
import { onMounted, ref } from 'vue';
import { Gift, RefreshCw, Eye, History, Copy } from 'lucide-vue-next';
import { valesApi, type Vale, type MovimientoVale } from '@/api/vales';
import { pagosApi } from '@/api/pagos';
import { useAuthStore } from '@/stores/auth';
import DynamicPaymentProcessingModal from '@/components/checkout/DynamicPaymentProcessingModal.vue';
import type { IniciarPagoResponse } from '@/types';

const props = withDefaults(defineProps<{ administracion?: boolean }>(), { administracion: false });
const auth = useAuthStore();
const tarjetas = ref<Vale[]>([]);
const movimientos = ref<MovimientoVale[]>([]);
const seleccionada = ref<Vale | null>(null);
const emitida = ref<Vale | null>(null);
const error = ref('');
const aviso = useNotificationMessage<string>('info', '');
const ocupado = ref(false);
const estado = ref('');
const ultimos = ref('');
const offset = ref(0);
const monto = ref(100);
const comprador = ref('');
const motivo = ref('');
const motivoGestion = ref('');
const gestionPendiente = ref<{ tarjeta: Vale; accion: 'activa' | 'bloqueada' | 'anulada' | 'regenerar' } | null>(null);
const vencimiento = ref('');
const solicitud = ref(crypto.randomUUID());
const pago = ref<IniciarPagoResponse | null>(null);
const transaccionPendiente = ref('');
const mostrarPago = ref(false);
const clavePendiente = () => `maxiconecta:vale-pago:${auth.user?.id}`;
const dinero = (n: number | string) => Number(n).toFixed(2);
const fecha = (s: string) => new Date(s).toLocaleString('es-BO');

async function ejecutar(accion: () => Promise<void>) {
  if (ocupado.value) return;
  ocupado.value = true;
  error.value = '';
  aviso.value = '';
  try { await accion(); }
  catch (e: any) { error.value = e.response?.data?.detail || e.message || 'No se pudo completar la operación.'; }
  finally { ocupado.value = false; }
}
async function cargar() {
  tarjetas.value = await valesApi.listar(props.administracion, estado.value, offset.value, ultimos.value.trim());
}
async function emitir() {
  await ejecutar(async () => {
    emitida.value = await valesApi.emitir({ solicitud_id: solicitud.value, comprador_id: comprador.value, monto: monto.value,
      motivo: motivo.value, vence_en: vencimiento.value ? new Date(vencimiento.value).toISOString() : undefined });
    solicitud.value = crypto.randomUUID();
    await cargar();
  });
}
async function comprar() {
  await ejecutar(async () => {
    if (transaccionPendiente.value) throw new Error('Resuelve primero el pago pendiente para evitar comprar dos tarjetas.');
    pago.value = await pagosApi.iniciarPago({ monto: monto.value, moneda: 'BOB', metodo_pago: 'qr',
      proposito: 'vale', cliente_id: auth.user!.id, descripcion: 'Compra de tarjeta de regalo' });
    transaccionPendiente.value = pago.value.transaccion_id;
    sessionStorage.setItem(clavePendiente(), transaccionPendiente.value);
    mostrarPago.value = true;
  });
}
async function confirmarCompra() {
  mostrarPago.value = false;
  await ejecutar(async () => {
    const tx = await pagosApi.consultarEstado(transaccionPendiente.value);
    if (tx.estado === 'rechazado') {
      sessionStorage.removeItem(clavePendiente());
      transaccionPendiente.value = '';
      aviso.value = 'El pago fue rechazado. Puedes iniciar otra compra.';
      return;
    }
    if (tx.estado !== 'aprobado') {
      aviso.value = 'El pago sigue pendiente. Puedes volver a consultarlo.';
      if (pago.value) mostrarPago.value = true;
      return;
    }
    emitida.value = await valesApi.comprar(transaccionPendiente.value);
    sessionStorage.removeItem(clavePendiente());
    transaccionPendiente.value = '';
    await cargar();
  });
}
function prepararGestion(tarjeta: Vale, accion: 'activa' | 'bloqueada' | 'anulada' | 'regenerar') {
  motivoGestion.value = '';
  error.value = '';
  gestionPendiente.value = { tarjeta, accion };
}
async function gestionar() {
  if (!gestionPendiente.value) return;
  const { tarjeta, accion } = gestionPendiente.value;
  await ejecutar(async () => {
    if (motivoGestion.value.trim().length < 3) throw new Error('Escribe el motivo de la gestión (al menos 3 caracteres).');
    if (accion === 'anulada' && !(await confirmAction('La anulación es definitiva e impide canjear el saldo.', { title: '¿Anular tarjeta?', confirmLabel: 'Anular tarjeta', danger: true }))) return;
    if (accion === 'regenerar') {
      if (!(await confirmAction('El código anterior dejará de funcionar.', { title: '¿Generar un código nuevo?', confirmLabel: 'Generar código' }))) return;
      emitida.value = await valesApi.regenerar(tarjeta.id, motivoGestion.value.trim());
    } else {
      await valesApi.cambiarEstado(tarjeta.id, accion, motivoGestion.value.trim());
      aviso.value = `Tarjeta ${accion}.`;
    }
    gestionPendiente.value = null;
    await cargar();
    if (seleccionada.value?.id === tarjeta.id) movimientos.value = await valesApi.movimientos(tarjeta.id);
  });
}
async function historial(tarjeta: Vale) {
  await ejecutar(async () => { seleccionada.value = tarjeta; movimientos.value = await valesApi.movimientos(tarjeta.id); });
}
async function verCodigo(tarjeta: Vale) {
  await ejecutar(async () => { emitida.value = await valesApi.codigo(tarjeta.id); });
}
async function copiar() {
  await ejecutar(async () => { await navigator.clipboard.writeText(emitida.value?.codigo || ''); aviso.value = 'Código copiado.'; });
}
onMounted(() => {
  if (!props.administracion) transaccionPendiente.value = sessionStorage.getItem(clavePendiente()) || '';
  void ejecutar(cargar);
});
</script>

<template>
  <section class="space-y-6 text-slate-900 dark:text-slate-100">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div><h2 class="text-xl font-extrabold flex items-center gap-2"><Gift class="w-6 h-6 text-blue-600" /> Tarjetas de regalo</h2>
        <p class="text-sm text-slate-500 mt-1">{{ administracion ? 'Emisión, códigos, estados e historial de saldo prepagado.' : 'Regala saldo para comprar en MaxiConecta. Canjea todo o una parte al pagar.' }}</p></div>
      <button :disabled="ocupado" class="text-sm flex items-center gap-2" @click="ejecutar(cargar)"><RefreshCw class="w-4 h-4" /> Actualizar</button>
    </header>
    <p v-if="error" role="alert" class="p-3 rounded-xl bg-rose-50 text-rose-700">{{ error }}</p>


    <form class="p-5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 space-y-4" @submit.prevent="administracion ? emitir() : comprar()">
      <h3 class="font-bold">{{ administracion ? 'Emitir tarjeta de regalo' : 'Comprar una tarjeta digital' }}</h3>
      <div class="grid sm:grid-cols-2 gap-4">
        <label class="text-sm">Monto en BOB (0.01 a 10000)<input v-model.number="monto" required type="number" min="0.01" max="10000" step="0.01" :disabled="ocupado || !!transaccionPendiente" class="mt-1 w-full rounded-xl border border-slate-300 p-2 dark:bg-slate-800" /></label>
        <label v-if="administracion" class="text-sm">ID del cliente comprador<input v-model="comprador" required placeholder="UUID del cliente" class="mt-1 w-full rounded-xl border border-slate-300 p-2 dark:bg-slate-800" /></label>
        <label v-if="administracion" class="text-sm">Vencimiento (opcional)<input v-model="vencimiento" type="datetime-local" class="mt-1 w-full rounded-xl border border-slate-300 p-2 dark:bg-slate-800" /></label>
      </div>
      <label v-if="administracion" class="block text-sm">Motivo de emisión<input v-model="motivo" required minlength="3" maxlength="240" placeholder="Ej.: vale autorizado por campaña comercial" class="mt-1 w-full rounded-xl border border-slate-300 p-2 dark:bg-slate-800" /></label>
      <p class="text-xs text-slate-500">{{ administracion ? 'La emisión administrativa asigna saldo sin cobrar al cliente. Toda gestión queda registrada. No se permite editar saldos directamente.' : 'Pago por QR. Se activa después de confirmar el cobro. Sin vencimiento en las tarjetas compradas; el saldo restante se conserva. Quien tenga el código podrá usarlo desde su cuenta.' }}</p>
      <button :disabled="ocupado || !!transaccionPendiente" class="px-4 py-2 rounded-xl bg-blue-600 text-white font-bold disabled:opacity-50">{{ ocupado ? 'Procesando…' : administracion ? 'Emitir y generar código' : `Comprar por Bs ${dinero(monto)}` }}</button>
    </form>
    <div v-if="transaccionPendiente" class="p-4 border border-amber-300 rounded-xl space-y-2"><p class="text-sm">Hay un pago pendiente de confirmar. Si ya pagaste, recupera tu tarjeta sin volver a cobrar.</p>
      <button :disabled="ocupado" class="text-blue-600 font-bold" @click="confirmarCompra">Consultar pago y recuperar tarjeta</button></div>

    <div v-if="emitida" class="p-5 rounded-2xl bg-blue-50 dark:bg-blue-950 border border-blue-200 space-y-3">
      <div class="flex justify-between"><h3 class="font-bold">Código de tu tarjeta</h3><button @click="emitida = null" aria-label="Ocultar código">Ocultar</button></div>
      <p class="font-mono text-sm sm:text-base break-all select-all">{{ emitida.codigo }}</p>
      <p class="text-xs">Guárdalo o compártelo con el destinatario por un canal privado. El código permite gastar el saldo.</p>
      <button class="flex items-center gap-2 text-sm font-bold" @click="copiar"><Copy class="w-4 h-4" /> Copiar código</button>
    </div>

    <div v-if="administracion" class="flex flex-wrap gap-3 items-end">
      <label class="text-sm">Estado<select v-model="estado" class="block rounded-lg p-2 border dark:bg-slate-800"><option value="">Todos</option><option value="activa">Activa</option><option value="bloqueada">Bloqueada</option><option value="anulada">Anulada</option></select></label>
      <label class="text-sm">Últimos 8 caracteres<input v-model="ultimos" maxlength="8" class="block rounded-lg p-2 border dark:bg-slate-800" /></label>
      <button :disabled="ocupado" class="px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg" @click="offset = 0; ejecutar(cargar)">Filtrar</button>
    </div>
    <div class="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-700">
      <table class="w-full text-sm text-left"><thead class="bg-slate-50 dark:bg-slate-800"><tr><th class="p-3">Tarjeta</th><th class="p-3">Saldo disponible</th><th class="p-3">Estado / vigencia</th><th class="p-3">Acciones</th></tr></thead>
        <tbody><tr v-for="tarjeta in tarjetas" :key="tarjeta.id" class="border-t border-slate-200 dark:border-slate-700">
          <td class="p-3"><p class="font-mono">•••• {{ tarjeta.codigo_ultimos }}</p><p class="text-xs text-slate-500">{{ fecha(tarjeta.created_at) }}</p><p v-if="administracion" class="text-xs max-w-48 break-all">Cliente: {{ tarjeta.comprador_id }}</p></td>
          <td class="p-3 font-bold">Bs {{ dinero(tarjeta.saldo) }}<p class="text-xs text-slate-500 font-normal">Inicial: Bs {{ dinero(tarjeta.monto_inicial) }}</p></td>
          <td class="p-3"><span>{{ tarjeta.estado }}</span><p class="text-xs">{{ tarjeta.vence_en ? `Vence: ${fecha(tarjeta.vence_en)}` : 'Sin vencimiento' }}</p></td>
          <td class="p-3"><div class="flex flex-wrap gap-3">
            <button :disabled="ocupado" class="text-blue-600 flex gap-1 items-center" @click="verCodigo(tarjeta)"><Eye class="w-4 h-4" /> Código</button>
            <button :disabled="ocupado" class="text-blue-600 flex gap-1 items-center" @click="historial(tarjeta)"><History class="w-4 h-4" /> Movimientos</button>
            <template v-if="administracion && tarjeta.estado !== 'anulada'">
              <button :disabled="ocupado" @click="prepararGestion(tarjeta, tarjeta.estado === 'activa' ? 'bloqueada' : 'activa')">{{ tarjeta.estado === 'activa' ? 'Bloquear' : 'Reactivar' }}</button>
              <button :disabled="ocupado" @click="prepararGestion(tarjeta, 'regenerar')">Regenerar código</button>
              <button :disabled="ocupado" class="text-rose-600" @click="prepararGestion(tarjeta, 'anulada')">Anular</button>
            </template>
          </div></td></tr><tr v-if="!tarjetas.length"><td colspan="4" class="p-6 text-center text-slate-500">{{ ocupado ? 'Cargando tarjetas…' : 'No hay tarjetas para mostrar.' }}</td></tr></tbody>
      </table>
    </div>
    <div v-if="gestionPendiente" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" @click.self="gestionPendiente = null">
      <form role="dialog" aria-modal="true" aria-labelledby="titulo-gestion-vale" class="w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900" @submit.prevent="gestionar">
        <h3 id="titulo-gestion-vale" class="text-lg font-bold">{{ { activa: 'Reactivar tarjeta', bloqueada: 'Bloquear tarjeta', anulada: 'Anular tarjeta', regenerar: 'Regenerar código' }[gestionPendiente.accion] }}</h3>
        <p class="text-sm text-slate-600 dark:text-slate-300">Tarjeta terminada en {{ gestionPendiente.tarjeta.codigo_ultimos }}. El motivo quedará registrado en sus movimientos.</p>
        <label class="block text-sm font-semibold">Motivo de la gestión
          <textarea v-model="motivoGestion" required minlength="3" maxlength="240" rows="3" placeholder="Escribe el motivo" class="mt-1 w-full rounded-xl border border-slate-300 p-3 dark:border-slate-700 dark:bg-slate-800" />
        </label>
        <p v-if="error" role="alert" class="text-sm text-rose-700">{{ error }}</p>
        <div class="flex justify-end gap-3"><button type="button" :disabled="ocupado" class="px-4 py-2 text-sm font-semibold" @click="gestionPendiente = null">Cancelar</button><button type="submit" :disabled="ocupado" class="rounded-xl bg-blue-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">Confirmar</button></div>
      </form>
    </div>
    <div v-if="administracion" class="flex justify-end gap-4 text-sm"><button :disabled="ocupado || offset === 0" @click="offset -= 50; ejecutar(cargar)">Anterior</button><span>Página {{ offset / 50 + 1 }}</span><button :disabled="ocupado || tarjetas.length < 50" @click="offset += 50; ejecutar(cargar)">Siguiente</button></div>
    <section v-if="seleccionada" class="p-5 rounded-2xl border border-slate-200 dark:border-slate-700 space-y-3">
      <div class="flex justify-between"><h3 class="font-bold">Movimientos · {{ seleccionada.codigo_ultimos }}</h3><button @click="seleccionada = null">Cerrar</button></div>
      <p class="text-xs text-slate-500">Las reservas reducen el disponible; el consumo confirma esa reserva sin descontar otra vez.</p>
      <ul class="divide-y divide-slate-200 dark:divide-slate-700"><li v-for="mov in movimientos" :key="mov.id" class="py-3 text-sm"><div class="flex justify-between gap-3"><span class="font-bold">{{ mov.tipo }}</span><span>Bs {{ dinero(mov.monto) }}</span></div><p>{{ mov.motivo }}</p><p class="text-xs text-slate-500">{{ fecha(mov.created_at) }} · {{ mov.actor }}</p></li></ul>
      <button v-if="movimientos.length && movimientos.length % 100 === 0" :disabled="ocupado" @click="ejecutar(async () => { movimientos.push(...await valesApi.movimientos(seleccionada!.id, movimientos.length)); })">Cargar más movimientos</button>
    </section>
    <DynamicPaymentProcessingModal v-if="mostrarPago && pago" :pago-data="pago" :nombre-cliente="auth.user?.nombre_completo || 'Cliente'" @approved="confirmarCompra" @rejected="confirmarCompra" @cancel="mostrarPago = false" />
  </section>
</template>
