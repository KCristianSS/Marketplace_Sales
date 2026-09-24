import { createRouter, createWebHistory } from 'vue-router';
import MarketplaceView from '@/views/marketplace/MarketplaceView.vue';
import PosView from '@/views/pos/PosView.vue';
import AdminView from '@/views/admin/AdminView.vue';

const routes = [
  {
    path: '/',
    redirect: '/marketplace'
  },
  {
    path: '/marketplace',
    name: 'marketplace',
    component: MarketplaceView,
    meta: { title: 'Marketplace Digital — MaxiConecta' }
  },
  {
    path: '/pos',
    name: 'pos',
    component: PosView,
    meta: { title: 'Punto de Venta Físico (POS) — MaxiConecta' }
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminView,
    meta: { title: 'Panel Administrativo — MaxiConecta' }
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, from, next) => {
  document.title = (to.meta.title as string) || 'MaxiConecta';
  next();
});

export default router;
