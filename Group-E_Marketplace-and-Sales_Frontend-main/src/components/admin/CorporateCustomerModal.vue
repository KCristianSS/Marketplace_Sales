<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { Building2, X } from 'lucide-vue-next';
import { registrarEmpresaB2B, errorB2B, type ClienteCorporativo } from '@/api/cotizaciones';

const props = defineProps<{ initialNit?: string }>();
const emit = defineEmits<{ close: []; registered: [cliente: ClienteCorporativo, creado: boolean] }>();
const dialog = ref<HTMLDialogElement | null>(null);
const nitInput = ref<HTMLInputElement | null>(null);
const saving = ref(false);
const error = ref('');
const form = reactive({ nit_ci: props.initialNit || '', razon_social: '', email: '', nombre_completo: '', telefono: '' });
function close() { if (!saving.value) emit('close'); }
async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const result = await registrarEmpresaB2B({ nit_ci: form.nit_ci.trim(), razon_social: form.razon_social.trim(), email: form.email.trim(),
      nombre_completo: form.nombre_completo.trim() || undefined, telefono: form.telefono.trim() || undefined });
    emit('registered', result.cliente, result.creado);
  } catch (err) { error.value = errorB2B(err, 'No se pudo registrar la empresa.'); }
  finally { saving.value = false; }
}
onMounted(() => { dialog.value?.showModal(); nitInput.value?.focus(); });
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" aria-modal="true" aria-labelledby="corporate-title" class="corporate-dialog m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 text-slate-900 shadow-2xl" @cancel.prevent="close">
      <header class="flex items-start justify-between gap-3"><div><h2 id="corporate-title" class="flex items-center gap-2 text-lg font-bold"><Building2 class="h-5 w-5 text-indigo-700" /> Registrar empresa</h2><p class="mt-1 text-xs leading-5 text-slate-500">Registra sus datos comerciales para emitir cotizaciones. No necesita una cuenta ni una contraseña.</p></div><button type="button" :disabled="saving" aria-label="Cerrar registro de empresa" class="rounded-lg p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-40" @click="close"><X class="h-5 w-5" /></button></header>
      <form class="mt-5 space-y-4" @submit.prevent="save">
        <fieldset :disabled="saving" class="space-y-4">
          <label class="block text-sm font-semibold">NIT<input ref="nitInput" v-model="form.nit_ci" required inputmode="numeric" pattern="[0-9]{5,20}" minlength="5" maxlength="20" placeholder="Solo números" class="company-input" /></label>
          <label class="block text-sm font-semibold">Razón social<input v-model="form.razon_social" required minlength="2" maxlength="200" autocomplete="organization" class="company-input" /></label>
          <label class="block text-sm font-semibold">Correo comercial<input v-model="form.email" required type="email" maxlength="150" autocomplete="email" class="company-input" /></label>
          <label class="block text-sm font-semibold">Nombre del contacto <span class="font-normal text-slate-400">(opcional)</span><input v-model="form.nombre_completo" minlength="2" maxlength="200" autocomplete="name" class="company-input" /></label>
          <label class="block text-sm font-semibold">Teléfono <span class="font-normal text-slate-400">(opcional)</span><input v-model="form.telefono" type="tel" maxlength="50" autocomplete="tel" class="company-input" /></label>
        </fieldset>
        <p v-if="error" role="alert" class="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{{ error }}</p>
        <div class="flex justify-end gap-2"><button type="button" :disabled="saving" class="rounded-xl border px-4 py-2.5 text-sm font-semibold disabled:opacity-40" @click="close">Cancelar</button><button type="submit" :disabled="saving" class="rounded-xl bg-indigo-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{{ saving ? 'Guardando…' : 'Guardar y seleccionar' }}</button></div>
      </form>
    </dialog>
  </Teleport>
</template>

<style scoped>
.corporate-dialog::backdrop { background: rgb(15 23 42 / 55%); backdrop-filter: blur(3px); }
.company-input { @apply mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-normal; }
</style>
