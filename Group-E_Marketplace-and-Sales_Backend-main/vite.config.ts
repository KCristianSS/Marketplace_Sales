import { defineConfig, Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
import { createApiMiddleware } from './src/server/api';

function apiPlugin(): Plugin {
  return {
    name: 'api-server-plugin',
    configureServer(server) {
      server.middlewares.use('/api', createApiMiddleware());
    }
  };
}

export default defineConfig({
  plugins: [vue(), apiPlugin()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    strictPort: true,
    allowedHosts: true,
    hmr: process.env.DISABLE_HMR === 'true' ? false : undefined
  }
});
