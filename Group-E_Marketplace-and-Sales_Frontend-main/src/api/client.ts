import axios from 'axios';

const API_BASE_URL = 
  import.meta.env.VITE_API_GATEWAY_URL || 
  import.meta.env.VITE_API_URL || 
  '/api';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Interceptor para inyectar token JWT y normalizar URLs
apiClient.interceptors.request.use((config) => {
  if (config.url?.startsWith('/v1/')) {
    config.url = `/api${config.url}`;
  }
  if (config.url?.startsWith('/api/')) {
    // Quitar únicamente el prefijo que ya forma parte de la URL base.
    const baseURL = (config.baseURL || '').replace(/\/+$/, '');
    config.baseURL = baseURL;
    if (baseURL.endsWith('/api/v1') && config.url.startsWith('/api/v1/')) {
      config.url = config.url.slice('/api/v1'.length);
    } else if (baseURL.endsWith('/api')) {
      config.url = config.url.slice('/api'.length);
    }
  }
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

// -----------------------------------------------------------------------------
// HISTORIA KAN-42: PREFERENCIAS DE NOTIFICACIÓN DE CLIENTES (KAN-187)
// -----------------------------------------------------------------------------
export interface PreferenciasNotificacion {
  id?: string;
  cliente_id: string;
  canal_correo: boolean;
  avisos_estado_pedido: boolean;
  avisos_promociones: boolean;
  avisos_recordatorios: boolean;
  updated_at?: string;
  mensaje?: string;
}

export async function getPreferenciasNotificacion(clienteId: string): Promise<PreferenciasNotificacion> {
  const res = await apiClient.get<PreferenciasNotificacion>(`/api/v1/clientes/${clienteId}/preferencias-notificacion`);
  return res.data;
}

export async function updatePreferenciasNotificacion(
  clienteId: string,
  payload: Partial<PreferenciasNotificacion>
): Promise<PreferenciasNotificacion> {
  const res = await apiClient.put<PreferenciasNotificacion>(
    `/api/v1/clientes/${clienteId}/preferencias-notificacion`,
    payload
  );
  return res.data;
}

// -----------------------------------------------------------------------------
// HISTORIA KAN-421: ADMINISTRACIÓN DE USUARIOS INTERNOS Y ROLES (KAN-424, KAN-425)
// -----------------------------------------------------------------------------
export interface UsuarioInterno {
  id: string;
  user_id?: string;
  nombre_completo: string;
  email: string;
  rol: 'cajero' | 'gerente_comercial' | 'administrador';
  sucursal_id?: string | null;
  sucursal_nombre?: string | null;
  activo: boolean;
  debe_cambiar_password: boolean;
  password_temporal?: string | null;
  sesion_revocada?: boolean;
  created_at?: string;
  updated_at?: string;
  mensaje?: string;
}

export async function getAdminUsuarios(params?: {
  rol?: string;
  activo?: boolean;
  sucursal_id?: string;
  q?: string;
}): Promise<UsuarioInterno[]> {
  const res = await apiClient.get<UsuarioInterno[]>('/api/v1/admin/usuarios', { params });
  return res.data;
}

export async function createAdminUsuario(payload: {
  nombre_completo: string;
  email: string;
  rol: string;
  sucursal_id?: string | null;
  sucursal_nombre?: string | null;
  debe_cambiar_password?: boolean;
}): Promise<UsuarioInterno> {
  const res = await apiClient.post<UsuarioInterno>('/api/v1/admin/usuarios', payload);
  return res.data;
}

export async function updateAdminUsuario(
  id: string,
  payload: Partial<UsuarioInterno>
): Promise<UsuarioInterno> {
  const res = await apiClient.patch<UsuarioInterno>(`/api/v1/admin/usuarios/${id}`, payload);
  return res.data;
}

export async function deleteAdminUsuario(id: string): Promise<UsuarioInterno> {
  const res = await apiClient.delete<UsuarioInterno>(`/api/v1/admin/usuarios/${id}`);
  return res.data;
}

// -----------------------------------------------------------------------------
// HISTORIA KAN-14 / KAN-40: SINCRONIZACIÓN CON CRM VÍA PUB/SUB (KAN-171, KAN-173)
// TÓPICO: projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e
// -----------------------------------------------------------------------------
export type EstadoCrmSync = 'sincronizado' | 'pendiente' | 'publicando' | 'publicado' | 'error' | 'reintentando';
export interface ClienteSyncItem {
  id: string;
  nombre_completo: string;
  email: string;
  telefono: string | null;
  tipo_cliente: string;
  crm_sync_estado: EstadoCrmSync;
  crm_sync_at: string | null;
  crm_contact_id: string | null;
  crm_sync_version: number;
}

export interface CrmOutboxLogItem {
  id: string;
  event_id: string;
  cliente_id: string;
  event_type: string;
  topic: string;
  payload: any;
  attributes: Record<string, string>;
  estado: EstadoCrmSync;
  intentos: number;
  max_intentos: number;
  ultimo_error?: string | null;
  message_id?: string | null;
  created_at: string;
  sent_at?: string | null;
}

export interface CrmVerificacionItem {
  id: string;
  event_id: string;
  event_type: string;
  cliente_id: string;
  payload: any;
  ignorado_duplicado: boolean;
  crm_status: string;
  aplicado: boolean;
  duplicados: number;
  recibido_at: string;
}

export interface CrmSyncEstadoResponse {
  receptor_configurado: boolean;
  status: string;
  topic: string;
  metricas_clientes: {
    total: number;
    sincronizados: number;
    pendientes: number;
    errores: number;
  };
  outbox_metricas: {
    total_eventos: number;
    sincronizados: number;
    pendientes: number;
    errores: number;
  };
  crm_verificacion_metricas: {
    total_mensajes_recibidos: number;
    duplicados_ignorados_idempotencia: number;
  };
  clientes: ClienteSyncItem[];
  ultimos_eventos_outbox: CrmOutboxLogItem[];
  ultimas_verificaciones_crm: CrmVerificacionItem[];
}

export async function getClientesSyncEstado(estado?: string): Promise<CrmSyncEstadoResponse> {
  const res = await apiClient.get<CrmSyncEstadoResponse>('/api/v1/clientes/sync/estado', {
    params: estado && estado !== 'todos' ? { estado } : undefined
  });
  return res.data;
}

export async function resincronizarCliente(id: string): Promise<{
  status: string;
  mensaje: string;
  outbox_item: CrmOutboxLogItem;
}> {
  const res = await apiClient.post(`/api/v1/clientes/${id}/resincronizar`, {});
  return res.data;
}

export async function procesarOutboxCrm(batchSize: number = 10): Promise<{
  status: string;
  mensaje: string;
  procesados_total: number;
  items: CrmOutboxLogItem[];
}> {
  const res = await apiClient.post('/api/v1/clientes/sync/procesar-outbox', {}, {
    params: { batch_size: batchSize }
  });
  return res.data;
}

export async function getVerificacionCrm(): Promise<{
  status: string;
  topic: string;
  metricas: {
    total_mensajes_recibidos: number;
    duplicados_ignorados_idempotencia: number;
  };
  verificaciones: CrmVerificacionItem[];
}> {
  const res = await apiClient.get('/api/v1/clientes/sync/verificacion-crm');
  return res.data;
}


