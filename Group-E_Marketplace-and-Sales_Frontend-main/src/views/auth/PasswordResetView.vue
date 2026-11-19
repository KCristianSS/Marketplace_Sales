<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { AlertCircle, ArrowLeft, CheckCircle, Eye, EyeOff, KeyRound, Loader2, Lock } from 'lucide-vue-next';

const router = useRouter();
const authStore = useAuthStore();
const password = ref('');
const confirmPassword = ref('');
const showPassword = ref(false);
const showConfirmPassword = ref(false);
const isLoading = ref(true);
const isSaving = ref(false);
const recoveryReady = ref(false);
const success = ref(false);
const errorMessage = ref('');

let supabase: SupabaseClient | null = null;
let unsubscribe: (() => void) | null = null;

onMounted(async () => {
  const url = import.meta.env.VITE_SUPABASE_URL;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    errorMessage.value = 'El servicio de recuperación no está configurado.';
    isLoading.value = false;
    return;
  }

  try {
    supabase = createClient(url, anonKey, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: true }
    });
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY' && session) {
        recoveryReady.value = true;
        isLoading.value = false;
        window.history.replaceState(null, document.title, window.location.pathname);
      }
    });
    unsubscribe = () => data.subscription.unsubscribe();

    const { data: sessionData, error } = await supabase.auth.getSession();
    if (error) throw error;
    if (!recoveryReady.value && sessionData.session) {
      const callbackParams = new URLSearchParams(window.location.hash.slice(1));
      if (callbackParams.get('type') === 'recovery') {
        recoveryReady.value = true;
        window.history.replaceState(null, document.title, window.location.pathname);
      }
    }
    if (!recoveryReady.value) {
      errorMessage.value = 'El enlace es inválido o expiró. Solicita uno nuevo desde el inicio de sesión.';
    }
  } catch {
    errorMessage.value = 'El enlace es inválido o expiró. Solicita uno nuevo desde el inicio de sesión.';
  } finally {
    isLoading.value = false;
  }
});

onUnmounted(() => unsubscribe?.());

async function savePassword() {
  if (password.value.length < 8) {
    errorMessage.value = 'La contraseña debe tener al menos 8 caracteres.';
    return;
  }
  if (password.value !== confirmPassword.value) {
    errorMessage.value = 'Las contraseñas no coinciden.';
    return;
  }
  if (!supabase || !recoveryReady.value) return;

  isSaving.value = true;
  errorMessage.value = '';
  const { error } = await supabase.auth.updateUser({ password: password.value });
  if (error) {
    errorMessage.value = 'No se pudo cambiar la contraseña. Solicita un enlace nuevo e inténtalo otra vez.';
    isSaving.value = false;
    return;
  }

  await supabase.auth.signOut({ scope: 'local' });
  success.value = true;
  isSaving.value = false;
}

function goToLogin() {
  void router.push('/marketplace');
  authStore.openAuthModal('login');
}
</script>

<template>
  <main class="min-h-screen bg-slate-100 dark:bg-slate-950 px-4 py-12 flex items-center justify-center">
    <section class="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-7 shadow-xl">
      <div class="mb-6 flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-white">
        <KeyRound class="h-5 w-5" />
      </div>

      <template v-if="isLoading">
        <h1 class="text-xl font-bold text-slate-900 dark:text-white">Validando enlace</h1>
        <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">Estamos verificando que el enlace siga vigente.</p>
        <Loader2 class="mt-6 h-5 w-5 animate-spin text-blue-600" />
      </template>

      <template v-else-if="success">
        <div class="mb-4 flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
          <CheckCircle class="h-5 w-5" />
          <h1 class="text-xl font-bold">Contraseña actualizada</h1>
        </div>
        <p class="text-sm text-slate-600 dark:text-slate-300">Ya puedes iniciar sesión con tu nueva contraseña.</p>
        <button class="mt-6 w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-bold text-white hover:bg-blue-700" @click="goToLogin">
          Ir a iniciar sesión
        </button>
      </template>

      <template v-else-if="recoveryReady">
        <h1 class="text-xl font-bold text-slate-900 dark:text-white">Crear contraseña nueva</h1>
        <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">Elige una contraseña de al menos 8 caracteres.</p>

        <div v-if="errorMessage" class="mt-5 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
          <span>{{ errorMessage }}</span>
        </div>

        <form class="mt-6 space-y-4" @submit.prevent="savePassword">
          <label class="block text-sm font-semibold text-slate-700 dark:text-slate-200">
            Nueva contraseña
            <span class="relative mt-1.5 block">
              <Lock class="absolute left-3 top-3 h-4 w-4 text-slate-400" />
              <input v-model="password" required minlength="8" autocomplete="new-password" :type="showPassword ? 'text' : 'password'" class="w-full rounded-lg border border-slate-300 bg-slate-50 py-2.5 pl-10 pr-10 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 dark:border-slate-700 dark:bg-slate-800 dark:focus:ring-blue-950" />
              <button type="button" class="absolute right-3 top-3 text-slate-400" :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'" @click="showPassword = !showPassword">
                <EyeOff v-if="showPassword" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </span>
          </label>
          <label class="block text-sm font-semibold text-slate-700 dark:text-slate-200">
            Confirmar contraseña
            <span class="relative mt-1.5 block">
              <Lock class="absolute left-3 top-3 h-4 w-4 text-slate-400" />
              <input v-model="confirmPassword" required minlength="8" autocomplete="new-password" :type="showConfirmPassword ? 'text' : 'password'" class="w-full rounded-lg border border-slate-300 bg-slate-50 py-2.5 pl-10 pr-10 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 dark:border-slate-700 dark:bg-slate-800 dark:focus:ring-blue-950" />
              <button type="button" class="absolute right-3 top-3 text-slate-400" :aria-label="showConfirmPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'" @click="showConfirmPassword = !showConfirmPassword">
                <EyeOff v-if="showConfirmPassword" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </span>
          </label>
          <button type="submit" :disabled="isSaving" class="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-60">
            <Loader2 v-if="isSaving" class="h-4 w-4 animate-spin" />
            <span>{{ isSaving ? 'Actualizando…' : 'Guardar contraseña' }}</span>
          </button>
        </form>
      </template>

      <template v-else>
        <div class="mb-4 flex items-center gap-2 text-rose-700 dark:text-rose-400">
          <AlertCircle class="h-5 w-5" />
          <h1 class="text-xl font-bold">Enlace no disponible</h1>
        </div>
        <p class="text-sm text-slate-600 dark:text-slate-300">{{ errorMessage }}</p>
        <button class="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="goToLogin">
          <ArrowLeft class="h-4 w-4" /> Volver al inicio de sesión
        </button>
      </template>
    </section>
  </main>
</template>