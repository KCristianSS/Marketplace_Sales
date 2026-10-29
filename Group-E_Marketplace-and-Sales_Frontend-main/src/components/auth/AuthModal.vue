<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { 
  X, 
  Mail, 
  Lock, 
  User, 
  Phone, 
  Eye, 
  EyeOff, 
  Sparkles, 
  CheckCircle, 
  AlertCircle, 
  ShieldCheck, 
  Store, 
  ShoppingBag,
  ArrowRight,
  Loader2
} from 'lucide-vue-next';

const router = useRouter();
const authStore = useAuthStore();

// Estados del Formulario de Login
const loginEmail = ref('');
const loginPassword = ref('');
const showLoginPassword = ref(false);
const loginError = ref('');
const isLoggingIn = ref(false);

// Estados del Formulario de Registro
const regNombre = ref('');
const regEmail = ref('');
const regTelefono = ref('');
const regPassword = ref('');
const regConfirmPassword = ref('');
const showRegPassword = ref(false);
const regError = ref('');
const isRegistering = ref(false);
const regSuccessMsg = ref('');

// Validación de contraseña en tiempo real
const passwordStrength = computed(() => {
  const p = regPassword.value;
  if (!p) return { score: 0, label: '', color: 'bg-slate-200' };
  if (p.length < 6) return { score: 1, label: 'Débil (mínimo 6 caracteres)', color: 'bg-rose-500' };
  
  let score = 1;
  if (p.length >= 8) score++;
  if (/[A-Z]/.test(p) && /[0-9]/.test(p)) score++;
  if (/[^A-Za-z0-9]/.test(p)) score++;

  if (score === 2) return { score: 2, label: 'Aceptable', color: 'bg-amber-500' };
  if (score >= 3) return { score: 3, label: 'Segura', color: 'bg-emerald-500' };
  return { score: 1, label: 'Débil', color: 'bg-rose-500' };
});

const passwordsMatch = computed(() => {
  if (!regConfirmPassword.value) return true;
  return regPassword.value === regConfirmPassword.value;
});

// Cambiar de pestaña
function switchTab(tab: 'login' | 'register') {
  authStore.authModalTab = tab;
  loginError.value = '';
  regError.value = '';
  regSuccessMsg.value = '';
}

// Cuentas Demo de Acceso Rápido (Para evaluación y testing ágil)
function fillDemoAccount(role: 'admin' | 'cajero' | 'cliente') {
  authStore.authModalTab = 'login';
  loginError.value = '';
  if (role === 'admin') {
    loginEmail.value = 'admin@maxiconecta.bo';
    loginPassword.value = 'Admin123!';
  } else if (role === 'cajero') {
    loginEmail.value = 'cajero@maxiconecta.bo';
    loginPassword.value = 'Cajero123!';
  } else {
    loginEmail.value = 'cliente@maxiconecta.bo';
    loginPassword.value = 'Cliente123!';
  }
}

// Ejecutar Login con Redirección Inteligente por Rol
async function handleLogin() {
  if (!loginEmail.value || !loginPassword.value) {
    loginError.value = 'Por favor complete todos los campos.';
    return;
  }

  isLoggingIn.value = true;
  loginError.value = '';

  try {
    const user = await authStore.login({
      email: loginEmail.value.trim(),
      password: loginPassword.value
    });

    authStore.closeAuthModal();

    // Redirección inteligente según el rol autenticado
    if (user.role === 'cajero') {
      router.push('/pos');
    } else if (user.role === 'administrador' || user.role === 'gerente_comercial') {
      router.push('/admin');
    } else {
      // Cliente: permanece en la vista actual o va al perfil si estaba en login
      if (router.currentRoute.value.path === '/login') {
        router.push('/marketplace');
      }
    }
  } catch (err: any) {
    loginError.value = err.response?.data?.detail || 'Error al iniciar sesión. Verifique sus credenciales.';
  } finally {
    isLoggingIn.value = false;
  }
}

// Ejecutar Registro de Nuevo Cliente
async function handleRegister() {
  if (!regNombre.value || !regEmail.value || !regPassword.value) {
    regError.value = 'Por favor complete los campos obligatorios.';
    return;
  }

  if (regPassword.value.length < 6) {
    regError.value = 'La contraseña debe tener al menos 6 caracteres.';
    return;
  }

  if (regPassword.value !== regConfirmPassword.value) {
    regError.value = 'Las contraseñas no coinciden.';
    return;
  }

  isRegistering.value = true;
  regError.value = '';

  try {
    const user = await authStore.register({
      nombre_completo: regNombre.value.trim(),
      email: regEmail.value.trim().toLowerCase(),
      password: regPassword.value,
      telefono: regTelefono.value.trim() || undefined
    });

    regSuccessMsg.value = '¡Cuenta creada con éxito! Se acreditaron tus 50 puntos de bienvenida.';
    
    setTimeout(() => {
      authStore.closeAuthModal();
      router.push('/mi-cuenta');
    }, 1200);
  } catch (err: any) {
    regError.value = err.response?.data?.detail || 'No se pudo crear la cuenta. El correo podría estar en uso.';
  } finally {
    isRegistering.value = false;
  }
}

// Cerrar con Escape
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') authStore.closeAuthModal();
}
watch(() => authStore.isAuthModalOpen, (open) => {
  if (open) window.addEventListener('keydown', handleKeyDown);
  else window.removeEventListener('keydown', handleKeyDown);
});
</script>

<template>
  <div 
    v-if="authStore.isAuthModalOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
    @click.self="authStore.closeAuthModal()"
  >
    <div 
      class="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden flex flex-col"
    >
      <!-- Cabecera del Modal con Selector de Pestañas -->
      <div class="px-6 pt-6 pb-4 border-b border-slate-100 dark:border-slate-800">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md">
              M
            </div>
            <div>
              <h3 class="font-bold text-slate-900 dark:text-white text-base leading-tight">
                MaxiConecta Identidad
              </h3>
              <p class="text-[11px] text-slate-400 font-medium">Autenticación Segura con JWT</p>
            </div>
          </div>

          <button 
            @click="authStore.closeAuthModal()"
            class="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Pestañas: Iniciar Sesión vs Registrarse -->
        <div class="grid grid-cols-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl gap-1 text-xs font-bold">
          <button
            @click="switchTab('login')"
            :class="[
              'py-2 rounded-lg transition-all',
              authStore.authModalTab === 'login'
                ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            ]"
          >
            Iniciar Sesión
          </button>

          <button
            @click="switchTab('register')"
            :class="[
              'py-2 rounded-lg transition-all flex items-center justify-center gap-1.5',
              authStore.authModalTab === 'register'
                ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            ]"
          >
            <span>Crear Cuenta</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-extrabold">+50 pts</span>
          </button>
        </div>
      </div>

      <!-- Cuerpo del Modal -->
      <div class="p-6 overflow-y-auto max-h-[75vh]">
        <!-- ==================== PESTAÑA: INICIAR SESIÓN ==================== -->
        <div v-if="authStore.authModalTab === 'login'" class="space-y-4">
          <!-- Banner de Cuentas Demo Rápidas -->
          <div class="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200/70 dark:border-slate-800 space-y-2">
            <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
              Acceso Rápido para Pruebas y Docencia:
            </span>
            <div class="grid grid-cols-3 gap-1.5">
              <button
                @click="fillDemoAccount('cliente')"
                class="px-2 py-1.5 bg-white dark:bg-slate-700 hover:bg-blue-50 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-lg text-[11px] font-semibold border border-slate-200 dark:border-slate-600 flex items-center justify-center gap-1 transition-colors"
                title="cliente@maxiconecta.bo"
              >
                <ShoppingBag class="w-3 h-3 text-blue-500" /> Cliente
              </button>
              <button
                @click="fillDemoAccount('cajero')"
                class="px-2 py-1.5 bg-white dark:bg-slate-700 hover:bg-emerald-50 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-lg text-[11px] font-semibold border border-slate-200 dark:border-slate-600 flex items-center justify-center gap-1 transition-colors"
                title="cajero@maxiconecta.bo (Abre POS)"
              >
                <Store class="w-3 h-3 text-emerald-500" /> Cajero POS
              </button>
              <button
                @click="fillDemoAccount('admin')"
                class="px-2 py-1.5 bg-white dark:bg-slate-700 hover:bg-indigo-50 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-lg text-[11px] font-semibold border border-slate-200 dark:border-slate-600 flex items-center justify-center gap-1 transition-colors"
                title="admin@maxiconecta.bo (Abre Admin)"
              >
                <ShieldCheck class="w-3 h-3 text-indigo-500" /> Admin
              </button>
            </div>
          </div>

          <!-- Alerta de Error -->
          <div 
            v-if="loginError"
            class="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-xl text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2"
          >
            <AlertCircle class="w-4 h-4 shrink-0" />
            <span>{{ loginError }}</span>
          </div>

          <form @submit.prevent="handleLogin" class="space-y-3.5">
            <!-- Email -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Correo Electrónico</label>
              <div class="relative">
                <Mail class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="loginEmail"
                  type="email"
                  required
                  placeholder="ejemplo@maxiconecta.bo"
                  class="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                />
              </div>
            </div>

            <!-- Contraseña -->
            <div class="space-y-1">
              <div class="flex justify-between items-center">
                <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Contraseña</label>
              </div>
              <div class="relative">
                <Lock class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="loginPassword"
                  :type="showLoginPassword ? 'text' : 'password'"
                  required
                  placeholder="••••••••"
                  class="w-full pl-9 pr-9 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                />
                <button
                  type="button"
                  @click="showLoginPassword = !showLoginPassword"
                  class="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  <EyeOff v-if="showLoginPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
            </div>

            <!-- Botón Submit -->
            <button
              type="submit"
              :disabled="isLoggingIn"
              class="w-full mt-2 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 transition-all"
            >
              <Loader2 v-if="isLoggingIn" class="w-4 h-4 animate-spin" />
              <span v-else>Iniciar Sesión</span>
              <ArrowRight v-if="!isLoggingIn" class="w-3.5 h-3.5" />
            </button>
          </form>

          <p class="text-[11px] text-center text-slate-400 pt-2">
            ¿No tienes cuenta? 
            <button @click="switchTab('register')" class="text-blue-600 font-bold hover:underline">
              Regístrate aquí y gana 50 puntos
            </button>
          </p>
        </div>

        <!-- ==================== PESTAÑA: CREAR CUENTA ==================== -->
        <div v-else class="space-y-4">
          <!-- Beneficio Destacado de Bienvenida -->
          <div class="p-3 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/40 dark:to-indigo-950/40 rounded-xl border border-blue-100 dark:border-blue-900/50 flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-sm">
              <Sparkles class="w-4 h-4" />
            </div>
            <div>
              <h4 class="text-xs font-bold text-blue-900 dark:text-blue-300">Bono de Bienvenida Automático</h4>
              <p class="text-[11px] text-blue-700 dark:text-blue-400">Recibe <strong>50 puntos de fidelidad</strong> canjeables de inmediato en compras.</p>
            </div>
          </div>

          <!-- Mensaje de Éxito -->
          <div 
            v-if="regSuccessMsg"
            class="p-3 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 rounded-xl text-emerald-700 dark:text-emerald-300 text-xs flex items-center gap-2"
          >
            <CheckCircle class="w-4 h-4 shrink-0" />
            <span>{{ regSuccessMsg }}</span>
          </div>

          <!-- Alerta de Error -->
          <div 
            v-if="regError"
            class="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-xl text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2"
          >
            <AlertCircle class="w-4 h-4 shrink-0" />
            <span>{{ regError }}</span>
          </div>

          <form @submit.prevent="handleRegister" class="space-y-3">
            <!-- Nombre Completo -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Nombre Completo *</label>
              <div class="relative">
                <User class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="regNombre"
                  type="text"
                  required
                  placeholder="Ej. Ana García Rojas"
                  class="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <!-- Email -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Correo Electrónico *</label>
              <div class="relative">
                <Mail class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="regEmail"
                  type="email"
                  required
                  placeholder="ana.garcia@example.com"
                  class="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <!-- Teléfono (Opcional) -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Teléfono / WhatsApp (Opcional)</label>
              <div class="relative">
                <Phone class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="regTelefono"
                  type="tel"
                  placeholder="+591 70000000"
                  class="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <!-- Contraseña con Medidor de Fortaleza -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Contraseña *</label>
              <div class="relative">
                <Lock class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="regPassword"
                  :type="showRegPassword ? 'text' : 'password'"
                  required
                  placeholder="Mínimo 6 caracteres"
                  class="w-full pl-9 pr-9 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
                <button
                  type="button"
                  @click="showRegPassword = !showRegPassword"
                  class="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  <EyeOff v-if="showRegPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>

              <!-- Barra de fortaleza reactiva -->
              <div v-if="regPassword" class="pt-1 space-y-1">
                <div class="h-1 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                  <div 
                    :class="['h-full transition-all duration-300', passwordStrength.color]" 
                    :style="{ width: `${(passwordStrength.score / 3) * 100}%` }"
                  ></div>
                </div>
                <span class="text-[10px] text-slate-400 font-medium">Seguridad: {{ passwordStrength.label }}</span>
              </div>
            </div>

            <!-- Confirmar Contraseña -->
            <div class="space-y-1">
              <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Confirmar Contraseña *</label>
              <div class="relative">
                <Lock class="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  v-model="regConfirmPassword"
                  type="password"
                  required
                  placeholder="Repita su contraseña"
                  class="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <span v-if="regConfirmPassword && !passwordsMatch" class="text-[10px] text-rose-500 font-semibold">
                Las contraseñas no coinciden.
              </span>
            </div>

            <!-- Botón Submit Registro -->
            <button
              type="submit"
              :disabled="isRegistering || !passwordsMatch"
              class="w-full mt-2 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 transition-all"
            >
              <Loader2 v-if="isRegistering" class="w-4 h-4 animate-spin" />
              <span v-else>Crear Cuenta y Recibir 50 Puntos</span>
              <Sparkles v-if="!isRegistering" class="w-3.5 h-3.5" />
            </button>
          </form>

          <p class="text-[11px] text-center text-slate-400 pt-2">
            ¿Ya tienes una cuenta? 
            <button @click="switchTab('login')" class="text-blue-600 font-bold hover:underline">
              Inicia sesión aquí
            </button>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
