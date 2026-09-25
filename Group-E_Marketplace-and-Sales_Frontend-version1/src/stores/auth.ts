import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { UserProfile, UserRole, LoginPayload, RegisterPayload, AuthResponse } from '@/types';
import { apiClient } from '@/api/client';

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('maxiconecta_token'));
  const refreshToken = ref<string | null>(localStorage.getItem('maxiconecta_refresh_token'));
  
  // Cargar usuario almacenado si existe
  const savedUser = localStorage.getItem('maxiconecta_user');
  const user = ref<UserProfile | null>(savedUser ? JSON.parse(savedUser) : null);

  // Control de estado del modal de autenticación
  const isAuthModalOpen = ref<boolean>(false);
  const authModalTab = ref<'login' | 'register'>('login');

  const isAuthenticated = computed(() => !!token.value && !!user.value);
  const userRole = computed<UserRole>(() => user.value?.role || 'cliente');
  const pointsBalance = computed<number>(() => user.value?.puntos_saldo || 0);

  function setSession(newToken: string, newRefreshToken: string, profile: UserProfile) {
    token.value = newToken;
    refreshToken.value = newRefreshToken;
    user.value = profile;

    localStorage.setItem('maxiconecta_token', newToken);
    localStorage.setItem('maxiconecta_refresh_token', newRefreshToken);
    localStorage.setItem('maxiconecta_user', JSON.stringify(profile));
  }

  async function login(credentials: LoginPayload): Promise<UserProfile> {
    const response = await apiClient.post<AuthResponse>('/api/v1/clientes/auth/login', credentials);
    const { access_token, refresh_token, user: profile } = response.data;
    setSession(access_token, refresh_token, profile);
    return profile;
  }

  async function register(payload: RegisterPayload): Promise<UserProfile> {
    const response = await apiClient.post<AuthResponse>('/api/v1/clientes/auth/registro', payload);
    const { access_token, refresh_token, user: profile } = response.data;
    setSession(access_token, refresh_token, profile);
    return profile;
  }

  async function fetchProfile(): Promise<UserProfile | null> {
    if (!token.value) return null;
    try {
      const response = await apiClient.get<UserProfile>('/api/v1/clientes/auth/me');
      user.value = response.data;
      localStorage.setItem('maxiconecta_user', JSON.stringify(response.data));
      return response.data;
    } catch (err) {
      console.warn('Error al sincronizar perfil con backend:', err);
      return null;
    }
  }

  function logout() {
    token.value = null;
    refreshToken.value = null;
    user.value = null;
    localStorage.removeItem('maxiconecta_token');
    localStorage.removeItem('maxiconecta_refresh_token');
    localStorage.removeItem('maxiconecta_user');
  }

  function openAuthModal(tab: 'login' | 'register' = 'login') {
    authModalTab.value = tab;
    isAuthModalOpen.value = true;
  }

  function closeAuthModal() {
    isAuthModalOpen.value = false;
  }

  function hasRole(roles: UserRole | UserRole[]): boolean {
    if (!user.value) return false;
    const allowed = Array.isArray(roles) ? roles : [roles];
    return allowed.includes(user.value.role);
  }

  return {
    token,
    refreshToken,
    user,
    isAuthenticated,
    userRole,
    pointsBalance,
    isAuthModalOpen,
    authModalTab,
    setSession,
    login,
    register,
    fetchProfile,
    logout,
    openAuthModal,
    closeAuthModal,
    hasRole
  };
});
