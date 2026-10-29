import { defineStore } from 'pinia';
import {
  sincronizarCatalogoDelta,
  suscribirseACambiosDeCatalogo,
  type SyncCatalogoItem,
} from '@/api/catalogo';

const STORAGE_KEY_CATALOGO = 'maxiconecta_pos_catalogo_local';
const STORAGE_KEY_LAST_SYNC = 'maxiconecta_pos_last_sync';

export interface ProductoLocal {
  id: string;
  sku: string;
  nombre: string;
  precio_referencia: number;
  estado: string;
  updated_at: string;
}

interface PosSyncState {
  catalogoLocal: Record<string, ProductoLocal>; // clave: sku
  ultimaSincronizacion: string | null;
  conectado: boolean;
  sincronizando: boolean;
  ultimoEvento: string | null;
  historialEventos: any[];
  eventSource: EventSource | null;
}

/**
 * RF-08 [FE]: Servicio de sincronización en segundo plano e hidratación de
 * caché local en POS. Al iniciar, trae en lotes (delta por `updated_at`)
 * todo el catálogo nuevo/modificado desde la última sincronización exitosa,
 * lo persiste en localStorage, y luego mantiene una conexión SSE abierta
 * para reflejar cambios de precio/estado en tiempo real sin volver a
 * consultar el backend por polling.
 */
export const usePosSyncStore = defineStore('posSync', {
  state: (): PosSyncState => ({
    catalogoLocal: cargarCatalogoLocal(),
    ultimaSincronizacion: localStorage.getItem(STORAGE_KEY_LAST_SYNC),
    conectado: false,
    sincronizando: false,
    ultimoEvento: null,
    historialEventos: [],
    eventSource: null,
  }),

  getters: {
    totalProductosSincronizados: (state) => Object.keys(state.catalogoLocal).length,
    buscarPorSku: (state) => (sku: string) => state.catalogoLocal[sku.toUpperCase()] ?? null,
  },

  actions: {
    /** Hidrata la caché local trayendo todas las páginas pendientes desde la última sincronización. */
    async hidratarCacheLocal(forceFromBeginning = false) {
      if (this.sincronizando) return;
      this.sincronizando = true;
      try {
        let cursor: string | undefined;
        let hayMas = true;
        const since = forceFromBeginning ? undefined : (this.ultimaSincronizacion ?? undefined);
        let maxTimestamp = since;

        while (hayMas) {
          const pagina = await sincronizarCatalogoDelta(since, cursor);
          for (const item of pagina.items) {
            this._aplicarItem(item);
            if (!maxTimestamp || item.updated_at > maxTimestamp) {
              maxTimestamp = item.updated_at;
            }
          }
          hayMas = pagina.hay_mas;
          cursor = pagina.cursor_siguiente ?? undefined;
        }

        if (maxTimestamp) {
          this.ultimaSincronizacion = maxTimestamp;
          localStorage.setItem(STORAGE_KEY_LAST_SYNC, maxTimestamp);
        }
        this._persistirCatalogo();
      } catch (err) {
        console.warn('No se pudo sincronizar el catálogo local del POS:', err);
      } finally {
        this.sincronizando = false;
      }
    },

    /** Fuerza una resincronización completa trayendo todo el catálogo delta */
    async forzarResincronizacion() {
      await this.hidratarCacheLocal(true);
      this.ultimoEvento = 'Catálogo resincronizado completamente.';
    },

    /** Abre (o reabre) la suscripción SSE a cambios de catálogo en tiempo real. */
    iniciarEscuchaEnTiempoReal() {
      if (this.eventSource) return;
      this.eventSource = suscribirseACambiosDeCatalogo(
        (evento: any) => {
          this.historialEventos.unshift(evento);
          if (this.historialEventos.length > 30) {
            this.historialEventos.pop();
          }

          if (evento.tipo === 'sincronizacion_masiva' || evento.tipo === 'catalogo_resincronizado') {
            this.hidratarCacheLocal(true);
            this.ultimoEvento = 'Sincronización masiva ejecutada por el Administrador';
          } else if (evento.sku) {
            this._aplicarItem({
              id: evento.producto_id ?? evento.id,
              sku: evento.sku,
              nombre: evento.nombre,
              precio_referencia: evento.precio ?? 0,
              estado: evento.estado ?? 'publicado',
              updated_at: evento.updated_at ?? evento.emitido_en,
            } as SyncCatalogoItem);
            this._persistirCatalogo();
            this.ultimaSincronizacion = evento.emitido_en;
            localStorage.setItem(STORAGE_KEY_LAST_SYNC, evento.emitido_en);
            this.ultimoEvento = `${evento.tipo === 'producto_creado' ? 'Nuevo producto' : 'Precio actualizado'}: ${evento.nombre} (${evento.precio ? 'BOB ' + evento.precio : ''})`;
          }

          // Disparar evento para que vistas activas (POS, Marketplace) reaccionen
          try {
            window.dispatchEvent(new CustomEvent('maxiconecta:catalogo-actualizado', { detail: evento }));
          } catch {
            // Entorno sin window
          }
        },
        (conectado) => {
          this.conectado = conectado;
        }
      );
    },

    detenerEscuchaEnTiempoReal() {
      this.eventSource?.close();
      this.eventSource = null;
      this.conectado = false;
    },

    /** Punto de entrada único: hidrata y luego abre el canal en tiempo real. */
    async iniciar() {
      await this.hidratarCacheLocal();
      this.iniciarEscuchaEnTiempoReal();
    },

    _aplicarItem(item: SyncCatalogoItem) {
      if (item.accion === 'baja') {
        delete this.catalogoLocal[item.sku];
        return;
      }
      this.catalogoLocal[item.sku] = {
        id: item.id,
        sku: item.sku,
        nombre: item.nombre,
        precio_referencia: Number(item.precio_referencia),
        estado: item.estado,
        updated_at: item.updated_at,
      };
    },

    _persistirCatalogo() {
      localStorage.setItem(STORAGE_KEY_CATALOGO, JSON.stringify(this.catalogoLocal));
    },
  },
});

function cargarCatalogoLocal(): Record<string, ProductoLocal> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_CATALOGO);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}
