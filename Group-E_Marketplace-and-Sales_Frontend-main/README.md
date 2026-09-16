# MaxiConecta — Repositorio Frontend

Aplicación cliente desarrollada con **Vue 3**, **TypeScript**, **Vite**, **Pinia** y **Tailwind CSS**.

## 🖥️ Portales de Usuario

El frontend unifica las tres experiencias requeridas por el sistema:
1. **Marketplace Digital (`/marketplace`):** Catálogo facetado, búsqueda en tiempo real, carrito persistente en Redis y checkout.
2. **Punto de Venta Físico (`/pos`):** Interfaz para cajeros optimizada para escáner de código de barras, turnos, comprobantes y suspensión de ventas.
3. **Panel Administrativo (`/admin`):** Dashboard con KPIs en tiempo real, monitoreo de ventas, alertas de quiebre de stock y cotizaciones B2B.

## 🚀 Comandos de Desarrollo

```powershell
# Instalar dependencias
npm install

# Iniciar servidor de desarrollo en puerto 5173
npm run dev

# Compilar para producción y verificación de tipos TypeScript
npm run build
```

## 🌐 Conexión al Backend
Por defecto, las peticiones se dirigen al **API Gateway** en `http://localhost:8000`. Puedes configurar la URL en el archivo `.env`.
