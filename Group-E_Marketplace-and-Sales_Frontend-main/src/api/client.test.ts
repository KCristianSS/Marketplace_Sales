// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  vi.stubEnv('VITE_API_URL', '');
});

afterEach(() => vi.unstubAllEnvs());

describe('rutas del API Gateway', () => {
  it.each([
    ['http://localhost:8000', 'http://localhost:8000/api/v1'],
    ['http://localhost:8000/', 'http://localhost:8000/api/v1'],
    ['http://localhost:8000/api/', 'http://localhost:8000/api/v1'],
    ['http://localhost:8000/api/v1', 'http://localhost:8000/api/v1'],
    ['', '/api/v1'],
  ])('conserva el prefijo con base %s', async (baseURL, expected) => {
    vi.stubEnv('VITE_API_GATEWAY_URL', baseURL);
    const { apiClient } = await import('./client');
    const urls: string[] = [];
    apiClient.defaults.adapter = async (config) => {
      urls.push(apiClient.getUri(config));
      return { config, data: {}, status: 200, statusText: 'OK', headers: {} };
    };
    await apiClient.get('/api/v1/catalogo/buscar');
    await apiClient.post('/v1/clientes/auth/login', {});
    expect(urls).toEqual([`${expected}/catalogo/buscar`, `${expected}/clientes/auth/login`]);
  });

  it('conserva el token al normalizar la ruta', async () => {
    vi.stubEnv('VITE_API_GATEWAY_URL', 'http://localhost:8000');
    localStorage.setItem('maxiconecta_token', 'token-prueba');
    const { apiClient } = await import('./client');
    apiClient.defaults.adapter = async (config) => {
      expect(config.headers.Authorization).toBe('Bearer token-prueba');
      return { config, data: {}, status: 200, statusText: 'OK', headers: {} };
    };
    await apiClient.get('/v1/clientes/auth/me');
  });
});
