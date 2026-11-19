"""
Script de prueba para publicar un mensaje al topico de Google Cloud Pub/Sub.
Credenciales: sistema-ventas-grupoe-3478d70b70b8.json
Equipo: Grupo E - MaxiConecta (Marketplace y Ventas)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from google.cloud import pubsub_v1
from google.oauth2 import service_account

# Forzar encoding UTF-8 en stdout para Windows
sys.stdout.reconfigure(encoding='utf-8')

# Configuracion
PROJECT_ID = "project-a96e5fe1-5ba6-4698-a85"
TOPIC_ID = "ucb-sis323"
CREDENTIALS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "project-a96e5fe1-5ba6-4698-a85-4d88ffe257a6.json"
)

def publish_message():
    """Publica un mensaje de prueba al topico Pub/Sub."""
    
    # Zona horaria Bolivia (UTC-4)
    tz_bolivia = timezone(timedelta(hours=-4))
    now = datetime.now(tz_bolivia)
    fecha_hora = now.strftime("%Y-%m-%d %H:%M:%S (UTC-4)")
    
    # Cargar credenciales de la cuenta de servicio
    credentials = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/pubsub"]
    )
    
    # Crear el cliente de Pub/Sub con las credenciales
    publisher = pubsub_v1.PublisherClient(credentials=credentials)
    topic_path = f"projects/{PROJECT_ID}/topics/{TOPIC_ID}"
    
    # Construir el mensaje
    message_data = {
        "equipo": "Grupo E - MaxiConecta (Marketplace y Ventas)",
        "proyecto": "Sistema de Ventas - MaxiConecta",
        "mensaje": "Prueba de publicacion Pub/Sub - Taller de Sistemas de Informacion UCB",
        "fecha_hora": fecha_hora,
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "integrante": "Cesar",
        "modulo": "Ventas y Marketplace"
    }
    
    data_bytes = json.dumps(message_data, ensure_ascii=False).encode("utf-8")
    
    print("=" * 55)
    print("  PUBLICACION DE MENSAJE - Google Cloud Pub/Sub")
    print("=" * 55)
    print(f"  Topico:        {topic_path}")
    print(f"  Credenciales:  sistema-ventas-grupoe-3478d70b70b8.json")
    print(f"  Service Acct:  pubsub-worker@sistema-ventas-grupoe")
    print(f"  Fecha/Hora:    {fecha_hora}")
    print(f"  Equipo:        Grupo E - MaxiConecta")
    print("=" * 55)
    print(f"\n  Enviando mensaje...\n")
    print(f"  Contenido del mensaje:")
    print(f"  {json.dumps(message_data, indent=2, ensure_ascii=False)}")
    print()
    
    try:
        # Publicar el mensaje
        future = publisher.publish(
            topic_path,
            data=data_bytes,
            equipo="Grupo_E",
            modulo="Ventas_Marketplace",
            origen="MaxiConecta"
        )
        
        # Esperar confirmacion
        message_id = future.result(timeout=30)
        
        print(f"  [OK] Mensaje publicado exitosamente!")
        print(f"  Message ID: {message_id}")
        print(f"  Fecha/Hora: {fecha_hora}")
        print("=" * 55)
        
        return message_id
        
    except Exception as e:
        print(f"  [ERROR] Error al publicar: {e}")
        print("=" * 55)
        raise


if __name__ == "__main__":
    publish_message()
