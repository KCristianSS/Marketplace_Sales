# 13. Bitácora de Cambios Técnicos — Rama `ft-seleccion-entrega` (US-15 / RF-15 / KAN-31)

Este documento registra de forma detallada y auditable el análisis, diseño de arquitectura, algoritmos logísticos, endpoints backend, esquemas Pydantic/TypeScript y componentes interactivos frontend implementados para la historia de usuario **KAN-31** y sus 4 subtareas asignadas en Jira.

---

## 1. Ficha Técnica del Release

| Atributo | Detalle |
| :--- | :--- |
| **Épica / Historia Jira** | **KAN-11 / KAN-31:** *Como Cliente, quiero seleccionar entre envío a domicilio o retiro en sucursal para elegir cómo recibir mi compra.* |
| **Requerimiento Funcional** | **RF-15 — Selección de Entrega** (Módulo 3: Marketplace Digital) |
| **Requerimientos Relacionados** | **RF-11** (Retiro en Sucursal / POS Click & Collect KAN-27), **RF-14** (Reserva Temporal), **RF-16** (Selección de Pago), **RF-45** (Facturación Electrónica CUF KAN-346 / KAN-367) |
| **Actor Principal** | Cliente Web / Marketplace |
| **Rama Git Sugerida** | `ft-seleccion-entrega` (en repositorios `backend` y `frontend`) |
| **Rama Base** | `main` / `master` |
| **Commit Backend** | `feat(be): algoritmo de calculo de flete segun zona y endpoint de sucursales habilitadas KAN-31` |
| **Commit Frontend** | `feat(fe): selector interactivo de despacho a domicilio vs retiro en sucursal con mapa de tiendas KAN-31` |

---

## 2. Matriz de Subtareas de Jira

| Código Subtarea | Tarea / Subtarea | Estimación | Tipo | Estado |
| :--- | :--- | :---: | :---: | :---: |
| **KAN-31-ST1** | `[BE]` Algoritmo de cálculo de costo de flete según zona y dirección de entrega | 3 h | Backend (FastAPI / Node) | **100% Completado** |
| **KAN-31-ST2** | `[BE]` Endpoint de consulta de sucursales habilitadas con stock para retiro | 3 h | Backend / Inventario | **100% Completado** |
| **KAN-31-ST3** | `[FE]` Paso 1 del Checkout con selector interactivo Domicilio vs Retiro | 3 h | Frontend (Vue 3 / Pinia) | **100% Completado** |
| **KAN-31-ST4** | `[FE]` Selector de sucursal con visualización de mapa o lista de tiendas con stock | 2 h | Frontend (Vue 3 / SVG) | **100% Completado** |
| **TOTAL** | **Historia de Usuario Completa KAN-31** | **11 h** | Full-Stack | **100% Completado** |

---

## 3. Subtarea 1: [BE] Algoritmo de Cálculo de Costo de Flete según Zona y Dirección de Entrega

### 3.1. Reglas de Negocio Implementadas
1. **Matriz de Tarifas por Ciudad y Zona Urbana (BOB):**
   - **La Paz:** Centro (BOB 15.00), Miraflores (BOB 15.00), Sopocachi (BOB 15.00), Zona Sur Calacoto/San Miguel (BOB 20.00), Achumani/Irpavi (BOB 22.00), Periférica/Laderas (BOB 25.00).
   - **El Alto:** Ceja (BOB 20.00), Ciudad Satélite (BOB 22.00), Villa Adela (BOB 25.00), Río Seco (BOB 28.00).
   - **Santa Cruz:** 1er a 4to Anillo (BOB 18.00), Equipetrol (BOB 18.00), Urubó (BOB 28.00), 5to a 8vo Anillo (BOB 25.00).
   - **Cochabamba:** Centro/El Prado (BOB 15.00), Cala Cala/Recoleta (BOB 18.00), Zona Sur (BOB 22.00), Sacaba/Quillacollo (BOB 30.00).
   - **Resto del País (Interdepartamental):** Sucre (BOB 35.00), Tarija (BOB 35.00), Oruro (BOB 30.00), Potosí (BOB 35.00), Beni/Pando (BOB 45-50.00).
2. **Bonificación Comercial (Flete Gratis):**
   - Si `subtotal_productos >= 500.00 BOB`, el costo de envío es `BOB 0.00` (`flete_gratis: true`).
3. **Ponderación por Sobrepeso:**
   - Para paquetes mayores a 5.0 kg, se añade un recargo de BOB 5.00 por cada kilogramo excedente.
4. **Modalidad Express:**
   - La opción `express_mismo_dia` agrega BOB 15.00 y garantiza entrega en menos de 4 horas hábiles.

### 3.2. Contrato de Endpoint
- **Ruta:** `POST /api/v1/ordenes/flete/calcular` (y `/api/v1/carrito/flete/calcular`)
- **Request Payload:**
```json
{
  "ciudad": "La Paz",
  "zona": "Zona Sur (Calacoto / San Miguel)",
  "direccion": "Calle 15 esq. Ballivián #802",
  "subtotal_productos": 550.00,
  "peso_estimado_kg": 2.0,
  "tipo_envio": "estandar"
}
```
- **Response Payload (200 OK):**
```json
{
  "ciudad": "La Paz",
  "zona": "Zona Sur (Calacoto / San Miguel)",
  "costo_flete": 0.0,
  "costo_original": 20.0,
  "flete_gratis": true,
  "umbral_flete_gratis": 500.0,
  "tiempo_estimado": "Entrega en 24 horas hábiles",
  "tipo_envio": "estandar",
  "mensaje": "¡Flete GRATIS aplicado por compras mayores a 500.00 BOB!",
  "desglose": {
    "tarifa_base_zona": 20.0,
    "recargo_peso": 0.0,
    "recargo_express": 0.0,
    "descuento_promocion": 20.0,
    "distancia_estimada_km": 6.5,
    "subtotal_evaluado": 550.0
  }
}
```

---

## 4. Subtarea 2: [BE] Endpoint de Consulta de Sucursales Habilitadas con Stock

- **Ruta:** `GET /api/v1/ordenes/sucursales/retiro` (con filtro opcional `?ciudad=La_Paz`)
- **Datos Georreferenciados:** Retorna red nacional de tiendas físicas con:
  - `id`: Identificador de sucursal (`suc-lpz-01`, `suc-lpz-02`, `suc-scz-01`, `suc-cbb-01`, etc.)
  - `nombre`: Nombre oficial de la tienda.
  - `direccion` y `referencia`: Ubicación física para el cliente.
  - `coordenadas`: `{ lat: -16.5028, lng: -68.1328 }` para mapa interactivo.
  - `stock_disponible`: Verificación de existencias para retiro inmediato.
  - `tiempo_preparacion`: "Listo para retiro en 2 horas".
  - `costo_retiro`: 0.00 BOB (100% gratuito).

---

## 5. Subtareas 3 y 4: [FE] Selector Interactivo de Despacho y Visualizador de Mapa

1. **Componente Reutilizable:** `src/components/DeliveryMethodSelector.vue`
   - Selector en 2 pestañas estilizadas:
     - 🚚 **Envío a Domicilio**: selectores dinámicos de ciudad y zona, dirección exacta, referencia, modalidad de servicio (Estándar vs Express Mismo Día) y badge de flete gratis.
     - 🏬 **Retiro en Sucursal (Click & Collect)**: filtro por ciudades, tarjetas con horarios, teléfonos y stock verificado.
2. **Visualizador de Mapa Interactivo:**
   - Mapa vectorial estilizado con calles, avenidas y pines geolocalizados de cada sucursal física.
   - Interactividad bidireccional: seleccionar en el mapa actualiza la tarjeta y viceversa.
   - Muestra de coordenadas GPS en tiempo real.
3. **Flujo Checkout Multi-Paso Integrado (`App.vue`):**
   - **Paso 1:** Selección de Entrega y Flete (KAN-31).
   - **Paso 2:** Datos Fiscales y Pago Online (KAN-346 / KAN-364).
   - **Paso 3:** Emisión de Factura Legal y Comprobante de Entrega con Código de Retiro / QR o Guía de Rastreo (compatible con KAN-27).
