<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { 
  User, 
  Mail, 
  Phone, 
  Sparkles, 
  ShoppingBag, 
  Package, 
  Calendar, 
  CreditCard, 
  CheckCircle2, 
  Clock, 
  ChevronRight, 
  LogOut,
  ShieldCheck,
  Store
} from 'lucide-vue-next';

const router = useRouter();
const authStore = useAuthStore();

const activeTab = ref<'perfil' | 'pedidos' | 'puntos'>('perfil');

// Demo de pedidos anteriores del cliente
const pedidos = ref([
  {
    id: 'ord-10023',
    codigo: 'MAXI-2026-0419',
    fecha: '2026-03-15',
    total: 8999.00,
    estado: 'entregada',
    items_count: 1,
    metodo_pago: 'Tarjeta de Crédito / QR',
    items_detalle: 'Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)'
  },
  {
    id: 'ord-10024',
    codigo: 'MAXI-2026-0488',
    fecha: '2026-03-22',
    total: 799.00,
    estado: 'en_preparacion',
    items_count: 1,
    metodo_pago: 'QR Simple',
    items_detalle: 'Mouse Inalámbrico Logitech MX Master 3S'
  }
]);

onMounted(async () => {
  if (authStore.isAuthenticated) {
    await authStore.fetchProfile();
  }
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
        @click="activeTab = 'pedidos'"
        :class="[
          'pb-3 border-b-2 transition-colors flex items-center gap-2',
          activeTab === 'pedidos'
            ? 'border-blue-600 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
        ]"
      >
        <Package class="w-4 h-4" /> Mis Compras y Pedidos
        <span class="text-[10px] px-1.5 py-0.2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-full font-extrabold">{{ pedidos.length }}</span>
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
      <div v-else-if="activeTab === 'pedidos'" class="lg:col-span-2 space-y-4">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 space-y-4">
          <div class="flex justify-between items-center">
            <h3 class="text-sm font-bold text-slate-900 dark:text-white">Historial de Compras y Seguimiento</h3>
            <span class="text-xs text-slate-400">Actualizado en tiempo real</span>
          </div>

          <div class="space-y-3">
            <div
              v-for="pedido in pedidos"
              :key="pedido.id"
              class="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-slate-300 transition-all"
            >
              <div class="space-y-1">
                <div class="flex items-center gap-2">
                  <span class="font-mono text-xs font-black text-blue-600 dark:text-blue-400">{{ pedido.codigo }}</span>
                  <span 
                    :class="[
                      'text-[10px] font-extrabold px-2 py-0.5 rounded-full capitalize',
                      pedido.estado === 'entregada' 
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
                    ]"
                  >
                    {{ pedido.estado.replace('_', ' ') }}
                  </span>
                </div>
                <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{{ pedido.items_detalle }}</p>
                <div class="flex items-center gap-3 text-[11px] text-slate-400">
                  <span class="flex items-center gap-1"><Calendar class="w-3 h-3" /> {{ pedido.fecha }}</span>
                  <span class="flex items-center gap-1"><CreditCard class="w-3 h-3" /> {{ pedido.metodo_pago }}</span>
                </div>
              </div>

              <div class="text-right">
                <span class="text-xs text-slate-400 block">Total Pagado:</span>
                <span class="text-sm font-extrabold text-slate-900 dark:text-white">BOB {{ pedido.total.toFixed(2) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- PESTAÑA: PUNTOS Y BENEFICIOS -->
      <div v-else class="lg:col-span-2 space-y-4">
        <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 space-y-4">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white">Programa de Fidelización MaxiPuntos</h3>
          
          <div class="p-4 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/40 dark:to-orange-950/40 border border-amber-200/70 rounded-xl flex items-center justify-between">
            <div>
              <span class="text-xs font-bold text-amber-900 dark:text-amber-200">Tu Saldo Disponible</span>
              <p class="text-2xl font-black text-amber-600">{{ authStore.pointsBalance }} Puntos</p>
              <p class="text-[11px] text-amber-700 dark:text-amber-300 mt-1">Equivalente a BOB {{ (authStore.pointsBalance * 0.5).toFixed(2) }} de descuento directo en checkout.</p>
            </div>
            <Sparkles class="w-10 h-10 text-amber-500 opacity-75" />
          </div>

          <div class="space-y-2 pt-2">
            <h4 class="text-xs font-bold text-slate-700 dark:text-slate-300">¿Cómo ganar más puntos?</h4>
            <ul class="text-xs text-slate-500 space-y-1.5 list-disc list-inside">
              <li>1 punto por cada BOB 20 de compra en el Marketplace o POS.</li>
              <li>Bonificación especial de bienvenida otorgada al registrarte (50 pts).</li>
              <li>Multiplicador x2 en promociones comerciales del ERP.</li>
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
