<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { useCartStore } from '@/stores/cart';
import { useAuthStore } from '@/stores/auth';
import { 
  ShoppingBag, 
  Store, 
  LayoutDashboard, 
  X, 
  Trash2, 
  Check, 
  UserCircle, 
  ChevronRight,
  ShieldAlert
} from 'lucide-vue-next';

const route = useRoute();
const cartStore = useCartStore();
const authStore = useAuthStore();

const cuponInput = ref('');
const cuponMsg = ref('');

function canjearCupon() {
  if (!cuponInput.value) return;
  const ok = cartStore.aplicarCupon(cuponInput.value);
  if (ok) {
    cuponMsg.value = '¡Cupón MAXI10 aplicado (10% de descuento)!';
  } else {
    cuponMsg.value = 'Cupón inválido. Prueba con MAXI10';
  }
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
    <!-- Navbar Superior Profesional -->
    <header class="sticky top-0 z-40 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-b border-slate-200 dark:border-slate-800">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <!-- Logo y Marca -->
        <div class="flex items-center gap-6">
          <router-link to="/" class="flex items-center gap-2 group">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white font-extrabold shadow-md group-hover:scale-105 transition-transform">
              M
            </div>
            <div>
              <span class="font-extrabold text-lg tracking-tight bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                MaxiConecta
              </span>
              <span class="block text-[10px] text-slate-400 font-medium -mt-1">Marketplace y Ventas (Grupo E)</span>
            </div>
          </router-link>

          <!-- Selector de Portales (Marketplace / POS / Admin) -->
          <nav class="hidden md:flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl">
            <router-link
              to="/marketplace"
              :class="[
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                route.path.startsWith('/marketplace')
                  ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
              ]"
            >
              <ShoppingBag class="w-3.5 h-3.5" /> Marketplace
            </router-link>

            <router-link
              to="/pos"
              :class="[
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                route.path.startsWith('/pos')
                  ? 'bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-400 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
              ]"
            >
              <Store class="w-3.5 h-3.5" /> Punto de Venta (POS)
            </router-link>

            <router-link
              to="/admin"
              :class="[
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                route.path.startsWith('/admin')
                  ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
              ]"
            >
              <LayoutDashboard class="w-3.5 h-3.5" /> Panel Admin
            </router-link>
          </nav>
        </div>

        <!-- Acciones Derecha (Rol Selector & Botón Carrito) -->
        <div class="flex items-center gap-3">
          <!-- Selector Rápido de Rol (Para pruebas y presentación) -->
          <div class="hidden sm:flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-lg text-xs">
            <UserCircle class="w-4 h-4 text-slate-400" />
            <select
              :value="authStore.userRole"
              @change="(e) => authStore.setRole((e.target as HTMLSelectElement).value as any)"
              class="bg-transparent text-xs font-semibold focus:outline-none cursor-pointer text-slate-700 dark:text-slate-200"
            >
              <option value="administrador">Rol: Administrador</option>
              <option value="cajero">Rol: Cajero</option>
              <option value="gerente_comercial">Rol: Gerente Comercial</option>
              <option value="cliente">Rol: Cliente</option>
            </select>
          </div>

          <!-- Botón Carrito Flotante (RF-13) -->
          <button
            @click="cartStore.toggleDrawer"
            class="relative p-2.5 bg-blue-50 dark:bg-blue-950/50 hover:bg-blue-100 text-blue-600 dark:text-blue-400 rounded-xl"
            title="Abrir Carrito"
          >
            <ShoppingBag class="w-5 h-5" />
            <span
              v-if="cartStore.itemCount > 0"
              class="absolute -top-1 -right-1 w-5 h-5 bg-blue-600 text-white text-[10px] font-bold rounded-full flex items-center justify-center shadow-md animate-bounce"
            >
              {{ cartStore.itemCount }}
            </span>
          </button>
        </div>
      </div>
    </header>

    <!-- Contenedor de Vistas -->
    <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <router-view />
    </main>

    <!-- Drawer Deslizante de Carrito Persistente (RF-13, RF-14) -->
    <div
      v-if="cartStore.isDrawerOpen"
      class="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm transition-opacity"
    >
      <div class="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div class="w-screen max-w-md bg-white dark:bg-slate-900 shadow-2xl flex flex-col border-l border-slate-200 dark:border-slate-800">
          <!-- Drawer Header -->
          <div class="p-5 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
            <div class="flex items-center gap-2">
              <ShoppingBag class="w-5 h-5 text-blue-600" />
              <h2 class="text-base font-bold">Carrito de Compras (Redis)</h2>
            </div>
            <button @click="cartStore.toggleDrawer" class="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
              <X class="w-5 h-5 text-slate-500" />
            </button>
          </div>

          <!-- Drawer Body: Lista de Ítems -->
          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <div
              v-for="item in cartStore.items"
              :key="item.variante_id"
              class="flex gap-3 p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800"
            >
              <div class="flex-1">
                <h4 class="text-xs font-bold text-slate-800 dark:text-slate-200 line-clamp-2">{{ item.nombre }}</h4>
                <span class="text-[11px] font-mono text-slate-400">BOB {{ item.precio_unitario.toFixed(2) }} c/u</span>
                
                <div class="flex items-center gap-2 mt-2">
                  <button @click="cartStore.updateQuantity(item.variante_id, -1)" class="w-6 h-6 rounded bg-slate-200 dark:bg-slate-700 text-xs font-bold">-</button>
                  <span class="text-xs font-bold px-1">{{ item.cantidad }}</span>
                  <button @click="cartStore.updateQuantity(item.variante_id, 1)" class="w-6 h-6 rounded bg-slate-200 dark:bg-slate-700 text-xs font-bold">+</button>
                </div>
              </div>

              <div class="flex flex-col justify-between items-end">
                <button @click="cartStore.removeItem(item.variante_id)" class="text-rose-500 hover:text-rose-700 p-1">
                  <Trash2 class="w-4 h-4" />
                </button>
                <span class="text-sm font-bold text-blue-600">BOB {{ item.total_linea.toFixed(2) }}</span>
              </div>
            </div>

            <div v-if="cartStore.items.length === 0" class="py-12 text-center text-slate-400 space-y-2">
              <ShoppingBag class="w-12 h-12 mx-auto text-slate-300 dark:text-slate-700" />
              <p class="text-sm">Tu carrito está vacío.</p>
            </div>
          </div>

          <!-- Drawer Footer: Cupones y Checkout -->
          <div class="p-5 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/80 space-y-3">
            <!-- Input Cupón (RF-17) -->
            <div class="flex gap-2">
              <input
                v-model="cuponInput"
                type="text"
                placeholder="Código Cupón (ej. MAXI10)"
                class="flex-1 px-3 py-1.5 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg uppercase"
              />
              <button @click="canjearCupon" class="px-3 py-1.5 bg-slate-800 dark:bg-slate-700 text-white text-xs font-semibold rounded-lg">
                Aplicar
              </button>
            </div>
            <p v-if="cuponMsg" class="text-[11px] text-emerald-600 font-semibold">{{ cuponMsg }}</p>

            <div class="space-y-1 text-xs text-slate-500 pt-1">
              <div class="flex justify-between">
                <span>Subtotal:</span>
                <span>BOB {{ cartStore.subtotal.toFixed(2) }}</span>
              </div>
              <div v-if="cartStore.descuento > 0" class="flex justify-between text-emerald-600 font-semibold">
                <span>Descuento cupón:</span>
                <span>- BOB {{ cartStore.descuento.toFixed(2) }}</span>
              </div>
              <div class="flex justify-between text-sm font-bold text-slate-900 dark:text-white pt-1 border-t border-slate-200">
                <span>Total:</span>
                <span>BOB {{ cartStore.total.toFixed(2) }}</span>
              </div>
            </div>

            <button
              :disabled="cartStore.items.length === 0"
              class="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl shadow-lg flex items-center justify-center gap-2"
            >
              Iniciar Checkout [Reserva Stock TTL] <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer Institucional UCB -->
    <footer class="bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 py-6 text-center text-xs text-slate-500">
      <div class="max-w-7xl mx-auto px-4 space-y-1">
        <p class="font-semibold text-slate-700 dark:text-slate-300">
          MaxiConecta — Marketplace y Ventas | Grupo E
        </p>
        <p>
          Taller de Sistemas de Información · Universidad Católica Boliviana "San Pablo" · La Paz, Bolivia
        </p>
      </div>
    </footer>
  </div>
</template>
