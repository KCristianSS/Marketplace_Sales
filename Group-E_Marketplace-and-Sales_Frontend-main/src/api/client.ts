import axios from 'axios';

// Accept the gateway URL with or without a trailing /api: paths below always carry the /api/v1 prefix.
const API_BASE_URL = (
  import.meta.env.VITE_API_GATEWAY_URL ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000'
).replace(/\/+$/, '').replace(/\/api$/, '');

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Interceptor para inyectar token JWT y normalizar URLs hacia /api/v1 del gateway
apiClient.interceptors.request.use((config) => {
  if (config.url) {
    if (config.url.startsWith('/v1/')) {
      config.url = `/api${config.url}`;
    } else if (config.url.startsWith('/productos') || config.url.startsWith('/categorias')) {
      config.url = `/api/v1/catalogo${config.url}`;
    }
  }
  const token = localStorage.getItem('maxiconecta_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshInFlight: Promise<string | null> | null = null;

async function renovarSesion(): Promise<string | null> {
  const refreshToken = localStorage.getItem('maxiconecta_refresh_token');
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post(`${API_BASE_URL}/api/v1/clientes/auth/refresh`, { refresh_token: refreshToken });
    localStorage.setItem('maxiconecta_token', data.access_token);
    localStorage.setItem('maxiconecta_refresh_token', data.refresh_token);
    if (data.user) localStorage.setItem('maxiconecta_user', JSON.stringify(data.user));
    window.dispatchEvent(new CustomEvent('maxiconecta:session-refreshed', { detail: data }));
    return data.access_token as string;
  } catch {
    return null;
  }
}

// Renueva la sesión una vez ante un 401 y reintenta; si no es posible, la cierra.
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config;
    const url: string = config?.url || '';
    if (error.response?.status !== 401 || !config || url.includes('/auth/')) {
      return Promise.reject(error);
    }

    if (!config._sessionRetried) {
      config._sessionRetried = true;
      refreshInFlight ??= renovarSesion().finally(() => { refreshInFlight = null; });
      const newToken = await refreshInFlight;
      if (newToken) {
        config.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(config);
      }
    }

    console.warn('Sesión expirada o token no válido. Se requiere iniciar sesión nuevamente.');
    localStorage.removeItem('maxiconecta_token');
    localStorage.removeItem('maxiconecta_refresh_token');
    localStorage.removeItem('maxiconecta_user');
    window.dispatchEvent(new CustomEvent('maxiconecta:session-expired'));
    return Promise.reject(error);
  }
);
