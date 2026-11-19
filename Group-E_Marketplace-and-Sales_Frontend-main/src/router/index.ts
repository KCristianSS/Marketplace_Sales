import { notify } from '@/lib/feedback';
import { createRouter, createWebHistory } from 'vue-router';
import MarketplaceView from '@/views/marketplace/MarketplaceView.vue';
import WishlistView from '@/views/marketplace/WishlistView.vue';
import PosView from '@/views/pos/PosView.vue';
import AdminView from '@/views/admin/AdminView.vue';
import AccountView from '@/views/customer/AccountView.vue';
import PasswordResetView from '@/views/auth/PasswordResetView.vue';
import SeguimientoPedidoView from '@/views/customer/SeguimientoPedidoView.vue';
import { useAuthStore } from '@/stores/auth';
import type { UserRole } from '@/types';

type ProtectedRouteMeta = {
  title: string;
  requiresAuth?: boolean;
  allowedRoles?: UserRole[];
};

const routes = [
  {
    path: '/primer-cambio-contrasena',
    name: 'primer-cambio-contrasena',
    component: () => import('@/views/auth/FirstPasswordChangeView.vue'),
    meta: { title: 'Cambiar contraseña — MaxiConecta', requiresAuth: true } satisfies ProtectedRouteMeta
  },
  {
    path: '/tarjetas-regalo',
    name: 'tarjetas-regalo',
    component: () => import('@/views/customer/GiftCardsView.vue'),
    meta: { title: 'Tarjetas de regalo — MaxiConecta', requiresAuth: true } satisfies ProtectedRouteMeta
  },
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
    path: '/seguimiento/:id',
    name: 'seguimiento-pedido',
    component: SeguimientoPedidoView,
    meta: { title: 'Seguimiento de pedido — MaxiConecta', requiresAuth: true } satisfies ProtectedRouteMeta
  },
  {
    path: '/notificaciones',
    redirect: '/mi-cuenta?tab=notificaciones'
  },

  {
    path: '/restablecer-contrasena',
    name: 'restablecer-contrasena',
    component: PasswordResetView,
    meta: { title: 'Restablecer contraseña — MaxiConecta' } satisfies ProtectedRouteMeta
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
    path: '/admin/ventas',
    name: 'admin-ventas',
    redirect: '/admin?tab=pedidos',
    meta: {
      title: 'Historial de Ventas — MaxiConecta',
      requiresAuth: true,
      allowedRoles: ['administrador', 'gerente_comercial']
    } satisfies ProtectedRouteMeta
  },
  {
    path: '/admin/reembolsos',
    name: 'admin-reembolsos',
    component: () => import('@/views/admin/ReembolsosView.vue'),
    meta: {
      title: 'Reembolsos — MaxiConecta',
      requiresAuth: true,
      allowedRoles: ['administrador']
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

  if (authStore.isAuthenticated && authStore.user?.debe_cambiar_password && to.name !== 'primer-cambio-contrasena') {
    return next('/primer-cambio-contrasena');
  }

  // 2. Verificación de Control de Acceso por Rol (RBAC - US-49)
  if (allowedRoles && allowedRoles.length > 0) {
    const userRole = authStore.userRole;
    if (!allowedRoles.includes(userRole)) {
      notify.error(`Acceso denegado: El módulo '${to.name?.toString().toUpperCase()}' requiere permisos de: ${allowedRoles.join(' o ')}. Tu rol actual es '${userRole}'.`);

      // Redirigir según el rol del usuario
      if (userRole === 'cajero') return next('/pos');
      if (userRole === 'administrador' || userRole === 'gerente_comercial') return next('/admin');
      return next('/marketplace');
    }
  }

  next();
});

export default router;
