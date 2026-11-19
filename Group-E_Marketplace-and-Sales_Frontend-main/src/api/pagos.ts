import { apiClient } from './client';
import type {
  PagosOrdenResumen,
  RegistrarPagoOrdenPayload,
  RegistrarPagoOrdenResponse,
  IniciarPagoPayload,
  IniciarPagoResponse,
  TransaccionPagoResponse
} from '@/types';

export const pagosApi = {
  /**
   * US-16 · RIO-PAG-01: Solicita procesamiento de cobro e inicio de transacción
   */
  async iniciarPago(payload: IniciarPagoPayload): Promise<IniciarPagoResponse> {
    const { data } = await apiClient.post<IniciarPagoResponse>('/api/v1/pagos/iniciar', payload);
    return data;
  },

  /**
   * US-16: Consulta en tiempo real del estado de la transacción (para polling / feedback instantáneo)
   */
  async consultarEstado(idOrToken: string): Promise<TransaccionPagoResponse> {
    const { data } = await apiClient.get<TransaccionPagoResponse>(`/api/v1/pagos/transacciones/${encodeURIComponent(idOrToken)}`);
    return data;
  },

  /**
   * US-16: Herramienta de simulación de webhook bancario para pruebas QA y demos interactivas
   */
  async simularWebhook(
    transaccionId: string,
    resultado: 'aprobado' | 'rechazado',
    motivo?: string
  ): Promise<{ recibido: boolean; transaccion_id: string; nuevo_estado: string; mensaje: string }> {
    const { data } = await apiClient.post('/api/v1/pagos/simular-webhook', {
      transaccion_id: transaccionId,
      resultado,
      motivo
    });
    return data;
  },

  /** KAN-54: pagos, saldo e historial de pagos de una orden */
  async pagosDeOrden(ordenId: string): Promise<PagosOrdenResumen> {
    const { data } = await apiClient.get<PagosOrdenResumen>(`/api/v1/ordenes/${ordenId}/pagos`);
    return data;
  },

  /** KAN-54: registra el pago (o un tramo) de una orden contra el medio utilizado */
  async registrarPagoOrden(payload: RegistrarPagoOrdenPayload): Promise<RegistrarPagoOrdenResponse> {
    const { data } = await apiClient.post<RegistrarPagoOrdenResponse>('/api/v1/pagos/registrar', payload);
    return data;
  }
};
