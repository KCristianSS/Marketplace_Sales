-- Migración KAN-421 / KAN-423: Tabla propia usuarios_internos y vinculación con roles y sucursales
-- Da soporte a la administración de roles y permisos (RF-49)

CREATE TABLE IF NOT EXISTS usuarios_internos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE, -- Vínculo opcional con auth.users de Supabase
    nombre_completo VARCHAR(200) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    rol VARCHAR(50) NOT NULL CHECK (rol IN ('cajero', 'gerente_comercial', 'administrador')),
    sucursal_id VARCHAR(100),
    sucursal_nombre VARCHAR(200),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    debe_cambiar_password BOOLEAN NOT NULL DEFAULT TRUE,
    password_temporal VARCHAR(255),
    sesion_revocada BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices de búsqueda y filtrado
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_email ON usuarios_internos(email);
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_rol ON usuarios_internos(rol);
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_sucursal ON usuarios_internos(sucursal_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_internos_activo ON usuarios_internos(activo);

-- Semilla inicial de usuarios internos clave
INSERT INTO usuarios_internos (id, user_id, nombre_completo, email, rol, sucursal_id, sucursal_nombre, activo, debe_cambiar_password)
VALUES 
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'Cesar Admin (Líder Grupo E)', 'admin@maxiconecta.bo', 'administrador', NULL, 'Acceso Corporativo Global', TRUE, FALSE),
    ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000002', 'Cajero Sucursal Central', 'cajero@maxiconecta.bo', 'cajero', 'SUC-01', 'Sucursal Central - La Paz', TRUE, FALSE),
    ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000003', 'Gerente Comercial ERP', 'gerente@maxiconecta.bo', 'gerente_comercial', NULL, 'Supervisión Regional', TRUE, FALSE)
ON CONFLICT (email) DO NOTHING;

ALTER TABLE public.usuarios_internos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.usuarios_internos FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.usuarios_internos TO service_role;
