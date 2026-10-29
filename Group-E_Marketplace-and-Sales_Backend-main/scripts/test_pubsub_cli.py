#!/usr/bin/env python3
"""
Herramienta CLI de Consola para Pruebas de Sincronización con Google Cloud Pub/Sub
Asignatura: UCB SIS-323 Sistemas Distribuidos
Historia de Usuario: KAN-56 / US-40 (RF-40) - Sincronización con ERP de Inventarios
Tópico Cátedra: projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e

Uso:
    python3 scripts/test_pubsub_cli.py --tipo docente
    python3 scripts/test_pubsub_cli.py --tipo compra
    python3 scripts/test_pubsub_cli.py --tipo reintegro
    python3 scripts/test_pubsub_cli.py --all
"""

import sys
import os
import json
import argparse
import asyncio
from datetime import datetime

# Configuración de rutas
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "Group-E_Marketplace-and-Sales_Backend-main"))

try:
    from backend.shared.pubsub_client import pubsub_client, EVENTOS_PUBSUB_LOG
    from backend.shared.config import settings
except ImportError:
    try:
        from shared.pubsub_client import pubsub_client, EVENTOS_PUBSUB_LOG
        from shared.config import settings
    except ImportError:
        # Fallback local
        sys.path.insert(0, os.path.join(BASE_DIR, "backend_reference"))
        from shared.pubsub_client import pubsub_client, EVENTOS_PUBSUB_LOG
        from shared.config import settings

# Códigos ANSI para salida estética por consola
GREEN = "\033[92m"
BLUE = "\033[94m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"\n{CYAN}{BOLD}" + "=" * 76 + f"{RESET}")
    print(f"{CYAN}{BOLD}  MAXICONECTA — GRUPO E (MARKETPLACE & VENTAS) — UCB SIS-323{RESET}")
    print(f"{CYAN}  Módulo de Sincronización de Eventos con ERP Inventarios (Google Pub/Sub){RESET}")
    print(f"{CYAN}{BOLD}" + "=" * 76 + f"{RESET}\n")


def print_status():
    cred_path = pubsub_client._resolve_credentials_path()
    topic = pubsub_client.topic_name
    project = pubsub_client.project_id

    print(f"{BOLD}[CONFIGURACIÓN ACTUAL]:{RESET}")
    print(f"  • {BOLD}GCP Project ID:{RESET} {project}")
    print(f"  • {BOLD}Pub/Sub Tópico:{RESET} {topic}")
    if cred_path:
        print(f"  • {BOLD}Credenciales:{RESET}   {GREEN}Detectadas en: {cred_path}{RESET}")
        print(f"  • {BOLD}Modo de Operación:{RESET} {GREEN}ONLINE (Conexión Real a Google Cloud Pub/Sub){RESET}")
    else:
        print(f"  • {BOLD}Credenciales:{RESET}   {YELLOW}No detectadas (archivo service-account.json no encontrado){RESET}")
        print(f"  • {BOLD}Modo de Operación:{RESET} {YELLOW}SIMULACIÓN OFFLINE (Generación de eventos deterministas){RESET}")
    print("-" * 76)


async def ejecutar_prueba_docente(responsable: str, mensaje: str):
    print(f"\n{BLUE}{BOLD}[TEST: PRUEBA DE PUBLICACIÓN PARA CÁTEDRA DOCENTE]{RESET}")
    print(f"Enviando mensaje al tópico de la materia para confirmación de recepción...")

    resultado = await pubsub_client.publicar_mensaje_test(
        responsable=responsable,
        detalle=mensaje
    )

    _imprimir_resultado(resultado)


async def ejecutar_prueba_compra(orden_id: str):
    print(f"\n{BLUE}{BOLD}[TEST: EVENTO DE COMPRA — DESCUENTO DEFINITIVO DE STOCK (RIO-INV-03)]{RESET}")
    items = [
        {"sku": "FAR-PARACETAMOL-500", "cantidad": 3, "nombre": "Paracetamol 500mg - Caja 20 tabletas"},
        {"sku": "FAR-IBUPROFENO-400", "cantidad": 2, "nombre": "Ibuprofeno 400mg - Caja 10 cápsulas"},
        {"sku": "FAR-ALCOHOL-70", "cantidad": 1, "nombre": "Alcohol Medicinal 70% 500ml"}
    ]
    print(f"Simulando venta completada en Marketplace (Orden: {orden_id}) con {len(items)} productos...")

    resultado = await pubsub_client.publicar_descuento_stock(
        orden_id=orden_id,
        items=items,
        origen="marketplace",
        sucursal_id="SUC-LP-CENTRAL"
    )

    _imprimir_resultado(resultado)


async def ejecutar_prueba_reintegro(orden_id: str):
    print(f"\n{BLUE}{BOLD}[TEST: EVENTO DE DEVOLUCIÓN — REINTEGRO DE STOCK (RIO-INV-04)]{RESET}")
    items = [
        {"sku": "FAR-PARACETAMOL-500", "cantidad": 1, "nombre": "Paracetamol 500mg - Caja 20 tabletas"}
    ]
    print(f"Simulando anulación/devolución de cliente para Orden {orden_id}...")

    resultado = await pubsub_client.publicar_reintegro_stock(
        orden_id=orden_id,
        items=items,
        motivo="devolucion_por_cliente_empaque_danado",
        origen="marketplace",
        sucursal_id="SUC-LP-CENTRAL"
    )

    _imprimir_resultado(resultado)


def _imprimir_resultado(res: dict):
    status = res.get("status")
    color = GREEN if status == "PUBLICADO" else YELLOW

    print(f"\n{color}{BOLD}>> RESULTADO:{RESET}")
    print(f"  • Estado:       {color}{status}{RESET}")
    print(f"  • Message ID:   {res.get('message_id')}")
    print(f"  • Event ID:     {res.get('event_id')}")
    print(f"  • Tópico:       {res.get('topic')}")
    print(f"  • Tipo Evento:  {res.get('event_type')}")
    print(f"  • Timestamp:    {res.get('timestamp')}")
    print(f"\n{BOLD}Carga Útil (Payload CloudEvents 1.0):{RESET}")
    print(json.dumps(res.get("payload", {}), indent=2, ensure_ascii=False))
    print(f"{CYAN}" + "-" * 76 + f"{RESET}")


async def main():
    parser = argparse.ArgumentParser(
        description="MaxiConecta - CLI de Pruebas Google Cloud Pub/Sub (SIS-323)"
    )
    parser.add_argument(
        "--tipo",
        choices=["docente", "compra", "reintegro"],
        help="Tipo de evento a publicar"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ejecuta todas las pruebas en secuencia"
    )
    parser.add_argument(
        "--responsable",
        default="Kevin Sancalli",
        help="Nombre del alumno responsable (por defecto: Kevin Sancalli)"
    )
    parser.add_argument(
        "--mensaje",
        default="Sincronización simulada enviando eventos de venta y stock al tópico del docente (Grupo E)",
        help="Detalle del mensaje a transmitir"
    )
    parser.add_argument(
        "--orden",
        default=f"ORD-PUB-{datetime.now().strftime('%m%d-%H%M%S')}",
        help="ID de la orden para el test de compra"
    )

    args = parser.parse_args()

    print_banner()
    print_status()

    if args.all:
        await ejecutar_prueba_docente(args.responsable, args.mensaje)
        await ejecutar_prueba_compra(args.orden)
        await ejecutar_prueba_reintegro(args.orden)
        print(f"\n{GREEN}{BOLD}✓ Todas las pruebas se completaron correctamente.{RESET}\n")
    elif args.tipo == "docente":
        await ejecutar_prueba_docente(args.responsable, args.mensaje)
    elif args.tipo == "compra":
        await ejecutar_prueba_compra(args.orden)
    elif args.tipo == "reintegro":
        await ejecutar_prueba_reintegro(args.orden)
    else:
        # Por defecto si no se especifican flags, ejecutar prueba docente y compra
        print(f"{YELLOW}No se especificó --tipo ni --all. Ejecutando prueba de cátedra y venta por defecto:{RESET}")
        await ejecutar_prueba_docente(args.responsable, args.mensaje)
        await ejecutar_prueba_compra(args.orden)


if __name__ == "__main__":
    asyncio.run(main())
