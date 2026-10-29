# Diseño de emisión de facturas legales en POS

## Propósito y alcance

Este diseño responde a US-10: emitir y entregar al cliente un comprobante de venta y, cuando la autoridad fiscal lo autorice, su factura electrónica. Describe el flujo del POS actual y el flujo objetivo para completar la integración RIO-PAG-02; no implica que el sistema ya esté conectado al SIN/SIAT ni sustituye la validación del contrato fiscal por el ERP.

La frontera propuesta conserva al **MS POS** como orquestador de la venta de mostrador y a `PagosClient` como adaptador al ERP externo de Pagos y Facturación. La comunicación con el SIN/SIAT, certificados, credenciales y contingencias fiscales pertenecen al ERP/proveedor autorizado, salvo que el contrato real indique otra cosa. No se propone un nuevo microservicio para esta historia.

## Estado actual del sistema

| Paso | Implementación encontrada |
| --- | --- |
| Inicio desde caja | `PosView.vue` envía `POST /api/v1/pos/ventas/cobrar` por el gateway y solicita después la impresión mediante `window.print()` con formato de 80 mm. |
| Validación y cálculo | `procesar_venta_pos` exige una caja abierta, calcula subtotales e IVA incluido del 13%, y construye el detalle fiscal. |
| Emisión externa | `PagosClient.emitir_factura` invoca `POST {ERP_PAGOS_URL}/api/v1/facturas/emitir` (RIO-PAG-02). La respuesta debe contener `numero_factura` y `cuf`; `cufd` y URL/QR son opcionales. |
| QR y comprobante | Si el ERP no da URL de QR, POS construye una URL de consulta del entorno piloto SIAT y genera una imagen SVG data URL. Devuelve el ticket en la respuesta; el navegador lo presenta e imprime. |
| Persistencia | El flujo POS no guarda la factura ni la venta en un repositorio durable. El modelo de órdenes tiene `cuf_factura`, pero este endpoint POS no crea una orden mediante MS Órdenes. |
| Fallback ERP | `BaseERPClient` devuelve `status=fallback` ante error HTTP. `PagosClient` responde con número y CUF sintéticos; por ello, que POS reciba ambos valores no demuestra autorización fiscal. Ese modo debe considerarse exclusivamente de pruebas. |
| Pago | Este endpoint recibe `metodo_pago` y contabiliza el total en la caja, pero no invoca `RIO-PAG-01` para autorizar un pago electrónico. Para efectivo, tarjeta y QR debe definirse cuál es la evidencia de pago confirmado antes de emitir la factura. |

## Diagrama de clases

Leyenda: `<<actual>>` corresponde a código o contrato existente; `<<propuesto>>` es una responsabilidad/modelo que conviene formalizar antes de habilitar facturación legal en producción.

```mermaid
classDiagram
    direction LR

    class PosView {
        <<actual>>
        +finalizarCobro()
        +imprimirTicket()
    }
    class VentaPOSRequest {
        <<actual>>
        +caja_id
        +sucursal_id
        +cliente_nit_ci
        +cliente_razon_social
        +items
        +metodo_pago
    }
    class ItemVentaPOS {
        <<actual>>
        +variante_id
        +sku
        +nombre
        +cantidad
        +precio_unitario
    }
    class POSRouter {
        <<actual>>
        +procesar_venta_pos(request)
        +calcular_iva_incluido(total)
        +generar_qr(url)
    }
    class PagosClient {
        <<actual>>
        +emitir_factura(datos_fiscales)
    }
    class BaseERPClient {
        <<actual>>
        +post(path, payload)
        +timeout
    }
    class ResultadoEmisionFiscal {
        <<propuesto>>
        +estado
        +numero_factura
        +cuf
        +cufd
        +qr_url
        +documento_fiscal_ref
    }
    class FacturaFiscal {
        <<propuesto>>
        +id
        +venta_id
        +estado
        +idempotency_key
        +registrarAutorizacion(resultado)
        +marcarPendiente(motivo)
    }
    class RepositorioFactura {
        <<propuesto>>
        +buscarPorIdempotencyKey(key)
        +guardar(factura)
    }
    class VentaPOSResponse {
        <<actual>>
        +orden_id
        +subtotal_neto
        +monto_iva
        +total
        +numero_factura
        +cuf
        +cufd
        +qr_url
        +qr_code
        +ticket_impresion
    }
    class Ticket80mm {
        <<actual inline>>
        +renderizar(respuesta)
    }
    class ERPFacturacion {
        <<externo RIO-PAG-02>>
        +emitir(datos_fiscales)
    }
    class SIN_SIAT {
        <<externo al ERP>>
        +autorizarSegunModalidad(documento)
    }

    PosView ..> VentaPOSRequest : envia
    VentaPOSRequest "1" *-- "1..*" ItemVentaPOS : incluye
    PosView ..> VentaPOSResponse : recibe
    POSRouter ..> VentaPOSRequest : valida y calcula
    POSRouter ..> PagosClient : solicita emision
    POSRouter ..> RepositorioFactura : persistencia propuesta
    POSRouter ..> Ticket80mm : formato actual
    PagosClient --|> BaseERPClient
    PagosClient ..> ERPFacturacion : RIO-PAG-02
    ERPFacturacion ..> SIN_SIAT : gestionado externamente
    ERPFacturacion ..> ResultadoEmisionFiscal : respuesta tipada propuesta
    FacturaFiscal --> ResultadoEmisionFiscal : registra
    RepositorioFactura --> FacturaFiscal : persiste
    POSRouter ..> VentaPOSResponse : construye
    VentaPOSResponse ..> PosView : JSON
```

### Responsabilidades y contratos

- `POSRouter` valida caja, consolida el detalle y prepara los importes; no debería decidir qué respuesta del modo mock es legalmente válida.
- `PagosClient` encapsula RIO-PAG-02. Conviene sustituir su `Dict[str, Any]` por un request/response tipado y exponer explícitamente si la respuesta proviene del ERP real o de un mock.
- `FacturaFiscal` y `RepositorioFactura` son propuestas para conservar el resultado fiscal, idempotencia y estado tras reinicios. La clave única debe evitar emitir dos facturas por reintentos del mismo cobro.
- `Ticket80mm` representa hoy el string `ticket_impresion` más la plantilla Vue/estilos `@media print`; no hay un driver de impresora ni una clase de impresión física en backend.
- El documento legal, XML/PDF o URL de descarga solo deben modelarse como propiedades requeridas después de confirmar qué entrega realmente el ERP.

## Diagrama de secuencia objetivo

Este flujo conserva el endpoint actual y muestra los controles que hacen falta antes de tratar el resultado como factura legal. El pago debe estar confirmado según el medio utilizado; RIO-PAG-01 no está invocado por el endpoint POS actual.

<!-- mermaid-checked: every participant uses `participant Id as "Label"`, no \n in aliases/messages/notes, every alt/opt/loop closed by end, no `:` inside any alias -->
```mermaid
sequenceDiagram
    autonumber
    participant Cajero as "Cajero"
    participant PosUI as "POS Vue"
    participant Gateway as "API Gateway"
    participant PosSvc as "MS POS"
    participant FactRepo as "Repositorio fiscal propuesto"
    participant Pagos as "PagosClient"
    participant ERP as "ERP Pagos y Facturacion"
    participant SIAT as "SIN SIAT gestionado por ERP"
    participant Browser as "Impresion del navegador"

    Cajero->>PosUI: Confirmar venta con pago aprobado
    PosUI->>Gateway: POST /api/v1/pos/ventas/cobrar
    Gateway->>PosSvc: Reenviar solicitud autenticada
    PosSvc->>PosSvc: Validar caja y calcular detalle e IVA
    Note over PosSvc,Pagos: El endpoint actual no confirma pagos con RIO-PAG-01
    PosSvc->>FactRepo: Buscar clave de idempotencia propuesta
    alt Factura ya emitida para la solicitud
        FactRepo-->>PosSvc: Devolver factura fiscal existente
    else Emision nueva
        PosSvc->>Pagos: emitir_factura(datos fiscales)
        Pagos->>ERP: POST /api/v1/facturas/emitir RIO-PAG-02
        ERP->>SIAT: Solicitar autorizacion fiscal
        SIAT-->>ERP: Resultado fiscal y codigo autorizado
        ERP-->>Pagos: numero_factura, CUF, CUFD, QR y documento
        Pagos-->>PosSvc: Resultado de emision
        alt Autorizacion real valida
            PosSvc->>FactRepo: Guardar factura autorizada antes de responder
        else Fallback mock, timeout o respuesta incompleta
            PosSvc->>FactRepo: Registrar pendiente o rechazada sin simular CUF legal
            PosSvc-->>Gateway: Error controlado sin ticket fiscal
            Gateway-->>PosUI: Mostrar que la factura no fue confirmada
        end
    end
    opt Factura autorizada
        PosSvc->>PosSvc: Construir QR y ticket de 80 mm
        PosSvc-->>Gateway: 201 con factura y comprobante
        Gateway-->>PosUI: Respuesta fiscal verificable
        PosUI-->>Cajero: Mostrar factura y opcion de imprimir
        Cajero->>PosUI: Solicitar impresion o reimpresion
        PosUI->>Browser: window.print con CSS de 80 mm
        Browser-->>Cajero: Comprobante impreso
    end
```

## Decisiones y brechas para cerrar

1. **Contrato legal:** confirmar si el ERP es quien se conecta al SIN/SIAT y qué modalidad, campos, códigos (CUF/CUFD), QR, XML/PDF, respuesta de autorización y contingencias son obligatorios. En Bolivia, “timbrado” debe mapearse a la terminología y flujo que valide el proveedor/SIN; no asumir un timbrado genérico.
2. **Pago antes de factura:** definir cómo se comprueba el pago de efectivo, tarjeta y QR. Para medios electrónicos, conectar/confirmar RIO-PAG-01 antes de emitir RIO-PAG-02; evitar facturar ventas rechazadas.
3. **Fallback no legal:** el CUF y número generados por `mock_fallback` solo sirven para desarrollo/pruebas. En producción, configurar un modo de prueba explícito y bloquear cualquier presentación como factura legal si no hay autorización fiscal real.
4. **Persistencia e idempotencia:** guardar solicitud, respuesta, CUF y estado de emisión con clave única antes de entregar el comprobante. Un timeout deja estado recuperable; reintentar debe consultar/recuperar la misma emisión antes de enviar otra.
5. **Impresión y reimpresión:** distinguir factura autorizada de impresión completada. Si el navegador o impresora falla, conservar la factura y permitir reimprimir sin volver a emitirla.
6. **Consistencia de venta:** acordar el orden entre cobro, factura y descuento de inventario. Son servicios separados y no comparten una transacción; diseñar compensación/conciliación para fallos parciales.
7. **Entrega del documento:** el frontend actual imprime el HTML del ticket con QR; confirmar si eso satisface el formato tributario o si el ERP debe entregar una representación fiscal oficial para imprimir/descargar.

## Criterio de aceptación del diseño

- Los diagramas distinguen componentes existentes de responsabilidades propuestas.
- La secuencia cubre autorización, respuesta inválida/fallback, persistencia, impresión y reimpresión.
- Queda explícito que `mock_fallback` no acredita validez tributaria y que el contrato legal depende del ERP y del SIN/SIAT.
- No se implementan cambios de API ni persistencia en esta tarea de diseño.