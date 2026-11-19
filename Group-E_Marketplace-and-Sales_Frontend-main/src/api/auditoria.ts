import { apiClient } from './client';

export interface AuditEntry {
  id: string;
  user_id: string | null;
  actor_id: string | null;
  user_role: string | null;
  ip_address: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  payload_before: unknown;
  payload_after: unknown;
  created_at: string;
  request_id: string | null;
  request_method: string | null;
  request_path: string | null;
  user_agent: string | null;
  source: string;
}
export interface AuditFilters {
  page: number;
  limit: number;
  accion?: string;
  entidad?: string;
  actor?: string;
  rol?: string;
  solicitud?: string;
  desde?: string;
  hasta?: string;
}
export interface AuditPage {
  items: AuditEntry[];
  total: number;
  pagina: number;
  total_paginas: number;
  pendientes_locales: number | null;
}
export async function obtenerAuditoria(params: AuditFilters, signal?: AbortSignal): Promise<AuditPage> {
  const { data } = await apiClient.get<AuditPage>('/api/v1/admin/auditoria', { params, signal });
  return data;
}
