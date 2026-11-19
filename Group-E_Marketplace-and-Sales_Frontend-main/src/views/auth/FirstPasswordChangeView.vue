<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import { useAuthStore } from '@/stores/auth';
import { LockKeyhole } from 'lucide-vue-next';

const auth = useAuthStore();
const router = useRouter();
const actual = ref('');
const nueva = ref('');
const confirmacion = ref('');
const error = ref('');
const enviando = ref(false);
const completado = ref(false);
async function guardar() {
  error.value = '';
  if (nueva.value.length < 8) { error.value = 'La nueva contraseña debe tener al menos 8 caracteres.'; return; }
  if (nueva.value !== confirmacion.value) { error.value = 'Las contraseñas no coinciden.'; return; }
  enviando.value = true;
  try {
    await apiClient.post('/v1/clientes/auth/primer-cambio-password', { password_actual: actual.value, password_nueva: nueva.value });
    actual.value = ''; nueva.value = ''; confirmacion.value = '';
    completado.value = true;
    auth.logout();
  } catch (e: any) {
    error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'No se pudo actualizar la contraseña.';
  } finally { enviando.value = false; }
}
function iniciarSesion() { router.push('/marketplace'); auth.openAuthModal('login'); }
</script>

<template>
  <main class="mx-auto flex min-h-[65vh] max-w-lg items-center px-4 py-10">
    <section class="w-full space-y-5 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div class="flex items-center gap-3"><span class="rounded-xl bg-emerald-100 p-3 text-emerald-700"><LockKeyhole class="h-6 w-6" /></span><div><h1 class="text-xl font-bold">Cambiar contraseña</h1><p class="text-sm text-slate-500">Protege tu cuenta antes de continuar.</p></div></div>
      <div v-if="completado" class="space-y-4"><p class="text-sm text-emerald-700">Tu contraseña se actualizó. Inicia sesión con la nueva contraseña.</p><button class="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white" @click="iniciarSesion">Iniciar sesión</button></div>
      <form v-else class="space-y-4" @submit.prevent="guardar">
        <label class="block text-sm font-semibold">Contraseña temporal<input v-model="actual" required type="password" autocomplete="current-password" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2" /></label>
        <label class="block text-sm font-semibold">Nueva contraseña<input v-model="nueva" required minlength="8" maxlength="72" type="password" autocomplete="new-password" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2" /></label>
        <label class="block text-sm font-semibold">Confirmar contraseña<input v-model="confirmacion" required type="password" autocomplete="new-password" class="mt-1 w-full rounded-xl border border-slate-300 bg-transparent px-3 py-2" /></label>
        <p v-if="error" role="alert" class="text-sm text-rose-700">{{ error }}</p>
        <button :disabled="enviando" class="w-full rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{{ enviando ? 'Guardando…' : 'Guardar contraseña' }}</button>
      </form>
    </section>
  </main>
</template>
