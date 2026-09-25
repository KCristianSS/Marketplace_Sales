import axios from 'axios';

const API_BASE_URL = 
  import.meta.env.VITE_API_GATEWAY_URL || 
  import.meta.env.VITE_API_URL || 
  'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Interceptor para inyectar token JWT si existe en localStorage
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('maxiconecta_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Manejo centralizado de respuestas de error
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Si la petición no era de login/registro, advertir de sesión expirada
      const url = error.config?.url || '';
      if (!url.includes('/login') && !url.includes('/registro')) {
        console.warn('Sesión expirada o token no válido. Limpiando almacenamiento.');
        localStorage.removeItem('maxiconecta_token');
        localStorage.removeItem('maxiconecta_refresh_token');
        localStorage.removeItem('maxiconecta_user');
      }
    }
    return Promise.reject(error);
  }
);
