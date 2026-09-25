import { createRouter, createWebHistory } from 'vue-router';
import MarketplaceView from '@/views/marketplace/MarketplaceView.vue';
import WishlistView from '@/views/marketplace/WishlistView.vue';
import PosView from '@/views/pos/PosView.vue';
import AdminView from '@/views/admin/AdminView.vue';
import AccountView from '@/views/customer/AccountView.vue';
import { useAuthStore } from '@/stores/auth';
import type { UserRole } from '@/types';

type ProtectedRouteMeta = {
  title: string;
  requiresAuth?: boolean;
  allowedRoles?: UserRole[];
};

const routes = [
  {
    path: '/',
    redirect: '/marketplace'
  },
  {
    path: '/marketplace',
    name: 'marketplace',
    component: MarketplaceView,
    meta: { title: 'Marketplace Digital — MaxiConecta' } satisfies ProtectedRouteMeta
  },
  {
    path: '/mi-cuenta',
    name: 'cuenta',
    component: AccountView,
    meta: {
      title: 'Mi Cuenta y Compras — MaxiConecta',
      requiresAuth: true
    } satisfies ProtectedRouteMeta
  },
  {
    path: '/compras',
    redirect: '/mi-cuenta'
  },
  {
    path: '/pos',
    name: 'pos',
    component: PosView,
    meta: {
      title: 'Punto de Venta Físico (POS) — MaxiConecta',
      requiresAuth: true,
      allowedRoles: ['cajero', 'administrador']
    } satisfies ProtectedRouteMeta
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminView,
    meta: {
      title: 'Panel Administrativo — MaxiConecta',
      requiresAuth: true,
      allowedRoles: ['administrador', 'gerente_comercial']
    } satisfies ProtectedRouteMeta
  },
  {
    path: '/wishlist',
    name: 'wishlist',
    component: WishlistView,
    meta: { title: 'Lista de Deseos — MaxiConecta' } satisfies ProtectedRouteMeta
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, from, next) => {
  document.title = (to.meta.title as string) || 'MaxiConecta';

  const authStore = useAuthStore();
  const requiresAuth = to.meta.requiresAuth as boolean | undefined;
  const allowedRoles = to.meta.allowedRoles as UserRole[] | undefined;

  // 1. Verificación de Autenticación
  if (requiresAuth && !authStore.isAuthenticated) {
    authStore.openAuthModal('login');
    // Si venía de una ruta válida se queda allí, sino al marketplace
    if (from.path && from.path !== to.path) {
      return next(false);
    }
    return next('/marketplace');
  }

  // 2. Verificación de Control de Acceso por Rol (RBAC - US-49)
  if (allowedRoles && allowedRoles.length > 0) {
    const userRole = authStore.userRole;
    if (!allowedRoles.includes(userRole)) {
      alert(`Acceso denegado: El módulo '${to.name?.toString().toUpperCase()}' requiere permisos de: ${allowedRoles.join(' o ')}. Tu rol actual es '${userRole}'.`);
      
      // Redirigir según el rol del usuario
      if (userRole === 'cajero') return next('/pos');
      if (userRole === 'administrador' || userRole === 'gerente_comercial') return next('/admin');
      return next('/marketplace');
    }
  }

  next();
});

export default router;
