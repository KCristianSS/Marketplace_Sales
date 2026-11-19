# Empresas y descuentos B2B

En Administración → Cotizaciones B2B, **Registrar empresa** permite ingresar NIT,
razón social y correo comercial; el contacto y teléfono son opcionales. Al guardar,
la empresa queda seleccionada para cotizar. Este registro crea un perfil comercial,
sin crear una cuenta de acceso ni solicitar contraseña.

Si el NIT ya pertenece a una empresa, se reutiliza el perfil sin sobrescribir sus
datos. Un NIT registrado como cliente minorista requiere revisión de su clasificación.
La base de datos serializa las altas por NIT para evitar duplicados concurrentes.

**Configurar descuentos** permite activar o desactivar los descuentos y editar
las cantidades mínimas y porcentajes. Se aplica el porcentaje del mayor umbral
alcanzado por la suma de unidades de la cotización. Los umbrales deben ser únicos
y los porcentajes no pueden disminuir al aumentar la cantidad mínima.

Las reglas iniciales conservan el comportamiento anterior: 5 unidades = 5 %,
10 unidades = 10 % y 20 unidades = 15 %. Se guardan en PostgreSQL y el servidor
realiza el cálculo. Cada cotización almacena la versión y las reglas utilizadas;
modificar la configuración no cambia cotizaciones emitidas. Una versión obsoleta
devuelve 409 para revisar las nuevas reglas antes de volver a emitir o guardar.

Endpoints disponibles para administrador y gerente comercial:

- `POST /api/v1/clientes/corporativos`: registrar o recuperar una empresa por NIT.
- `GET /api/v1/cotizaciones/configuracion`: consultar reglas y versión.
- `PUT /api/v1/cotizaciones/configuracion`: guardar reglas con versión esperada.

Migración: `db/migrations/20261110061159_empresas_y_descuentos_b2b.sql`.
El alta de empresas y la actualización de descuentos generan registros de auditoría.
