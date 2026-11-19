// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import NotificationPreferences from './NotificationPreferences.vue';
import { useAuthStore } from '@/stores/auth';
import { getPreferenciasNotificacion, updatePreferenciasNotificacion } from '@/api/client';

vi.mock('@/api/client', () => ({ apiClient: {}, getPreferenciasNotificacion: vi.fn(), updatePreferenciasNotificacion: vi.fn() }));
vi.mock('@/lib/feedback', () => ({ notify: { success: vi.fn() } }));
beforeEach(() => {
  setActivePinia(createPinia());
  vi.resetAllMocks();
  useAuthStore().user = { id: 'cliente', email: 'cliente@example.com', nombre_completo: 'Cliente', role: 'cliente', puntos_saldo: 0 };
  const prefs = { cliente_id: 'cliente', canal_correo: true, avisos_estado_pedido: true, avisos_promociones: false, avisos_recordatorios: false };
  vi.mocked(getPreferenciasNotificacion).mockResolvedValue(prefs);
  vi.mocked(updatePreferenciasNotificacion).mockResolvedValue(prefs);
});

it('permite desactivar el correo de pedidos sin seleccionar tipos de aviso', async () => {
  const wrapper = mount(NotificationPreferences);
  await flushPromises();
  expect(wrapper.text()).toContain('Notificaciones por correo');
  expect(wrapper.text()).not.toContain('SMS');
  expect(wrapper.text()).not.toContain('Push');
  expect(wrapper.text()).not.toContain('Tipos de aviso');
  const boxes = wrapper.findAll('input[type="checkbox"]');
  expect(boxes).toHaveLength(1);
  await boxes[0].setValue(false);
  await wrapper.find('form').trigger('submit');
  await flushPromises();
  expect(updatePreferenciasNotificacion).toHaveBeenCalledWith('cliente', {
    canal_correo: false, avisos_estado_pedido: false, avisos_promociones: false, avisos_recordatorios: false,
  });
  wrapper.unmount();
});
