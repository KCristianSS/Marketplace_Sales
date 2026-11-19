"""
Pruebas automatizadas para KAN-421 (Subtareas KAN-423 y KAN-424):
Gestión de usuarios internos con RBAC, asignación de rol y sucursal,
generación de contraseñas temporales, revocación de sesión y auditoría.
"""
import sys
import os
import uuid

# Asegurar path de importación
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.services.clientes.app.main import app
from backend.shared.security import create_access_token

client = TestClient(app)

def test_admin_usuarios_internos_suite():
    print("=" * 65)
    print("INICIANDO SUITE DE PRUEBAS: KAN-421 USUARIOS INTERNOS Y RBAC")
    print("=" * 65)

    # Generar tokens de prueba
    token_admin = create_access_token({
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "admin@maxiconecta.bo",
        "role": "administrador",
        "nombre_completo": "Cesar Admin"
    })
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    token_cajero = create_access_token({
        "sub": "00000000-0000-0000-0000-000000000002",
        "email": "cajero@maxiconecta.bo",
        "role": "cajero",
        "nombre_completo": "Cajero Sucursal"
    })
    headers_cajero = {"Authorization": f"Bearer {token_cajero}"}

    # 1. Criterio 1: Solo un administrador puede acceder a los endpoints
    print("\n[TEST 1] Intento de acceso por parte de un Cajero (Debe fallar con 403)...")
    res_cajero_block = client.get("/api/v1/admin/usuarios", headers=headers_cajero)
    assert res_cajero_block.status_code == 403, f"Esperaba 403 pero obtuvo {res_cajero_block.status_code}"
    assert "administrador" in res_cajero_block.json()["detail"].lower()
    print("  -> OK: Rechazo 403 con mensaje de RBAC para rol no administrador.")

    # 2. Listado por parte del Administrador
    print("\n[TEST 2] Listado de colaboradores por parte del Administrador...")
    res_list = client.get("/api/v1/admin/usuarios", headers=headers_admin)
    assert res_list.status_code == 200, f"Error listando usuarios: {res_list.text}"
    usuarios = res_list.json()
    assert len(usuarios) >= 2, "Deben existir usuarios semilla iniciales"
    print(f"  -> OK: {len(usuarios)} usuarios internos listados exitosamente.")

    # 3. Alta de un nuevo usuario interno (Cajero) con contraseña temporal
    nuevo_email = f"nuevo.cajero.{uuid.uuid4().hex[:6]}@maxiconecta.bo"
    print(f"\n[TEST 3] Alta de nuevo cajero ({nuevo_email})...")
    payload_nuevo = {
        "nombre_completo": "Laura Méndez (Cajera Equipetrol)",
        "email": nuevo_email,
        "rol": "cajero",
        "sucursal_id": "SUC-03",
        "sucursal_nombre": "Sucursal Equipetrol - Santa Cruz",
        "debe_cambiar_password": True
    }
    res_create = client.post("/api/v1/admin/usuarios", json=payload_nuevo, headers=headers_admin)
    assert res_create.status_code == 201, f"Error creando usuario: {res_create.text}"
    data_nuevo = res_create.json()
    assert data_nuevo["email"] == nuevo_email
    assert data_nuevo["rol"] == "cajero"
    assert data_nuevo["sucursal_id"] == "SUC-03"
    assert data_nuevo["debe_cambiar_password"] is True
    assert data_nuevo["password_temporal"] is not None and len(data_nuevo["password_temporal"]) >= 10
    nuevo_id = data_nuevo["id"]
    print(f"  -> OK: Usuario creado con ID {nuevo_id} y password temporal generada.")

    # 4. Criterio 2: Dado un correo ya registrado, no se permite duplicarlo
    print("\n[TEST 4] Intento de registrar correo duplicado (Debe fallar con 409)...")
    res_dup = client.post("/api/v1/admin/usuarios", json=payload_nuevo, headers=headers_admin)
    assert res_dup.status_code == 409, f"Esperaba 409 pero obtuvo {res_dup.status_code}"
    print("  -> OK: Rechazo 409 Conflict ante correo duplicado.")

    # 5. Edición de datos y cambio de rol/sucursal
    print(f"\n[TEST 5] Edición de rol de Cajero a Gerente Comercial...")
    payload_update = {
        "nombre_completo": "Laura Méndez (Supervisora)",
        "rol": "gerente_comercial",
        "sucursal_id": None,
        "sucursal_nombre": "Supervisión Regional Oriente"
    }
    res_patch = client.patch(f"/api/v1/admin/usuarios/{nuevo_id}", json=payload_update, headers=headers_admin)
    assert res_patch.status_code == 200, f"Error actualizando usuario: {res_patch.text}"
    data_updated = res_patch.json()
    assert data_updated["rol"] == "gerente_comercial"
    assert data_updated["nombre_completo"] == "Laura Méndez (Supervisora)"
    print("  -> OK: Rol y sucursal modificados correctamente.")

    # 6. Criterio 4: Desactivar usuario interno y revocación inmediata de sesión
    print(f"\n[TEST 6] Desactivación de usuario y revocación de sesión...")
    res_del = client.delete(f"/api/v1/admin/usuarios/{nuevo_id}", headers=headers_admin)
    assert res_del.status_code == 200, f"Error desactivando usuario: {res_del.text}"
    data_desactivado = res_del.json()
    assert data_desactivado["activo"] is False, "El usuario debe quedar inactivo"
    assert data_desactivado["sesion_revocada"] is True, "La sesión debe quedar revocada"
    print("  -> OK: Usuario desactivado y sesión revocada exitosamente.")

    print("\n" + "=" * 65)
    print("TODAS LAS PRUEBAS DE KAN-421 (KAN-423, KAN-424) PASARON CON ÉXITO")
    print("=" * 65)

if __name__ == "__main__":
    test_admin_usuarios_internos_suite()
