import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { UserProfile } from '@/types';

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('maxiconecta_token'));
  const user = ref<UserProfile>({
    id: 'usr-demo-001',
    nombre_completo: 'Cesar Cayllante (Líder Grupo E)',
    email: 'cesar.cayllante@ucb.edu.bo',
    role: 'administrador',
    puntos_saldo: 350
  });

  const isAuthenticated = computed(() => !!token.value);
  const userRole = computed(() => user.value.role);

  function setSession(newToken: string, profile: UserProfile) {
    token.value = newToken;
    user.value = profile;
    localStorage.setItem('maxiconecta_token', newToken);
  }

  function setRole(newRole: 'cliente' | 'cajero' | 'administrador' | 'gerente_comercial') {
    user.value.role = newRole;
  }

  function logout() {
    token.value = null;
    localStorage.removeItem('maxiconecta_token');
  }

  return {
    token,
    user,
    isAuthenticated,
    userRole,
    setSession,
    setRole,
    logout
  };
});
