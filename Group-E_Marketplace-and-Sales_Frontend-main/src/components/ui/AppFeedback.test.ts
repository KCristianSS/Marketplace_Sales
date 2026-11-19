// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { reactive } from 'vue';
import { toast } from 'vue-sonner';
import AppFeedback from './AppFeedback.vue';
import { activeConfirmation, cancelConfirmations, confirmAction, notify, useNotificationMessage } from '@/lib/feedback';

const route = reactive({ fullPath: '/admin?tab=envios' });
vi.mock('vue-router', () => ({ useRoute: () => route }));
vi.mock('vue-sonner', () => ({
  Toaster: { template: '<div aria-label="Notificaciones" />' },
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

let wrapper: VueWrapper;
beforeEach(() => {
  cancelConfirmations();
  vi.clearAllMocks();
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true,
    value() { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true,
    value() { this.open = false; } });
  wrapper = mount(AppFeedback, { attachTo: document.body });
});
afterEach(() => { wrapper.unmount(); document.body.innerHTML = ''; cancelConfirmations(); });

const dialog = () => document.querySelector('dialog')!;
const clickButton = (text: string) => {
  const button = Array.from(dialog().querySelectorAll('button')).find(item => item.textContent === text);
  expect(button).toBeTruthy();
  button!.click();
};

describe('confirmación compartida', () => {
  it('espera una decisión y acepta solo al pulsar el botón de la acción', async () => {
    const action = vi.fn();
    const result = confirmAction('Se eliminará la dirección.', { title: '¿Eliminar dirección?', confirmLabel: 'Eliminar', danger: true });
    void result.then(accepted => { if (accepted) action(); });
    await flushPromises();
    expect(dialog().open).toBe(true);
    expect(dialog().textContent).toContain('¿Eliminar dirección?');
    expect(document.activeElement?.textContent).toBe('Cancelar');
    expect(action).not.toHaveBeenCalled();
    clickButton('Eliminar');
    expect(await result).toBe(true);
    await flushPromises();
    expect(action).toHaveBeenCalledOnce();
    expect(dialog().open).toBe(false);
  });

  it.each(['cancelar', 'escape', 'cerrar'])('rechaza la operación al %s', async modo => {
    const result = confirmAction('Descartar cambios');
    await flushPromises();
    if (modo === 'escape') dialog().dispatchEvent(new Event('cancel', { cancelable: true }));
    else if (modo === 'cerrar') (dialog().querySelector('[aria-label="Cerrar confirmación"]') as HTMLButtonElement).click();
    else clickButton('Cancelar');
    expect(await result).toBe(false);
  });

  it('mantiene separadas las decisiones de dos solicitudes simultáneas', async () => {
    const first = confirmAction('Primera acción');
    const second = confirmAction('Segunda acción');
    await flushPromises();
    clickButton('Cancelar');
    expect(await first).toBe(false);
    await flushPromises();
    expect(dialog().textContent).toContain('Segunda acción');
    clickButton('Continuar');
    expect(await second).toBe(true);
  });

  it('cancela las acciones pendientes al cambiar de pantalla', async () => {
    const first = confirmAction('Primera acción');
    const second = confirmAction('Segunda acción');
    route.fullPath = '/marketplace';
    await flushPromises();
    expect(await first).toBe(false);
    expect(await second).toBe(false);
    expect(activeConfirmation.value).toBeNull();
    expect(dialog().open).toBe(false);
  });
});

describe('avisos con Sonner', () => {
  it('muestra las operaciones repetidas y evita avisos vacíos al limpiar el estado', () => {
    const message = useNotificationMessage<string | null>('success', null);
    message.value = 'Configuración guardada';
    message.value = 'Configuración guardada';
    message.value = null;
    expect(toast.success).toHaveBeenCalledTimes(2);
    expect(toast.success).toHaveBeenLastCalledWith('Configuración guardada');
    expect(message.value).toBeNull();
  });

  it('presenta el detalle del error de la API como texto legible', () => {
    notify.error({ detail: [{ msg: 'El monto es obligatorio' }, { msg: 'Selecciona una zona' }] });
    expect(toast.error).toHaveBeenCalledWith('El monto es obligatorio\nSelecciona una zona', { duration: 8000 });
  });
});
