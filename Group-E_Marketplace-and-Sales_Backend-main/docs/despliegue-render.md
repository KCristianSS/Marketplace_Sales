# Despliegue publico en Render

## Alcance

El Blueprint de la raiz despliega un frontend Vue, el API Gateway y dos
microservicios independientes: Catalogo y Clientes. Los microservicios y Redis
usan la red privada de Render; el navegador accede al gateway por HTTPS.
Supabase sigue siendo la base de datos externa.

No incluye POS, Carrito, Ordenes, Reportes ni los ERP. Sus pantallas y rutas no
estan operativas en este despliegue minimo. No usarlo para cobrar compras reales.
La existencia del Blueprint no significa que ya haya un despliegue publico.

## Requisitos

- Cuenta de Render con acceso a ambos repositorios de GitHub.
- Publicar los cambios de configuracion en la rama Alex de backend.
- Revisar el costo en Render antes de crear el Blueprint: tres servicios de
  computo 0.5c-512mb y Redis 256mb son recursos de pago. El sitio estatico usa CDN.
- Supabase configurado con tablas de catalogo y clientes, sus politicas RLS y
  usuarios reales. Las cuentas demo se deshabilitan en production.
- Nunca subir .env ni JSON de cuentas de servicio; tampoco cambiar el ejemplo
  de credenciales para incluir una clave real.

## Crear el despliegue

1. En Render, New > Blueprint, conectar el repositorio backend y elegir Alex.
   Render lee render.yaml y conecta tambien el repositorio frontend en Alex.
   Revisar nombres, region y planes antes de confirmar.
2. En maxiconecta-clientes, introducir SUPABASE_URL, SUPABASE_KEY (anon) y
   SUPABASE_SERVICE_ROLE_KEY en el formulario seguro de Render. No introducir
   la service-role key en el frontend.
3. Catalogo recibe esas tres variables por referencia a Clientes. Un valor
  ausente no debe aceptarse como evidencia de conexion real: los servicios
  tienen fallbacks de desarrollo.
4. Configurar CORS_ORIGINS del gateway con la URL HTTPS exacta del sitio estatico,
   sin barra final. Si Render aun no asigno la URL, completar tras la creacion y
   volver a desplegar el gateway.
5. Configurar VITE_API_GATEWAY_URL del frontend con la URL HTTPS del gateway,
   sin /api/v1. Volver a desplegar el frontend despues de cambiarla: Vite inserta
   esta variable durante el build, no en tiempo de ejecucion.
6. Esperar que Catalogo, Clientes y Gateway esten Live. Los host/port internos,
   Redis y el JWT_SECRET compartido se resuelven desde el Blueprint.

Los deploys automaticos estan desactivados: revisar los cambios antes de cada
Manual Deploy. Los nombres de servicio no garantizan un dominio onrender.com
exacto: usar las URLs que muestre Render.

## Verificacion y evidencia

Desde una maquina fuera de la red local:

- Abrir la URL HTTPS del frontend en ventana privada.
- Abrir /marketplace directamente y recargar: el rewrite debe servir index.html.
- GET <gateway>/health debe devolver 200 (solo verifica el gateway).
- GET <gateway>/api/v1/catalogo/productos debe devolver 200 con productos reales
  de Supabase. No confundir un catalogo simulado con datos persistidos.
- Iniciar sesion con un usuario de prueba real del servicio Clientes; comprobar
  en Network que la peticion va al gateway HTTPS, no a localhost.
- GET /api/v1/clientes/auth/me con el token emitido debe devolver ese perfil.
- Una preflight OPTIONS desde el origen del frontend debe llevar
  Access-Control-Allow-Origin con ese origen, no un comodin.
- En las consolas privadas de Catalogo y Clientes, comprobar GET /health.

Guardar URLs publicas, fecha, revision desplegada de ambos repos, capturas del
frontend y respuestas HTTP como evidencia de aceptacion. Sin estas pruebas
publicas la historia sigue pendiente de validacion en nube.

## Rollback y apagado

Usar Rollback to previous deploy en Render para recuperar la revision anterior.
Si cambia el dominio del gateway, actualizar VITE_API_GATEWAY_URL y reconstruir
el frontend. Suspender/eliminar los recursos desde Render para detener costos;
no eliminar la base Supabase ni compartir credenciales en capturas.