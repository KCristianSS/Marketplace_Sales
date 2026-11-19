# Cotización de flete en checkout

El checkout consulta `POST /api/v1/ordenes/flete/calcular` al cambiar destino,
modalidad, cupón, puntos o reserva. Las solicitudes requieren ciudad, zona,
dirección y `reserva_id`; aceptan `referencia`, `cupon`, `puntos_canjeados` y
`tipo_envio` (`estandar` o `express_mismo_dia`). Sin reserva, el endpoint permite
consultar una tarifa orientativa, pero no emite una cotización para pagar.

La respuesta incluye costo en BOB, plazo estimado, total, `cotizacion_flete`
firmada y `expira_en` como timestamp Unix en segundos. La firma vincula destino,
productos, cliente, descuentos, total y reserva. El subtotal se obtiene de los
productos reservados; el cupón se valida contra el servicio de carrito.

Las reglas se administran en **Administración → Envíos**, con acceso para
`administrador` y `gerente_comercial`. Se pueden agregar o editar ciudades y
zonas, desactivar cobertura, habilitar estándar o express por zona y definir
sus plazos. Las tarifas y condiciones generales son editables.

Valores iniciales (se conservan para comenzar):

- Se inicia con las tarifas locales por ciudad y zona. Se rechazan destinos sin cobertura.
- Flete gratis desde BOB 500 en productos después del cupón y antes de puntos.
- Como el catálogo no tiene pesos, se estima 1,5 kg por unidad en el servidor.
  Por encima de 5 kg se cobran BOB 5 por kg adicional.
- Express añade BOB 15; la bonificación de flete cubre también los recargos.
- Los plazos son estimados según las reglas locales. No se consulta un transportista.
- La cotización dura hasta 15 minutos, limitada por el vencimiento de la reserva.

## Administración de envíos

1. Iniciar sesión como administrador o gerente comercial y abrir `/admin`.
2. Elegir la pestaña **Envíos** y modificar las reglas generales o las zonas.
3. En el formulario de zona, **Aplicar a la configuración** agrega el cambio
   al borrador. **Guardar configuración** guarda todos los cambios juntos.
4. Las nuevas cotizaciones usan los valores guardados. Los checkouts abiertos
   consultan opciones actualizadas cada 30 segundos, excepto durante un pago.
5. Una cotización firmada ya emitida conserva su precio hasta vencer aunque
   se modifiquen tarifas o cobertura. Las órdenes anteriores guardan su propia copia.

`GET /api/v1/ordenes/flete/opciones` publica solo las zonas activas y sus
modalidades. El checkout obtiene de allí las ciudades, zonas, plazos y promoción;
ya no mantiene una lista fija de destinos ni un monto fijo de envío gratis.

`GET /api/v1/ordenes/flete/configuracion` y `PUT` sobre esa misma ruta requieren
rol autorizado tanto en el gateway como en el servicio. El `PUT` recibe
`{version, configuracion}`. Cada actualización incrementa la versión y registra
autor y fecha. Si dos administradores editan la misma versión, el segundo recibe
409 y debe recargar: sus cambios no sobrescriben los del primero.

Supabase guarda el documento completo en `flete_configuracion`; el trigger
registra los valores anteriores y nuevos en `flete_configuracion_historial`.
Ambas tablas están protegidas con RLS y se accede desde el backend con la clave
de servicio. Una falla de la base de datos devuelve un error y no sustituye
tarifas guardadas por valores iniciales. Solo en desarrollo sin base configurada
se permite memoria temporal, identificada con un aviso en la pantalla.

`POST /api/v1/pagos/iniciar` recibe `tipo_despacho` y `cotizacion_flete`.
Para domicilio con reserva exige firma vigente, cliente y productos coincidentes,
moneda BOB y monto igual al total cotizado antes de llamar al ERP de pagos.
La transacción conserva la cotización en su payload persistido.

La creación de una orden web a domicilio con reserva requiere el token y la
transacción aprobada correspondiente. Comprueba subtotal, descuentos, flete,
total y productos. Una cotización aceptada al iniciar el cobro sigue siendo
válida para esa transacción cuando el pago termina; se conserva la validación
existente de la reserva de stock. La orden guarda una copia del destino,
modalidad, costo y plazo en `entrega` y la envía al servicio de despachos.

El frontend invalida inmediatamente los resultados anteriores, espera 300 ms
para agrupar cambios, descarta respuestas fuera de orden, muestra errores con
reintento y bloquea el pago sin una cotización vigente. Durante el cobro se
bloquean los controles y se conserva la selección aceptada aunque venza la
cotización mientras se espera la aprobación.

## Base de datos

Aplicar `db/migrations/20261102_cotizacion_flete.sql` antes de desplegar el backend.
Agrega `ordenes.entrega` (JSONB) y actualiza el RPC de confirmación atómica.
Aplicar también `db/migrations/20261103_administracion_envios.sql`, que crea la
configuración, su historial y las tarifas iniciales. Si ya se aplicó la primera
migración, basta ejecutar la segunda. La migración administrativa no sobrescribe
una configuración existente. Reiniciar el backend y actualizar el frontend.
Los esquemas para instalaciones nuevas incluyen ambos cambios.

## Verificación

- Backend: `pytest backend/tests/test_administracion_flete.py backend/tests/test_flete_checkout.py backend/tests/test_pagos.py backend/tests/test_reserva_stock.py backend/tests/test_persistencia_orden_sin_rpc.py` desde el directorio padre del paquete `backend`.
- Frontend: `npm test`, `npm run check:checkout` y `npm run build`.
- Revisar manualmente una dirección guardada sin zona, cambio rápido de destino,
  error de conexión, cupón, puntos, envío gratis, vencimiento y aprobación de QR.

En esta copia del repositorio la compilación general está bloqueada por errores
de sintaxis previos en `AccountView.vue` y `PosView.vue`. La ampliación de pruebas
a POS y clientes también encuentra errores previos al importar sus routers.
El checkout se verificó mediante comprobación de tipos y compilación aisladas.
