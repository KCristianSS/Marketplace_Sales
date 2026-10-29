# Instrucciones para el archivo de credenciales de Google Cloud Pub/Sub
### Cátedra: UCB SIS-323 Sistemas Distribuidos — Grupo E

Para conectar el sistema con el tópico real de Google Cloud Pub/Sub (`projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e`):

1. Usa una clave de servicio vigente con el rol `roles/pubsub.publisher` en el proyecto.
2. Coloca el JSON con el nombre **`service-account.json`** en esta carpeta (`./credentials/service-account.json`). Docker la monta como solo lectura en los servicios POS y Órdenes.
3. No publiques ni confirmes el JSON al repositorio. Los archivos JSON de esta carpeta están ignorados por Git.

4. Si prefieres usar una variable de entorno fuera de Docker, define:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/ruta/a/tu/archivo.json"
   ```

5. **Si no colocas el archivo**: el sistema registrará el evento en modo `FALLBACK_OFFLINE`; no se habrá publicado en Google Cloud.

Si una clave privada fue compartida en un chat o repositorio, revócala en Google Cloud IAM y genera una nueva antes de usar la integración.

### Comandos para probar el envío por consola:
```bash
# Prueba de recepción docente:
python3 scripts/test_pubsub_cli.py --tipo docente

# Prueba de descuento de stock por compra:
python3 scripts/test_pubsub_cli.py --tipo compra

# Ejecutar todas las pruebas (docente, compra y reintegro):
python3 scripts/test_pubsub_cli.py --all

# También disponible en Node.js:
node scripts/test_pubsub_cli.js --all
```
