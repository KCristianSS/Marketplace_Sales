# Tarjetas de regalo y administración

Historia: como Cliente quiero comprar y canjear tarjetas de regalo mediante un código único para pagar parte o toda una compra con saldo prepagado. La administración puede emitir tarjetas, consultar su historial, bloquearlas, reactivarlas, anularlas y regenerar sus códigos.

## Activación

1. Aplicar `db/migrations/20261022_confirmar_orden_atomica.sql` si aún no está desplegada y después `db/migrations/20261105_tarjetas_regalo.sql` en Supabase. Las instalaciones nuevas con `db/schema.sql` incluyen los vales.
2. Configurar `SUPABASE_SERVICE_ROLE_KEY` en el servicio de órdenes. Las tablas y los RPC de vales no conceden acceso a `anon` ni `authenticated`; la autorización se realiza con JWT en el backend y RBAC en el gateway.
3. Generar `VALES_CODIGO_SECRET` con `python -c "import secrets; print(secrets.token_urlsafe(48))"` y guardarlo en el entorno del servicio de órdenes. Es independiente de JWT, debe tener al menos 32 caracteres y conservarse entre despliegues. Cambiarlo afecta la recuperación de códigos emitidos: no rotarlo sin una migración explícita.
4. En staging/production configurar `PAGOS_WEBHOOK_SECRET` y acordar el protocolo de firma con Pagos. En esos entornos la simulación de webhooks está deshabilitada y los vales rechazan respuestas `mock_fallback` del proveedor.
5. Reiniciar órdenes y gateway. Cliente: **Mi cuenta → Tarjetas de regalo** (`/tarjetas-regalo`). Administración: **Panel administrativo → Tarjetas de regalo**.

## Reglas de la primera versión

- BOB, con dos decimales. Compra o emisión desde Bs 0.01 hasta Bs 10000.
- Tarjetas compradas sin vencimiento; en la emisión administrativa puede definirse una fecha futura.
- Código transferible: cualquier cliente autenticado que posea el código puede gastarlo. El comprador original puede recuperar el código y consultar movimientos; no se expone el historial de otra persona al consultar saldo por código.
- Un vale por checkout de Marketplace, con canje total o parcial. El resto se paga por QR, tarjeta o pasarela. El saldo sobrante se conserva; no se entrega cambio en efectivo. El canje POS queda fuera de esta versión.
- No se permite comprar un vale con otro vale. La emisión administrativa es una asignación autorizada de saldo sin cobro y requiere identificar al comprador y registrar el motivo; no equivale a una compra bancaria.
- Estados persistidos: activa, bloqueada y anulada. El saldo cero y el vencimiento también impiden canjear. Una anulación es definitiva y no reembolsa automáticamente la compra del vale; el saldo queda registrado para revisión administrativa.
- No hay borrado de tarjetas, edición libre del saldo ni recargas. Las devoluciones de órdenes reintegran únicamente el aporte original del vale y son idempotentes. Un vale bloqueado o vencido conserva ese estado al recibir una devolución.
- Gestionar estado o regenerar código requiere motivo y ausencia de reservas activas. Regenerar invalida el código anterior y mantiene saldo e historial.

## API

Todos los endpoints de vales están bajo `/api/v1/ordenes/vales` y exigen JWT. Las rutas `/admin` requieren `administrador` o `gerente_comercial`, incluso accediendo directamente al microservicio.

| Método y ruta | Función |
|---|---|
| `GET /` | Mis tarjetas (hasta 100) |
| `POST /comprar` | Emite una tarjeta a partir de `transaccion_id` aprobado, propio y con propósito `vale` |
| `POST /consultar` | Consulta disponible con `{codigo}` |
| `POST /reservas` | Reserva `min(saldo,total)` con `{codigo,checkout_id,total}` |
| `DELETE /reservas/{id}` | Libera una reserva propia todavía no consumida |
| `GET /{id}/codigo` | Recupera código para comprador o administrador |
| `GET /{id}/movimientos?offset=0` | Historial por páginas de 100, para comprador o administrador |
| `GET /admin` | Filtros `estado`, `comprador_id`, `ultimos` (8 caracteres), `offset`; páginas de 50 |
| `POST /admin` | Emisión con `solicitud_id` UUID idempotente, `comprador_id`, `monto`, `motivo`, `vence_en` opcional |
| `PATCH /admin/{id}/estado` | `{estado,motivo}` |
| `POST /admin/{id}/regenerar` | `{motivo}` |

Compra: iniciar el cobro existente en `POST /api/v1/pagos/iniciar` con `proposito: "vale"` y `cliente_id` igual al JWT. Tras aprobación, llamar a `/vales/comprar`. Repetir la emisión con la misma transacción devuelve la misma tarjeta y no genera otro saldo. La pantalla permite recuperar el pago pendiente sin volver a cobrar.

Canje: reservar saldo para la reserva de stock (`checkout_id = reserva_id`). Si hay diferencia, iniciar un pago con `vale_reserva_id` y el importe restante. Al crear la orden incluir `vale_reserva_id` y, cuando corresponda, `transaccion_id` del cobro restante. El backend reconstruye el desglose con importes de la reserva y del pago aprobado; no acepta un tramo `vale` enviado libremente por el cliente.

## Consistencia y seguridad

Los códigos contienen 128 bits derivados con HMAC-SHA256 y una versión por tarjeta. La BD guarda un hash del código normalizado, su versión y los últimos ocho caracteres. No se guardan códigos completos en movimientos, pagos ni URLs.

`operar_vale` bloquea la fila de la tarjeta para serializar operaciones concurrentes. Reservar reduce el saldo disponible, consumir confirma la reserva sin descontar otra vez y liberar/reintegrar restituyen ese importe una sola vez. Reservas de 15 minutos: se limpian al operar sobre esa tarjeta; los listados calculan también el saldo liberable por vencimiento. No se necesita un proceso residente para recuperar un saldo retenido.

`confirmar_orden_con_vale` consume el vale y llama a `confirmar_orden_atomica` dentro de una sola transacción PostgreSQL. Si falla la orden, se revierte el consumo. No hay fallback a memoria ni persistencia por pasos para canjes. Las compensaciones de órdenes restituyen el aporte del vale localmente y revierten el tramo bancario mediante el adaptador de Pagos.

## Interoperabilidad ERP

- **RIO-PAG-01:** la compra del vale cobra el monto completo; el pago mixto cobra externamente solo la diferencia. `vale` es un medio interno y no se manda a la pasarela como si fuera una tarjeta bancaria.
- **RIO-PAG-03 / RIO-CON-04:** cancelar una orden revierte el tramo bancario y reintegra el vale, conservando el desglose para la reversión contable.
- **RIO-CON-01:** `OrderPaidEvent` incluye `vale` y su importe en `desglose_pagos` y `totales_por_metodo` cuando se utiliza para pagar una venta.
- La emisión de saldo no se publica como una venta de productos ni genera stock o despacho. El registro contable externo específico de la emisión de saldo queda pendiente de acordar con Contabilidad; no se inventa un contrato RIO para ello.

Firma del webhook en staging/production: el adaptador de Pagos envía `firma_hmac` hexadecimal con HMAC-SHA256 usando `PAGOS_WEBHOOK_SECRET`, sobre el texto UTF-8 `transaccion_id|evento|monto`. El monto se escribe con dos decimales; si se omite, el último segmento está vacío. El secreto nunca llega al frontend. Este es el contrato del adaptador MaxiConecta y debe alinearse con el proveedor real antes de habilitar cobros reales.

## Verificación

`npm run check:vales` y `npm test -- src/components/TarjetasRegaloPanel.test.ts` en frontend.

Para probar transacciones PostgreSQL reales, configurar `VALES_TEST_DSN` hacia un PostgreSQL **local** de pruebas con permisos de crear bases y ejecutar `python -m pytest backend/tests/test_tarjetas_regalo.py -q` desde el directorio superior de backend. Se crea y elimina una base `vales_test_<uuid>`; nunca se usa la BD de Supabase. Sin esa variable, solo se ejecuta la prueba independiente de códigos y las pruebas SQL quedan omitidas explícitamente.
