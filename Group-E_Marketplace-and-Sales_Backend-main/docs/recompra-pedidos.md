# Repetir un pedido

Desde Mi cuenta → Historial de compras, el cliente puede pulsar **Repetir pedido**
en la tarjeta o en el detalle. Se abre el carrito con los productos que se pudieron
agregar y los avisos de disponibilidad, ajustes de cantidades y precios.

## Contrato

`POST /api/v1/ordenes/{id}/repetir`, sin cuerpo, requiere JWT con rol `cliente` y
que el pedido pertenezca al usuario autenticado. Devuelve `orden_id`, `items` y
`avisos`. Cada ítem contiene `variante_id`, `variante_original_id`, `sku`, `nombre`,
`cantidad`, `precio_unitario` y `stock_disponible`.

La operación prepara la recompra sin modificar pedidos ni generar cobros o
reservas; por ello se puede reintentar sin duplicar efectos en el servidor.
La fusión se realiza en el store Pinia porque el carrito actual persiste en
localStorage y recién se sincroniza con el servicio de carrito durante checkout.
El store bloquea solicitudes concurrentes desde historial y detalle, y aplica
cada respuesta una sola vez. Una acción posterior permite volver a agregar el
pedido, respetando el stock disponible.

## Reglas

- Se usan catálogo publicado, precios vigentes del canal web retail y stock
  consultado mediante el adaptador de Inventarios (RIO-INV-01).
- Se conserva la variante original. Si un pedido antiguo guardó el ID del
  producto, se admite la variante con SKU coincidente o una única variante sin
  ambigüedad; las opciones eliminadas no se sustituyen por otra.
- La resolución de precios respeta la tarifa de la variante seleccionada y las
  listas vigentes; no usa tarifas de otras variantes del mismo producto.
- Se conservan los otros productos del carrito y se suman unidades de la misma
  variante. El stock se calcula por SKU, contando lo que ya existe en el carrito.
- Se informa cualquier precio cambiado y se recalcula el total de la línea al
  precio vigente. No se copian cupones, fletes ni descuentos históricos.
- Los productos sin catálogo, sin precio en BOB, agotados o con stock no
  verificable se omiten con aviso. Si ninguno se agrega, el carrito se conserva.
- Una falla de catálogo/precios devuelve 503 y permite reintentar sin modificar
  el carrito. Una reserva activa impide la recompra hasta terminar o cancelar el
  checkout.
- El checkout habitual sigue siendo responsable de reservar stock con TTL y
  procesar el pago. La disponibilidad de recompra no constituye una reserva.

## Configuración y verificación

El servicio de órdenes consulta catálogo mediante `MS_CATALOGO_URL`. El valor
por defecto local es `http://localhost:8001`; Docker Compose configura
`http://ms-catalogo:8001`. No se requieren cambios de base de datos.

Desde la raíz del workspace:

```powershell
python -m pytest backend/tests/test_recompra.py backend/tests/test_catalogo_batch_loading.py -q
python -m pytest backend/tests/test_historial_ordenes.py backend/tests/test_reserva_stock.py -q
```

Desde `frontend/`:

```powershell
npm test
npm run check:recompra
npm run build
```

Las pruebas cubren autorización y aislamiento del cliente, precios por variante,
productos omitidos, reintentos sin efectos de compra, conservación del carrito,
límites de stock compartido, doble clic y acciones desde historial/detalle.

La compilación global encuentra dos errores de sintaxis previos en
`src/views/pos/PosView.vue` (comas faltantes en las líneas 47 y 897). La verificación
`check:recompra` comprueba los componentes de esta historia, el store, sus pruebas,
la cuenta y App independientemente de esa vista. Se repararon declaraciones
truncadas y duplicadas que ya existían en AccountView para habilitar el historial.
