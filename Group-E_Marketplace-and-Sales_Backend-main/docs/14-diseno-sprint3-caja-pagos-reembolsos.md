# Diseño Sprint 3 — Arqueo ciego, movimientos de efectivo, validación de pagos y reembolsos

Historias: **KAN-341**, **KAN-342**, **KAN-54**, **KAN-55**. Tareas [DIS] de cada historia (diagramas de clases y de secuencia, Mermaid).
Toda integración con otros sistemas del ERP (Contabilidad, Pagos) es **simulada**: si el ERP no responde, los clientes devuelven una respuesta local (`modo: mock_fallback`).

---

## KAN-341 — Arqueo ciego

### Diagrama de clases
```mermaid
classDiagram
    class CajaTurno {
        +UUID id
        +UUID cajero_id
        +UUID sucursal_id
        +Decimal fondo_inicial
        +Decimal total_efectivo
        +estado: abierta|cerrada
        +bool con_diferencia
        +Decimal monto_cierre_real
        +Decimal diferencia
    }
    class ArqueoCaja {
        +UUID id
        +string numero_reporte
        +Decimal total_esperado
        +Decimal total_declarado
        +Decimal diferencia
        +estado_cuadre: cuadrado|sobrante|faltante
        +bool con_diferencia
        +dict notificacion_contabilidad
    }
    class DenominacionDeclarada {
        +tipo: billete|moneda
        +Decimal denominacion
        +int cantidad
        +Decimal subtotal
    }
    class ArqueoService {
        +ejecutar_arqueo_ciego(caja_id, desglose, obs, user)
        +obtener_reporte_arqueo(caja_id, user)
        -normalizar_desglose()
    }
    class MovimientoEfectivoService {
        +movimientos_netos(caja_id)
    }
    class ContabilidadClient {
        +notificar_arqueo_con_diferencia(data)
    }
    CajaTurno "1" --> "0..1" ArqueoCaja : se arquea una sola vez
    ArqueoCaja "1" *-- "1..11" DenominacionDeclarada : arqueo_detalle
    ArqueoService ..> CajaTurno
    ArqueoService ..> ArqueoCaja
    ArqueoService ..> MovimientoEfectivoService : opcional (0 si no existe)
    ArqueoService ..> ContabilidadClient : simulado
```

### Secuencia del cierre ciego
```mermaid
sequenceDiagram
    actor C as Cajero
    participant FE as ArqueoCiegoView
    participant API as POST /pos/caja/{id}/arqueo-ciego
    participant S as ArqueoService
    participant DB as caja_turnos / arqueo_caja / arqueo_detalle
    participant CON as ContabilidadClient (simulado)
    C->>FE: Ingresa cantidades por denominación (sin ver totales)
    FE->>API: desglose + observaciones
    API->>S: ejecutar_arqueo_ciego()
    S->>DB: Lee caja; si estado != abierta → 409
    S->>S: esperado = fondo + ventas efectivo + movimientos netos
    S->>S: declarado = Σ denominación × cantidad; diferencia = declarado − esperado
    S->>DB: UPDATE caja_turnos SET estado='cerrada' WHERE estado='abierta' (atómico)
    S->>DB: INSERT arqueo_caja + arqueo_detalle (inmutables) y audit_logs
    alt diferencia ≠ 0
        S->>CON: notificar_arqueo_con_diferencia()
        CON-->>S: recibida (o mock_fallback)
    end
    S-->>API: reporte
    API-->>FE: 201 reporte (recién ahora se revelan los totales)
    FE-->>C: Reporte imprimible de sobrante/faltante
```

---

## KAN-342 — Movimientos de efectivo

### Diagrama de clases
```mermaid
classDiagram
    class CajaTurno { +UUID id +Decimal fondo_inicial +Decimal total_efectivo +estado }
    class MovimientoEfectivo {
        +UUID id
        +tipo: entrada|retiro
        +Decimal monto
        +string motivo
        +bool requiere_supervisor
        +string supervisor_id
        +string numero_comprobante
        +dict comprobante
    }
    class MovimientoEfectivoService {
        +registrar_movimiento_efectivo(caja, tipo, monto, motivo, user, supervisor_token)
        +movimientos_netos(caja_id) Decimal
        +efectivo_disponible(caja)
        +resolver_supervisor(user, token)
        +limite_seguridad() Decimal
    }
    CajaTurno "1" --> "*" MovimientoEfectivo
    MovimientoEfectivoService ..> MovimientoEfectivo
```

### Secuencia de retiro con confirmación de supervisor
```mermaid
sequenceDiagram
    actor C as Cajero
    actor S as Supervisor
    participant FE as Modal de movimiento
    participant API as POST /pos/caja/{id}/movimientos
    participant SV as MovimientoEfectivoService
    C->>FE: Retiro Bs. 2.500 + motivo
    FE->>API: {tipo: retiro, monto, motivo}
    API->>SV: valida motivo, caja abierta, saldo disponible
    SV-->>API: 428 SUPERVISOR_REQUERIDO (monto > límite Bs. 2.000)
    API-->>FE: 428
    FE->>S: Solicita credenciales del supervisor
    S->>FE: correo + contraseña (login sin cambiar la sesión del cajero)
    FE->>API: {…, supervisor_token}
    API->>SV: supervisor con rol administrador/supervisor y distinto del cajero
    SV->>SV: INSERT caja_movimientos + comprobante + audit_logs
    API-->>FE: 201 comprobante imprimible
```

---

## KAN-54 — Validación de pagos de una orden

### Diagrama de clases
```mermaid
classDiagram
    class Orden { +UUID id +Decimal total +estado: pendiente|confirmada|... }
    class PagoOrden {
        +UUID id
        +string transaccion_id (único)
        +metodo
        +Decimal monto
        +estado: pendiente|aprobado|rechazado|reembolsado
        +int intento
        +UUID caja_turno_id
        +Decimal monto_reembolsado
    }
    class ValidacionPago {
        +registrar_pago(orden, metodo, monto, user)
        +procesar_webhook(pago, evento)
        -reevaluar_orden()
        +resumen(orden_id)
    }
    class MaquinaEstados { +validar(actual, nuevo) }
    class PagosClient { +procesar_cobro() }
    class HistorialPago { +tipo +estado_anterior +estado_nuevo +origen +usuario_id }
    Orden "1" --> "*" PagoOrden
    Orden "1" --> "*" HistorialPago
    ValidacionPago ..> PagoOrden
    ValidacionPago ..> MaquinaEstados
    ValidacionPago ..> PagosClient : simulado
```

### Secuencia de validación por webhook
```mermaid
sequenceDiagram
    actor C as Cajero / Cliente
    participant API as ms-ordenes
    participant V as PagoValidationService
    participant PG as Pasarela (simulada)
    C->>API: POST /pagos/registrar (qr, Bs. 60)
    API->>V: registrar_pago()
    V->>PG: procesar_cobro() → token / QR
    V-->>C: pago 'pendiente' (orden sigue 'pendiente')
    PG->>API: POST /pagos/webhook {transaccion_id, evento, firma_hmac}
    API->>API: verifica HMAC-SHA256 (401 si falla)
    API->>V: procesar_webhook()
    alt ya estaba aprobado/rechazado (aviso repetido)
        V-->>PG: 200 duplicado=true (sin cambios)
    else pendiente
        V->>V: pago → aprobado/rechazado + historial
        V->>V: Σ aprobados == total ? → MaquinaEstados pendiente→confirmada
        V-->>PG: 200
    end
```

---

## KAN-55 — Reembolsos

### Diagrama de clases
```mermaid
classDiagram
    class PagoOrden { +UUID id +metodo +Decimal monto +Decimal monto_reembolsado +estado }
    class Reembolso {
        +UUID id
        +UUID pago_id
        +Decimal monto
        +string motivo
        +estado: solicitado|procesando|completado|fallido
        +int intento
        +string error
        +dict comprobante (efectivo)
        +dict contabilidad
    }
    class ReembolsoService {
        +solicitar(pago_id|orden_id, monto, motivo)
        +reintentar(reembolso_id)
        +saldo_reembolsable(pago)
    }
    class PagosClient { +reembolsar_cobro() }
    class ContabilidadClient { +registrar_reembolso() }
    PagoOrden "1" --> "*" Reembolso
    ReembolsoService ..> PagosClient : simulado
    ReembolsoService ..> ContabilidadClient : simulado
```

### Secuencia del reembolso con reintento
```mermaid
sequenceDiagram
    actor A as Administrador
    participant API as POST /reembolsos
    participant R as ReembolsoService
    participant PG as PagosClient (simulado)
    participant CON as ContabilidadClient (simulado)
    A->>API: {orden_id | pago_id, monto, motivo}
    API->>R: solicitar()
    R->>R: monto ≤ saldo reembolsable? (si no → 422)
    R->>R: pago dividido: reparte por tramo y medio (último tramo primero)
    R->>R: Reembolso 'solicitado' → 'procesando'
    R->>PG: reembolsar_cobro(transaccion_id, monto, metodo)
    alt PG responde completado
        R->>R: 'completado' + pago.monto_reembolsado (+ 'reembolsado' si total) + comprobante de egreso si es efectivo
        R->>CON: registrar_reembolso()
        R->>R: audit_logs REEMBOLSO_COMPLETADO
    else PG falla
        R->>R: 'fallido' (+ audit_logs REEMBOLSO_FALLIDO)
        A->>API: POST /reembolsos/{id}/reintentar
        API->>R: reintentar() — solo si 'fallido' y el saldo alcanza
    end
```
