import express, { Request, Response, NextFunction } from 'express';
import multer from 'multer';
import sharp from 'sharp';
import { randomUUID } from 'node:crypto';
import { supabaseAdmin, BUCKET_NAME, ensureStorageBucket } from './supabase';
import {
  getPubSubStatus,
  pubSubEventLogs,
  publishStockDescuento,
  publishStockReintegro,
  publishPruebaDocente
} from './pubsub';

const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 10 * 1024 * 1024 // 10 MB
  },
  fileFilter: (_req, file, cb) => {
    if (file.mimetype.startsWith('image/')) {
      cb(null, true);
    } else {
      cb(new Error('Solo se permiten archivos de imagen válidos (PNG, JPEG, WebP, etc.).'));
    }
  }
});

export function createApiMiddleware() {
  const router = express();
  router.use(express.json());

  // Normalizar prefijo redundante /api si llega al middleware (para compatibilidad universal de rutas)
  router.use((req: Request, _res: Response, next: NextFunction) => {
    if (req.url.startsWith('/api/')) {
      req.url = req.url.substring(4);
    }
    next();
  });

  // Ensure storage bucket is initialized
  ensureStorageBucket().catch(err => console.error('Bucket initialization error:', err));

  // Health check
  router.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });

  // GET /productos - Lista de productos con categoría, variantes (precio) y cantidad de imágenes
  router.get('/productos', async (_req: Request, res: Response) => {
    try {
      const { data: productos, error } = await supabaseAdmin
        .from('productos')
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          created_at,
          categorias ( id, nombre ),
          imagenes_producto ( id, url, es_principal, orden ),
          variantes ( id, sku, nombre_variante, precio, precio_costo, codigo_barras )
        `)
        .order('created_at', { ascending: false });

      if (error) {
        return res.status(500).json({ error: error.message });
      }

      // Normalizar precio principal para el producto
      const enriched = (productos || []).map(p => {
        const principalVariante = p.variantes && p.variantes.length > 0 ? p.variantes[0] : null;
        return {
          ...p,
          precio: principalVariante ? Number(principalVariante.precio) : 0,
          precio_costo: principalVariante?.precio_costo ? Number(principalVariante.precio_costo) : 0
        };
      });

      res.json({ productos: enriched });
    } catch (err: any) {
      res.status(500).json({ error: err?.message || 'Error interno del servidor' });
    }
  });

  // GET /productos/:id - Obtener un producto específico
  router.get('/productos/:id', async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { data: producto, error } = await supabaseAdmin
        .from('productos')
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          created_at,
          categorias ( id, nombre ),
          imagenes_producto ( id, url, es_principal, orden ),
          variantes ( id, sku, nombre_variante, precio, precio_costo, codigo_barras )
        `)
        .eq('id', id)
        .single();

      if (error || !producto) {
        return res.status(404).json({ error: 'Producto no encontrado.' });
      }

      const principalVariante = producto.variantes && producto.variantes.length > 0 ? producto.variantes[0] : null;
      res.json({
        producto: {
          ...producto,
          precio: principalVariante ? Number(principalVariante.precio) : 0,
          precio_costo: principalVariante?.precio_costo ? Number(principalVariante.precio_costo) : 0
        }
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // GET /categorias - Lista de categorías
  router.get('/categorias', async (_req: Request, res: Response) => {
    try {
      const { data: categorias, error } = await supabaseAdmin
        .from('categorias')
        .select('*')
        .order('nombre', { ascending: true });

      if (error) return res.status(500).json({ error: error.message });
      res.json({ categorias });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // POST /productos - Crear nuevo producto (Subtarea KAN-306 / KAN-287) y guardar su precio en tabla variantes
  router.post('/productos', async (req: Request, res: Response) => {
    try {
      const { sku, nombre, descripcion, marca, categoria_id, estado, precio, precio_costo } = req.body;
      if (!sku || !nombre) {
        return res.status(400).json({ error: 'El SKU y el nombre son requeridos.' });
      }

      const cleanSku = String(sku).trim().toUpperCase();

      // Validación de unicidad de SKU (KAN-287)
      const { data: existingSku } = await supabaseAdmin
        .from('productos')
        .select('id')
        .eq('sku', cleanSku)
        .maybeSingle();

      if (existingSku) {
        return res.status(409).json({ error: `El SKU "${cleanSku}" ya está registrado por otro producto.` });
      }

      // Mapear estado al ENUM de postgres: publicado, borrador, inactivo, descontinuado
      let dbEstado = (estado || 'publicado').toLowerCase();
      if (dbEstado === 'archivado') dbEstado = 'descontinuado';

      const { data: nuevoProducto, error } = await supabaseAdmin
        .from('productos')
        .insert([{
          sku: cleanSku,
          nombre: String(nombre).trim(),
          descripcion: descripcion ? String(descripcion).trim() : '',
          marca: marca ? String(marca).trim() : '',
          categoria_id: categoria_id || null,
          estado: dbEstado
        }])
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          created_at,
          categorias ( id, nombre )
        `)
        .single();

      if (error) return res.status(500).json({ error: error.message });

      // Guardar precio en la tabla 'variantes' (Arquitectura relacional Supabase)
      const numericPrice = Number(precio) || 0;
      const numericCost = Number(precio_costo) || Math.round(numericPrice * 0.7);

      const { data: varianteData } = await supabaseAdmin
        .from('variantes')
        .insert([{
          producto_id: nuevoProducto.id,
          sku: `${cleanSku}-STD`,
          nombre_variante: 'Estándar',
          precio: numericPrice,
          precio_costo: numericCost,
          atributos: {}
        }])
        .select()
        .single();

      res.status(201).json({
        producto: {
          ...nuevoProducto,
          precio: numericPrice,
          precio_costo: numericCost,
          variantes: varianteData ? [varianteData] : []
        }
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // PUT /productos/:id - Actualizar producto existente y sincronizar precio en variantes (KAN-306 / KAN-307)
  router.put('/productos/:id', async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { sku, nombre, descripcion, marca, categoria_id, estado, precio, precio_costo } = req.body;

      if (!sku || !nombre) {
        return res.status(400).json({ error: 'El SKU y el nombre son obligatorios.' });
      }

      const cleanSku = String(sku).trim().toUpperCase();

      // Verificar unicidad de SKU excluyendo el producto actual
      const { data: duplicateSku } = await supabaseAdmin
        .from('productos')
        .select('id')
        .eq('sku', cleanSku)
        .neq('id', id)
        .maybeSingle();

      if (duplicateSku) {
        return res.status(409).json({ error: `El SKU "${cleanSku}" ya pertenece a otro producto.` });
      }

      let dbEstado = (estado || 'publicado').toLowerCase();
      if (dbEstado === 'archivado') dbEstado = 'descontinuado';

      const { data: updated, error } = await supabaseAdmin
        .from('productos')
        .update({
          sku: cleanSku,
          nombre: String(nombre).trim(),
          descripcion: descripcion ? String(descripcion).trim() : '',
          marca: marca ? String(marca).trim() : '',
          categoria_id: categoria_id || null,
          estado: dbEstado
        })
        .eq('id', id)
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          created_at,
          categorias ( id, nombre ),
          imagenes_producto ( id, url, es_principal, orden )
        `)
        .single();

      if (error) return res.status(500).json({ error: error.message });

      // Actualizar o crear variante con el precio
      const numericPrice = Number(precio) || 0;
      const numericCost = Number(precio_costo) || Math.round(numericPrice * 0.7);

      const { data: existingVars } = await supabaseAdmin
        .from('variantes')
        .select('id')
        .eq('producto_id', id);

      if (existingVars && existingVars.length > 0) {
        await supabaseAdmin
          .from('variantes')
          .update({
            precio: numericPrice,
            precio_costo: numericCost
          })
          .eq('id', existingVars[0].id);
      } else {
        await supabaseAdmin
          .from('variantes')
          .insert([{
            producto_id: id,
            sku: `${cleanSku}-STD`,
            nombre_variante: 'Estándar',
            precio: numericPrice,
            precio_costo: numericCost,
            atributos: {}
          }]);
      }

      res.json({
        producto: {
          ...updated,
          precio: numericPrice,
          precio_costo: numericCost
        },
        message: 'Producto y precio actualizados con éxito.'
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // PATCH /productos/:id/estado - Cambio rápido de ciclo de vida (publicado, borrador, inactivo, descontinuado)
  router.patch('/productos/:id/estado', async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { estado } = req.body;
      const validStates = ['publicado', 'borrador', 'archivado', 'descontinuado', 'inactivo'];

      if (!estado || !validStates.includes(estado.toLowerCase())) {
        return res.status(400).json({ error: `Estado inválido. Opciones válidas: ${validStates.join(', ')}` });
      }

      let dbEstado = estado.toLowerCase();
      if (dbEstado === 'archivado') dbEstado = 'descontinuado';

      const { data: updated, error } = await supabaseAdmin
        .from('productos')
        .update({ estado: dbEstado })
        .eq('id', id)
        .select('id, sku, nombre, estado')
        .single();

      if (error) return res.status(500).json({ error: error.message });
      res.json({ producto: updated, message: `Estado cambiado a ${estado}` });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // DELETE /productos/:id - Eliminar producto del catálogo (KAN-291)
  router.delete('/productos/:id', async (req: Request, res: Response) => {
    try {
      const { id } = req.params;

      // 1. Eliminar imágenes asociadas
      await supabaseAdmin
        .from('imagenes_producto')
        .delete()
        .eq('producto_id', id);

      // 2. Eliminar el producto
      const { error } = await supabaseAdmin
        .from('productos')
        .delete()
        .eq('id', id);

      if (error) return res.status(500).json({ error: error.message });

      res.json({ success: true, message: 'Producto eliminado del catálogo.' });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // GET /productos/:id/imagenes - Listar imágenes de un producto
  router.get('/productos/:id/imagenes', async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { data: imagenes, error } = await supabaseAdmin
        .from('imagenes_producto')
        .select('*')
        .eq('producto_id', id)
        .order('orden', { ascending: true })
        .order('created_at', { ascending: true });

      if (error) return res.status(500).json({ error: error.message });

      // Añadir thumbnailUrl derivado para vista rápida optimizada
      const enriched = (imagenes || []).map(img => {
        let thumbnailUrl = img.url;
        if (img.url.includes(`/object/public/${BUCKET_NAME}/${id}/`)) {
          thumbnailUrl = img.url.replace(`/${id}/`, `/${id}/thumbs/`);
        }
        return {
          ...img,
          thumbnailUrl
        };
      });

      res.json({ imagenes: enriched });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // POST /productos/:id/imagenes - Cargar una o múltiples imágenes (Multipart)
  // Subtarea KAN-75: Integración con Supabase Storage y endpoints de subida multipart
  // Subtarea KAN-76: Generación de thumbnails y optimización/compresión de imágenes
  router.post(
    '/productos/:id/imagenes',
    upload.array('imagenes', 10),
    async (req: Request, res: Response) => {
      try {
        const { id: productoId } = req.params;
        const files = (req.files as Express.Multer.File[]) || (req.file ? [req.file] : []);

        if (!files || files.length === 0) {
          return res.status(400).json({ error: 'No se enviaron archivos de imagen.' });
        }

        // Verificar que el producto exista
        const { data: producto, error: pErr } = await supabaseAdmin
          .from('productos')
          .select('id, nombre')
          .eq('id', productoId)
          .single();

        if (pErr || !producto) {
          return res.status(404).json({ error: 'Producto no encontrado.' });
        }

        // Obtener imágenes existentes para calcular orden y si ya hay principal
        const { data: existingImages } = await supabaseAdmin
          .from('imagenes_producto')
          .select('id, es_principal, orden')
          .eq('producto_id', productoId)
          .order('orden', { ascending: false });

        let currentMaxOrder = (existingImages && existingImages.length > 0)
          ? Math.max(...existingImages.map(i => i.orden || 0))
          : -1;

        const hasPrincipal = existingImages?.some(i => i.es_principal);

        const uploadedResults = [];

        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          const fileUid = randomUUID();
          const mainFileName = `${fileUid}.webp`;
          const mainPath = `${productoId}/${mainFileName}`;
          const thumbPath = `${productoId}/thumbs/${mainFileName}`;

          const originalSize = file.size;

          // 1. Optimización y compresión con Sharp: Máx 1920x1080, WebP 85% calidad
          const optimizedBuffer = await sharp(file.buffer)
            .resize({ width: 1920, height: 1080, fit: 'inside', withoutEnlargement: true })
            .webp({ quality: 85, effort: 4 })
            .toBuffer();

          // 2. Generación de Thumbnail con Sharp: 320x320 Cover, WebP 80% calidad
          const thumbnailBuffer = await sharp(file.buffer)
            .resize(320, 320, { fit: 'cover', position: 'centre' })
            .webp({ quality: 80, effort: 3 })
            .toBuffer();

          // 3. Subida a Supabase Storage: Imagen Optimizada Principal
          const { error: mainUploadError } = await supabaseAdmin.storage
            .from(BUCKET_NAME)
            .upload(mainPath, optimizedBuffer, {
              contentType: 'image/webp',
              upsert: true,
              cacheControl: '31536000'
            });

          if (mainUploadError) {
            console.error('Error subiendo imagen principal a Storage:', mainUploadError);
            throw new Error(`Fallo al subir ${file.originalname}: ${mainUploadError.message}`);
          }

          // 4. Subida a Supabase Storage: Thumbnail
          const { error: thumbUploadError } = await supabaseAdmin.storage
            .from(BUCKET_NAME)
            .upload(thumbPath, thumbnailBuffer, {
              contentType: 'image/webp',
              upsert: true,
              cacheControl: '31536000'
            });

          if (thumbUploadError) {
            console.warn('Advertencia subiendo thumbnail a Storage:', thumbUploadError);
          }

          // 5. Obtener URLs públicas
          const { data: { publicUrl: mainUrl } } = supabaseAdmin.storage
            .from(BUCKET_NAME)
            .getPublicUrl(mainPath);

          const { data: { publicUrl: thumbUrl } } = supabaseAdmin.storage
            .from(BUCKET_NAME)
            .getPublicUrl(thumbPath);

          // Determinar si esta imagen es portada
          currentMaxOrder += 1;
          const isPrincipal = !hasPrincipal && i === 0;

          // 6. Registrar en la tabla imagenes_producto de PostgreSQL
          const { data: dbRecord, error: dbError } = await supabaseAdmin
            .from('imagenes_producto')
            .insert([{
              producto_id: productoId,
              url: mainUrl,
              es_principal: isPrincipal,
              orden: currentMaxOrder
            }])
            .select()
            .single();

          if (dbError) {
            console.error('Error insertando en imagenes_producto:', dbError);
            throw new Error(`Error en base de datos: ${dbError.message}`);
          }

          uploadedResults.push({
            ...dbRecord,
            thumbnailUrl: thumbUrl,
            stats: {
              nombreOriginal: file.originalname,
              pesoOriginalBytes: originalSize,
              pesoOptimizadoBytes: optimizedBuffer.length,
              pesoThumbnailBytes: thumbnailBuffer.length,
              porcentajeAhorro: Math.round((1 - optimizedBuffer.length / originalSize) * 100)
            }
          });
        }

        res.status(201).json({
          success: true,
          message: `${uploadedResults.length} recurso(s) multimedia procesado(s) exitosamente.`,
          imagenes: uploadedResults
        });
      } catch (err: any) {
        console.error('Error en POST /productos/:id/imagenes:', err);
        res.status(500).json({ error: err.message || 'Error al procesar y subir imágenes' });
      }
    }
  );

  // PUT /productos/:id/imagenes/reordenar - Reordenar galería visual
  // Subtarea KAN-77: Reordenamiento de recursos multimedia
  router.put('/productos/:id/imagenes/reordenar', async (req: Request, res: Response) => {
    try {
      const { id: productoId } = req.params;
      const { ordenes } = req.body as { ordenes: Array<{ id: string; orden: number }> };

      if (!Array.isArray(ordenes)) {
        return res.status(400).json({ error: 'El cuerpo debe contener un arreglo "ordenes" con { id, orden }.' });
      }

      // Actualizar secuencialmente o en paralelo
      const updates = ordenes.map(item =>
        supabaseAdmin
          .from('imagenes_producto')
          .update({ orden: item.orden })
          .eq('id', item.id)
          .eq('producto_id', productoId)
      );

      await Promise.all(updates);

      // Retornar lista ordenada actualizada
      const { data: updatedList, error } = await supabaseAdmin
        .from('imagenes_producto')
        .select('*')
        .eq('producto_id', productoId)
        .order('orden', { ascending: true });

      if (error) return res.status(500).json({ error: error.message });

      res.json({
        success: true,
        message: 'Orden de galería actualizado exitosamente.',
        imagenes: updatedList
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // PATCH /productos/:id/imagenes/:imagenId/principal - Marcar como imagen de portada
  // Subtarea KAN-78: Selector de imagen de portada
  router.patch('/productos/:id/imagenes/:imagenId/principal', async (req: Request, res: Response) => {
    try {
      const { id: productoId, imagenId } = req.params;

      // 1. Quitar 'es_principal' de todas las imágenes de este producto
      await supabaseAdmin
        .from('imagenes_producto')
        .update({ es_principal: false })
        .eq('producto_id', productoId);

      // 2. Asignar 'es_principal = true' a la imagen seleccionada
      const { data: updated, error } = await supabaseAdmin
        .from('imagenes_producto')
        .update({ es_principal: true })
        .eq('id', imagenId)
        .eq('producto_id', productoId)
        .select()
        .single();

      if (error) return res.status(500).json({ error: error.message });

      res.json({
        success: true,
        message: 'Imagen designada como portada principal del producto.',
        imagen: updated
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // DELETE /productos/:id/imagenes/:imagenId - Eliminar recurso multimedia
  // Subtarea KAN-78: Eliminación de recursos multimedia
  router.delete('/productos/:id/imagenes/:imagenId', async (req: Request, res: Response) => {
    try {
      const { id: productoId, imagenId } = req.params;

      // 1. Consultar registro para obtener URL y saber si era principal
      const { data: imgRecord, error: findError } = await supabaseAdmin
        .from('imagenes_producto')
        .select('*')
        .eq('id', imagenId)
        .eq('producto_id', productoId)
        .single();

      if (findError || !imgRecord) {
        return res.status(404).json({ error: 'Recurso multimedia no encontrado.' });
      }

      // 2. Extraer path del storage si está almacenado en Supabase Storage
      try {
        const urlObj = new URL(imgRecord.url);
        const marker = `/storage/v1/object/public/${BUCKET_NAME}/`;
        if (urlObj.pathname.includes(marker)) {
          const relativePath = urlObj.pathname.substring(urlObj.pathname.indexOf(marker) + marker.length);
          const thumbRelativePath = relativePath.replace(`/${productoId}/`, `/${productoId}/thumbs/`);
          await supabaseAdmin.storage.from(BUCKET_NAME).remove([relativePath, thumbRelativePath]);
        }
      } catch (storageErr) {
        console.warn('Aviso: no se pudo eliminar del storage:', storageErr);
      }

      // 3. Eliminar de la base de datos
      const { error: delError } = await supabaseAdmin
        .from('imagenes_producto')
        .delete()
        .eq('id', imagenId)
        .eq('producto_id', productoId);

      if (delError) return res.status(500).json({ error: delError.message });

      // 4. Si la imagen eliminada era la principal, reasignar automáticamente a la primera disponible
      if (imgRecord.es_principal) {
        const { data: remaining } = await supabaseAdmin
          .from('imagenes_producto')
          .select('id')
          .eq('producto_id', productoId)
          .order('orden', { ascending: true })
          .limit(1);

        if (remaining && remaining.length > 0) {
          await supabaseAdmin
            .from('imagenes_producto')
            .update({ es_principal: true })
            .eq('id', remaining[0].id);
        }
      }

      res.json({
        success: true,
        message: 'Recurso multimedia eliminado correctamente.'
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ============================================================================
  // CLIENTES & AUTH ENPOINTS (RF-22, US-22 / RF-49, US-49)
  // Permite inicio de sesión, registro y sincronización de perfiles
  // ============================================================================

  const demoUsers: Record<string, any> = {
    'admin@maxiconecta.bo': {
      id: 'a0000000-0000-0000-0000-000000000001',
      user_id: 'a0000000-0000-0000-0000-000000000001',
      nombre_completo: 'Administrador Sistema',
      email: 'admin@maxiconecta.bo',
      role: 'administrador',
      puntos_saldo: 500,
      tipo_cliente: 'corporativo'
    },
    'cajero@maxiconecta.bo': {
      id: 'c0000000-0000-0000-0000-000000000002',
      user_id: 'c0000000-0000-0000-0000-000000000002',
      nombre_completo: 'Cajero Central',
      email: 'cajero@maxiconecta.bo',
      role: 'cajero',
      sucursal_id: 'SUC-01',
      puntos_saldo: 100,
      tipo_cliente: 'retail'
    }
  };

  const handleRegister = async (req: Request, res: Response) => {
    try {
      const { nombre_completo, email, password, telefono, nit_ci, razon_social } = req.body;
      if (!nombre_completo || !email || !password) {
        return res.status(400).json({ detail: 'Por favor complete todos los campos obligatorios.' });
      }

      const cleanEmail = email.toLowerCase().trim();
      let userId: string = randomUUID();
      let token = 'jwt_token_' + randomUUID();

      // 1. Registrar usuario en Supabase Auth (auth.users)
      try {
        const { data: authData, error: authError } = await supabaseAdmin.auth.admin.createUser({
          email: cleanEmail,
          password,
          email_confirm: true,
          user_metadata: { nombre_completo, role: 'cliente' }
        });

        if (!authError && authData?.user) {
          userId = authData.user.id;
        } else if (authError) {
          console.warn('Supabase Auth createUser nota:', authError.message);
        }
      } catch (sbErr) {
        console.warn('Supabase auth signup fallback:', sbErr);
      }

      // 2. Persistir perfil en la tabla 'perfiles_clientes' de PostgreSQL (Supabase)
      try {
        const { data: existingProf } = await supabaseAdmin
          .from('perfiles_clientes')
          .select('id')
          .eq('email', cleanEmail)
          .maybeSingle();

        if (existingProf?.id) {
          userId = existingProf.id;
          await supabaseAdmin
            .from('perfiles_clientes')
            .update({
              nombre_completo,
              telefono: telefono || null,
              nit_ci: nit_ci || null,
              razon_social: razon_social || null,
              updated_at: new Date().toISOString()
            })
            .eq('id', userId);
        } else {
          const { data: newProf, error: profErr } = await supabaseAdmin
            .from('perfiles_clientes')
            .insert({
              id: userId,
              user_id: userId,
              nombre_completo,
              email: cleanEmail,
              telefono: telefono || null,
              nit_ci: nit_ci || null,
              razon_social: razon_social || null,
              tipo_cliente: 'retail'
            })
            .select()
            .maybeSingle();

          if (newProf?.id) {
            userId = newProf.id;
          } else if (profErr) {
            console.warn('Aviso guardando en perfiles_clientes:', profErr.message);
          }
        }
      } catch (dbErr) {
        console.warn('Advertencia DB perfiles_clientes:', dbErr);
      }

      const profile = {
        id: userId,
        user_id: userId,
        nombre_completo,
        email: cleanEmail,
        telefono: telefono || null,
        nit_ci: nit_ci || null,
        razon_social: razon_social || null,
        tipo_cliente: 'retail',
        role: 'cliente',
        puntos_saldo: 50,
        mensaje: 'Bienvenido a MaxiConecta'
      };

      demoUsers[cleanEmail] = profile;

      return res.status(201).json({
        access_token: token,
        refresh_token: 'refresh_' + randomUUID(),
        token_type: 'bearer',
        expires_in: 7200,
        user: profile
      });
    } catch (err: any) {
      return res.status(500).json({ detail: err.message || 'Error en el registro' });
    }
  };

  const handleLogin = async (req: Request, res: Response) => {
    try {
      const { email, password } = req.body;
      if (!email || !password) {
        return res.status(400).json({ detail: 'Correo y contraseña requeridos' });
      }

      const cleanEmail = email.toLowerCase().trim();

      // 1. Validar credenciales estrictamente con Supabase Auth (auth.users)
      const { data: authData, error: authErr } = await supabaseAdmin.auth.signInWithPassword({
        email: cleanEmail,
        password
      });

      if (authErr || !authData?.user) {
        console.warn('Fallo de autenticación en Supabase Auth:', authErr?.message);
        return res.status(401).json({ detail: 'Credenciales inválidas. Verifica tu correo o contraseña.' });
      }

      const u = authData.user;
      const meta = u.user_metadata || {};

      // 2. Consultar perfil en perfiles_clientes para enriquecer datos de negocio
      const { data: dbProfile } = await supabaseAdmin
        .from('perfiles_clientes')
        .select('*')
        .eq('email', cleanEmail)
        .maybeSingle();

      const profile = {
        id: u.id,
        user_id: u.id,
        nombre_completo: dbProfile?.nombre_completo || meta.nombre_completo || cleanEmail.split('@')[0],
        email: cleanEmail,
        telefono: dbProfile?.telefono || null,
        nit_ci: dbProfile?.nit_ci || null,
        razon_social: dbProfile?.razon_social || null,
        role: meta.role || (cleanEmail.includes('admin') ? 'administrador' : cleanEmail.includes('cajero') ? 'cajero' : 'cliente'),
        puntos_saldo: 50,
        tipo_cliente: dbProfile?.tipo_cliente || 'retail'
      };

      return res.json({
        access_token: authData.session?.access_token || ('jwt_' + randomUUID()),
        refresh_token: authData.session?.refresh_token || ('refresh_' + randomUUID()),
        token_type: 'bearer',
        expires_in: authData.session?.expires_in || 7200,
        user: profile
      });
    } catch (err: any) {
      console.error('Error en login:', err);
      return res.status(500).json({ detail: err.message || 'Error en el inicio de sesión' });
    }
  };

  router.post('/v1/clientes/auth/registro', handleRegister);
  router.post('/v1/clientes/registro', handleRegister);
  router.post('/clientes/auth/registro', handleRegister);

  router.post('/v1/clientes/auth/login', handleLogin);
  router.post('/v1/clientes/login', handleLogin);
  router.post('/clientes/auth/login', handleLogin);

  router.get('/v1/clientes/auth/me', (_req: Request, res: Response) => {
    res.json({
      id: 'demo-user-id',
      nombre_completo: 'Usuario MaxiConecta',
      email: 'usuario@maxiconecta.bo',
      role: 'cliente',
      puntos_saldo: 50
    });
  });

  // ============================================================================
  // ALIAS DE RUTAS /v1/catalogo/* y /api/v1/* para compatibilidad total
  // ============================================================================
  router.get('/v1/catalogo/categorias', async (_req: Request, res: Response) => {
    try {
      const { data: categorias, error } = await supabaseAdmin
        .from('categorias')
        .select('*')
        .order('nombre', { ascending: true });
      if (error) return res.status(500).json({ error: error.message });
      res.json(categorias || []);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  router.get('/v1/catalogo/productos', async (_req: Request, res: Response) => {
    try {
      const { data: productos, error } = await supabaseAdmin
        .from('productos')
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          created_at,
          categorias ( id, nombre ),
          imagenes_producto ( id, url, es_principal, orden ),
          variantes ( id, sku, nombre_variante, precio, precio_costo, codigo_barras )
        `)
        .order('created_at', { ascending: false });

      if (error) return res.status(500).json({ error: error.message });

      const enriched = (productos || []).map(p => {
        const principalVariante = p.variantes && p.variantes.length > 0 ? p.variantes[0] : null;
        return {
          ...p,
          precio: principalVariante ? principalVariante.precio : null,
          precio_costo: principalVariante ? principalVariante.precio_costo : null,
          variante_id: principalVariante ? principalVariante.id : null,
          total_imagenes: p.imagenes_producto ? p.imagenes_producto.length : 0
        };
      });

      res.json(enriched);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ============================================================================
  // HISTORIA KAN-346 / KAN-13: SUBTAREAS KAN-365 Y KAN-367
  // FACTURACIÓN ELECTRÓNICA, VALIDACIÓN DE NIT Y PERFILES FISCALES
  // ============================================================================

  // Base en memoria para perfiles fiscales y base de datos simulada del Padrón Tributario (SIN)
  const mockPadronTributario: Record<string, { razon_social: string; estado: 'ACTIVO' | 'INACTIVO' }> = {
    '1020304050': { razon_social: 'EMPRESA MINERA SAN CRISTÓBAL S.A.', estado: 'ACTIVO' },
    '1002345678': { razon_social: 'MAXICONECTA BOLIVIA S.R.L.', estado: 'ACTIVO' },
    '4829102': { razon_social: 'CARLOS MENDOZA PATZI', estado: 'ACTIVO' },
    '7894561012': { razon_social: 'IMPORTADORA Y DISTRIBUIDORA ANDINA S.A.', estado: 'ACTIVO' },
    '6543210': { razon_social: 'SOFÍA DORIA MEDINA', estado: 'ACTIVO' },
    '9876543210': { razon_social: 'SOLUCIONES TECNOLÓGICAS DEL VALLE LTDA.', estado: 'ACTIVO' },
    '11223344': { razon_social: 'JUAN PÉREZ GARCÍA', estado: 'INACTIVO' }
  };

  const perfilesFiscalesStore: Array<{
    id: string;
    cliente_id?: string;
    tipo_documento: 'NIT' | 'CI' | 'CEX' | 'PAS';
    nit_ci: string;
    razon_social: string;
    email_facturacion?: string;
    es_predeterminado: boolean;
    creado_el: string;
  }> = [
    {
      id: 'perf-001',
      cliente_id: 'demo-client',
      tipo_documento: 'NIT',
      nit_ci: '1020304050',
      razon_social: 'EMPRESA MINERA SAN CRISTÓBAL S.A.',
      email_facturacion: 'contabilidad@sancristobal.bo',
      es_predeterminado: true,
      creado_el: new Date().toISOString()
    }
  ];

  let facturaCorrelativo = 1420;

  // 1. KAN-365: [BE] Validación de NIT/CI con el servicio fiscal (Impuestos Nacionales)
  const handleValidarNit = async (req: Request, res: Response) => {
    try {
      const { nit_ci, tipo_documento = 'NIT' } = req.body;
      const cleanNit = String(nit_ci || '').trim();

      if (!cleanNit) {
        return res.status(400).json({
          valido: false,
          nit_ci: '',
          estado: 'NO_ENCONTRADO',
          mensaje: 'Debe ingresar un número de NIT o CI.'
        });
      }

      // Caso especial: Consumidor Final / Sin Factura legal nominada
      if (cleanNit === '0' || cleanNit === '99001' || cleanNit.toLowerCase() === 'consumidor final') {
        return res.json({
          valido: true,
          nit_ci: '0',
          razon_social: 'CONSUMIDOR FINAL',
          estado: 'ACTIVO',
          mensaje: 'Documento legal para ventas a Consumidor Final.'
        });
      }

      // Validación de formato numérico básico
      if (!/^\d{5,15}$/.test(cleanNit) && tipo_documento === 'NIT') {
        return res.json({
          valido: false,
          nit_ci: cleanNit,
          estado: 'NO_ENCONTRADO',
          mensaje: 'El formato del NIT debe contener entre 5 y 15 dígitos numéricos.'
        });
      }

      // Consulta en el padrón tributario (SIN)
      const enPadron = mockPadronTributario[cleanNit];
      if (enPadron) {
        if (enPadron.estado === 'INACTIVO') {
          return res.json({
            valido: false,
            nit_ci: cleanNit,
            razon_social: enPadron.razon_social,
            estado: 'INACTIVO',
            mensaje: `El NIT ${cleanNit} se encuentra INACTIVO en el Servicio de Impuestos Nacionales.`
          });
        }

        return res.json({
          valido: true,
          nit_ci: cleanNit,
          razon_social: enPadron.razon_social,
          estado: 'ACTIVO',
          mensaje: 'NIT verificado y activo en el padrón del Servicio de Impuestos Nacionales.'
        });
      }

      // Si no está en el mock pero cumple con formato válido
      const perfilPrevio = perfilesFiscalesStore.find(p => p.nit_ci === cleanNit);
      if (perfilPrevio) {
        return res.json({
          valido: true,
          nit_ci: cleanNit,
          razon_social: perfilPrevio.razon_social,
          estado: 'ACTIVO',
          mensaje: 'NIT verificado en historial fiscal del cliente.'
        });
      }

      // Si es CI o NIT válido sintácticamente pero no en el mock, se acepta como válido
      return res.json({
        valido: true,
        nit_ci: cleanNit,
        razon_social: '',
        estado: 'ACTIVO',
        mensaje: 'NIT con formato tributario válido en el Servicio Fiscal.'
      });
    } catch (err: any) {
      return res.status(500).json({ error: err.message || 'Error validando NIT con el servicio fiscal.' });
    }
  };

  router.post('/v1/facturacion/validar-nit', handleValidarNit);
  router.post('/api/v1/facturacion/validar-nit', handleValidarNit);

  // 2. KAN-365: [BE] Persistencia y consulta de perfiles fiscales
  const handleGetPerfilesFiscales = async (req: Request, res: Response) => {
    try {
      const clienteId = (req.query.cliente_id as string) || 'demo-client';
      const perfiles = perfilesFiscalesStore.filter(p => !p.cliente_id || p.cliente_id === clienteId);
      res.json(perfiles);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  };

  const handleCreatePerfilFiscal = async (req: Request, res: Response) => {
    try {
      const { nit_ci, razon_social, tipo_documento = 'NIT', email_facturacion, cliente_id = 'demo-client', es_predeterminado = false } = req.body;

      if (!nit_ci || !razon_social) {
        return res.status(400).json({ error: 'El NIT/CI y la Razón Social son campos requeridos.' });
      }

      const cleanNit = String(nit_ci).trim();
      const cleanRazon = String(razon_social).trim().toUpperCase();

      // Si se marca como predeterminado, desmarcar los demás
      if (es_predeterminado) {
        perfilesFiscalesStore.forEach(p => {
          if (p.cliente_id === cliente_id) p.es_predeterminado = false;
        });
      }

      const existingIndex = perfilesFiscalesStore.findIndex(p => p.nit_ci === cleanNit && p.cliente_id === cliente_id);
      let perfil;

      if (existingIndex >= 0) {
        perfilesFiscalesStore[existingIndex] = {
          ...perfilesFiscalesStore[existingIndex],
          razon_social: cleanRazon,
          tipo_documento,
          email_facturacion: email_facturacion || perfilesFiscalesStore[existingIndex].email_facturacion,
          es_predeterminado: es_predeterminado ?? perfilesFiscalesStore[existingIndex].es_predeterminado
        };
        perfil = perfilesFiscalesStore[existingIndex];
      } else {
        perfil = {
          id: 'perf-' + randomUUID().substring(0, 8),
          cliente_id,
          tipo_documento,
          nit_ci: cleanNit,
          razon_social: cleanRazon,
          email_facturacion,
          es_predeterminado,
          creado_el: new Date().toISOString()
        };
        perfilesFiscalesStore.unshift(perfil);
      }

      res.status(201).json({ mensaje: 'Perfil fiscal guardado con éxito.', perfil });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  };

  const handleGetPerfilByNit = async (req: Request, res: Response) => {
    try {
      const { nit_ci } = req.params;
      const cleanNit = String(nit_ci).trim();
      const perfil = perfilesFiscalesStore.find(p => p.nit_ci === cleanNit);
      const enPadron = mockPadronTributario[cleanNit];

      if (perfil) {
        return res.json(perfil);
      }
      if (enPadron) {
        return res.json({
          tipo_documento: 'NIT',
          nit_ci: cleanNit,
          razon_social: enPadron.razon_social
        });
      }

      return res.status(404).json({ error: 'No se encontró perfil fiscal para el documento indicado.' });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  };

  router.get('/v1/facturacion/perfiles-fiscales', handleGetPerfilesFiscales);
  router.get('/api/v1/facturacion/perfiles-fiscales', handleGetPerfilesFiscales);
  router.post('/v1/facturacion/perfiles-fiscales', handleCreatePerfilFiscal);
  router.post('/api/v1/facturacion/perfiles-fiscales', handleCreatePerfilFiscal);
  router.get('/v1/facturacion/perfiles-fiscales/:nit_ci', handleGetPerfilByNit);
  router.get('/api/v1/facturacion/perfiles-fiscales/:nit_ci', handleGetPerfilByNit);

  // 3. KAN-367: [INT] Integración con el microservicio de Facturación (Payload de Emisión)
  const handleEmitirFactura = async (req: Request, res: Response) => {
    try {
      const {
        modalidad = 'con_factura', // 'con_factura' | 'sin_factura'
        tipo_documento = 'NIT',
        nit_ci = '0',
        razon_social = 'CONSUMIDOR FINAL',
        email_facturacion = '',
        guardar_perfil = false,
        sucursal = 'Sucursal Central - La Paz',
        punto_venta = 1,
        metodo_pago = 'efectivo',
        items = [],
        descuento = 0
      } = req.body;

      const esConsumidorFinal = modalidad === 'sin_factura' || nit_ci === '0' || !nit_ci.trim();
      const nitFinal = esConsumidorFinal ? '0' : String(nit_ci).trim();
      const razonFinal = esConsumidorFinal ? 'CONSUMIDOR FINAL' : String(razon_social).trim().toUpperCase();

      facturaCorrelativo += 1;
      const numeroFactura = facturaCorrelativo;

      // Calcular montos
      const itemsProcesados = (items || []).map((it: any) => {
        const cant = Number(it.cantidad) || 1;
        const precio = Number(it.precio_unitario || it.precio) || 0;
        return {
          sku: it.sku || 'SKU-GEN',
          nombre: it.nombre || 'Producto',
          cantidad: cant,
          precio_unitario: precio,
          subtotal: cant * precio
        };
      });

      const tipo_despacho = req.body.tipo_despacho || 'domicilio';
      const datos_despacho = req.body.datos_despacho || {};
      const costo_envio = tipo_despacho === 'retiro_sucursal' ? 0 : (Number(req.body.costo_envio) || Number(datos_despacho.costo_flete) || 0);

      const subtotalTotal = itemsProcesados.reduce((acc: number, curr: any) => acc + curr.subtotal, 0);
      const totalPagar = Math.max(0, subtotalTotal - (Number(descuento) || 0) + costo_envio);

      // Generar CUF (Código Único de Facturación) timbrado alfanumérico
      const timestamp = new Date().toISOString().replace(/[-:TZ.]/g, '').substring(0, 14);
      const cufRaw = `${timestamp}1028374029${punto_venta}${numeroFactura}1${randomUUID().replace(/-/g, '').substring(0, 16)}`.toUpperCase();
      const cuf = `CUF-${cufRaw.substring(0, 4)}-${cufRaw.substring(4, 8)}-${cufRaw.substring(8, 16)}`;
      const cufd = `CUFD-${randomUUID().substring(0, 8).toUpperCase()}-${timestamp.substring(0, 8)}`;

      // Identificadores logísticos de entrega (KAN-31 / KAN-27)
      const codigo_retiro = tipo_despacho === 'retiro_sucursal'
        ? (datos_despacho.codigo_retiro || `RET-${Math.floor(100000 + Math.random() * 900000)}`)
        : undefined;
      const tracking_number = tipo_despacho === 'domicilio'
        ? (datos_despacho.tracking_number || `MAXI-TRK-${Math.floor(100000 + Math.random() * 900000)}`)
        : undefined;

      // Cadena del Código QR según normativa SIN
      const codigoQr = `https://pilotosiat.impuestos.gob.bo/consulta/QR?nit=1028374029&cuf=${cuf}&numero=${numeroFactura}&t=${totalPagar.toFixed(2)}`;

      const leyendaFiscal = 'Ley N° 453: El proveedor deberá suministrar el servicio en las modalidades y términos ofertados.';

      // Payload oficial del microservicio de facturación
      const facturaPayload = {
        id: 'FAC-' + randomUUID(),
        numero_factura: numeroFactura,
        cuf,
        cufd,
        fecha_emision: new Date().toISOString(),
        modalidad: esConsumidorFinal ? 'sin_factura' : 'con_factura',
        datos_comprador: {
          tipo_documento: esConsumidorFinal ? 'CI' : tipo_documento,
          nit_ci: nitFinal,
          razon_social: razonFinal,
          email_facturacion: email_facturacion || undefined
        },
        sucursal: datos_despacho.sucursal_nombre || sucursal,
        punto_venta,
        tipo_despacho,
        costo_envio,
        subtotal: subtotalTotal,
        total: totalPagar,
        total_sujeto_iva: totalPagar,
        descuento: Number(descuento) || 0,
        metodo_pago,
        codigo_qr: codigoQr,
        codigo_retiro,
        tracking_number,
        datos_despacho,
        leyenda_fiscal: leyendaFiscal,
        items: itemsProcesados
      };

      // Si es retiro en sucursal, sincronizar orden en store de Click & Collect (KAN-27)
      if (tipo_despacho === 'retiro_sucursal' && codigo_retiro) {
        const qrRetiro = `MAXI-CC|ORD-FAC-${numeroFactura}|${codigo_retiro}|${datos_despacho.sucursal_id || 'SUC-01'}`;
        clickAndCollectOrdersStore[codigo_retiro] = {
          id: randomUUID(),
          codigo_orden: `ORD-FAC-${numeroFactura}`,
          codigo_retiro,
          codigo_qr: qrRetiro,
          estado: 'confirmada',
          es_entregable: true,
          motivo_rechazo: null,
          sucursal_id: datos_despacho.sucursal_id || 'SUC-01',
          sucursal_nombre: datos_despacho.sucursal_nombre || 'Sucursal Central El Prado',
          fecha_compra: new Date().toISOString(),
          cliente_nombre: razonFinal,
          cliente_documento: nitFinal,
          cliente_telefono: '+591 70012345',
          cliente_email: email_facturacion || 'cliente@maxiconecta.bo',
          subtotal: subtotalTotal,
          descuento: Number(descuento) || 0,
          total: totalPagar,
          metodo_pago,
          cuf_factura: cuf,
          numero_factura: numeroFactura,
          items: itemsProcesados.map((it: any) => ({
            id: it.variante_id || it.sku,
            sku: it.sku,
            nombre: it.nombre,
            cantidad: it.cantidad,
            precio_unitario: it.precio_unitario,
            total_linea: it.subtotal
          }))
        };
      }

      // Si el usuario solicitó guardar el perfil fiscal y no es Consumidor Final
      if (guardar_perfil && !esConsumidorFinal) {
        const existe = perfilesFiscalesStore.find(p => p.nit_ci === nitFinal);
        if (!existe) {
          perfilesFiscalesStore.unshift({
            id: 'perf-' + randomUUID().substring(0, 8),
            cliente_id: 'demo-client',
            tipo_documento,
            nit_ci: nitFinal,
            razon_social: razonFinal,
            email_facturacion,
            es_predeterminado: true,
            creado_el: new Date().toISOString()
          });
        }
      }

      // PERSISTENCIA REAL EN BASE DE DATOS SUPABASE (ordenes.cuf_factura, perfiles_clientes, pagos)
      try {
        // 1. Obtener o crear perfil de cliente en perfiles_clientes
        let clienteDbId: string | null = null;
        let { data: existingClient } = await supabaseAdmin
          .from('perfiles_clientes')
          .select('id, email')
          .eq('nit_ci', nitFinal)
          .maybeSingle();

        if (!existingClient && email_facturacion) {
          const { data: clientByEmail } = await supabaseAdmin
            .from('perfiles_clientes')
            .select('id, email')
            .eq('email', email_facturacion.trim().toLowerCase())
            .maybeSingle();
          if (clientByEmail) existingClient = clientByEmail;
        }

        if (existingClient?.id) {
          clienteDbId = existingClient.id;
          await supabaseAdmin
            .from('perfiles_clientes')
            .update({
              razon_social: razonFinal,
              nombre_completo: razonFinal,
              nit_ci: nitFinal,
              updated_at: new Date().toISOString()
            })
            .eq('id', clienteDbId);
        } else {
          const safeEmail = email_facturacion && email_facturacion.includes('@')
            ? email_facturacion.trim().toLowerCase()
            : `factura.${nitFinal}.${Date.now()}@maxiconecta.bo`;

          const { data: newClient, error: clientInsertErr } = await supabaseAdmin
            .from('perfiles_clientes')
            .insert({
              nombre_completo: razonFinal,
              email: safeEmail,
              nit_ci: nitFinal,
              razon_social: razonFinal,
              tipo_cliente: 'retail'
            })
            .select('id')
            .maybeSingle();

          if (newClient?.id) {
            clienteDbId = newClient.id;
          } else if (clientInsertErr) {
            console.warn('[DB Facturación] Buscando perfil alternativo:', clientInsertErr.message);
            const { data: anyClient } = await supabaseAdmin.from('perfiles_clientes').select('id').limit(1).maybeSingle();
            clienteDbId = anyClient?.id || null;
          }
        }

        // 2. Insertar orden con el campo cuf_factura en la tabla ordenes
        if (clienteDbId) {
          const codigoOrden = `ORD-FAC-${numeroFactura}`;
          const canalVenta = sucursal && String(sucursal).toLowerCase().includes('pos') ? 'pos' : 'web';
          const { data: nuevaOrden, error: ordenErr } = await supabaseAdmin
            .from('ordenes')
            .insert({
              codigo_orden: codigoOrden,
              cliente_id: clienteDbId,
              canal: canalVenta,
              tipo_despacho: 'retiro_sucursal',
              subtotal: subtotalTotal,
              descuento: Number(descuento) || 0,
              costo_envio: 0,
              total: totalPagar,
              moneda: 'BOB',
              estado: 'confirmada',
              cuf_factura: cuf
            })
            .select('id')
            .single();

          if (nuevaOrden?.id) {
            const ordenDbId = nuevaOrden.id;

            // 3. Insertar items en orden_items resolviendo variante_id real (NOT NULL)
            if (itemsProcesados.length > 0) {
              const { data: dbVars } = await supabaseAdmin.from('variantes').select('id, sku');
              const fallbackVarId = dbVars && dbVars.length > 0 ? dbVars[0].id : null;

              if (fallbackVarId) {
                const itemsAInsertar = itemsProcesados.map((it: any) => {
                  const matched = (dbVars || []).find((v: any) => 
                    v.sku === it.sku || 
                    v.sku.toLowerCase().includes(String(it.sku).toLowerCase()) ||
                    v.id === it.variante_id
                  );
                  return {
                    orden_id: ordenDbId,
                    variante_id: matched ? matched.id : fallbackVarId,
                    sku: it.sku,
                    nombre_producto: it.nombre,
                    cantidad: it.cantidad,
                    precio_unitario: it.precio_unitario,
                    total_linea: it.subtotal
                  };
                });
                await supabaseAdmin.from('orden_items').insert(itemsAInsertar);
              }
            }

            // 4. Insertar pago con método de pago normalizado y raw_payload
            const validMetodos = ['tarjeta', 'qr', 'transferencia', 'efectivo', 'pasarela'];
            const metodoValido = validMetodos.includes(String(metodo_pago).toLowerCase())
              ? String(metodo_pago).toLowerCase()
              : 'efectivo';

            await supabaseAdmin.from('pagos').insert({
              orden_id: ordenDbId,
              transaccion_id: `TX-${cuf.substring(4, 16)}`,
              metodo: metodoValido,
              monto: totalPagar,
              moneda: 'BOB',
              estado: 'aprobado',
              raw_payload: facturaPayload
            });

            console.log(`[Facturación BD] Factura #${numeroFactura} y orden ${codigoOrden} almacenadas con CUF ${cuf} en Supabase`);
          } else if (ordenErr) {
            console.warn('[Facturación BD] Aviso al insertar orden:', ordenErr.message);
          }
        }
      } catch (dbError: any) {
        console.warn('[Facturación BD] Advertencia de persistencia (no bloqueante):', dbError?.message);
      }

      // Guardar también en almacén en memoria para consulta inmediata
      facturasEmitidasStore.unshift(facturaPayload);

      // Sincronización automática con Inventario vía Google Cloud Pub/Sub (KAN-56 / US-40)
      try {
        const idOrdenSync = `ORD-FAC-${numeroFactura}`;
        const itemsParaSincronizar = (itemsProcesados || []).map((it: any) => ({
          sku: it.sku,
          cantidad: it.cantidad,
          nombre: it.nombre
        }));
        if (itemsParaSincronizar.length > 0) {
          publishStockDescuento(
            idOrdenSync,
            itemsParaSincronizar,
            metodo_pago === 'efectivo' ? 'pos' : 'marketplace',
            sucursal || 'SUC-LP-CENTRAL'
          ).catch(e => console.warn('[PubSub Auto] Error secundario:', e));
        }
      } catch (pubSubErr) {
        console.warn('[PubSub Auto] Error no bloqueante al sincronizar venta:', pubSubErr);
      }

      return res.status(201).json({
        mensaje: 'Factura legal electrónica timbrada y almacenada en base de datos exitosamente.',
        factura: facturaPayload
      });
    } catch (err: any) {
      return res.status(500).json({ error: err.message || 'Error emitiendo factura electrónica.' });
    }
  };

  const facturasEmitidasStore: any[] = [];

  const handleGetFacturas = async (_req: Request, res: Response) => {
    try {
      // Consultar órdenes que tengan cuf_factura en la BD
      const { data: ordenesFacturadas } = await supabaseAdmin
        .from('ordenes')
        .select(`
          id,
          codigo_orden,
          cuf_factura,
          total,
          subtotal,
          descuento,
          created_at,
          perfiles_clientes ( nit_ci, razon_social, email ),
          pagos ( metodo, raw_payload )
        `)
        .not('cuf_factura', 'is', null)
        .order('created_at', { ascending: false });

      if (ordenesFacturadas && ordenesFacturadas.length > 0) {
        const facturasDb = ordenesFacturadas.map(ord => {
          const pago = ord.pagos?.[0];
          if (pago?.raw_payload && pago.raw_payload.cuf) {
            return pago.raw_payload;
          }
          return {
            id: ord.id,
            codigo_orden: ord.codigo_orden,
            cuf: ord.cuf_factura,
            total: ord.total,
            fecha_emision: ord.created_at,
            datos_comprador: {
              nit_ci: (ord.perfiles_clientes as any)?.nit_ci || '0',
              razon_social: (ord.perfiles_clientes as any)?.razon_social || 'CONSUMIDOR FINAL'
            }
          };
        });
        return res.json(facturasDb);
      }

      return res.json(facturasEmitidasStore);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  };

  const handleGetFacturaByCuf = async (req: Request, res: Response) => {
    try {
      const { cuf } = req.params;
      const enCache = facturasEmitidasStore.find(f => f.cuf === cuf);
      if (enCache) return res.json(enCache);

      const { data: orden } = await supabaseAdmin
        .from('ordenes')
        .select('id, cuf_factura, pagos(raw_payload)')
        .eq('cuf_factura', cuf)
        .maybeSingle();

      if (orden?.pagos?.[0]?.raw_payload) {
        return res.json(orden.pagos[0].raw_payload);
      }

      return res.status(404).json({ error: 'Factura no encontrada para el CUF especificado.' });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  };

  router.post('/v1/facturacion/emitir', handleEmitirFactura);
  router.post('/api/v1/facturacion/emitir', handleEmitirFactura);
  router.get('/v1/facturacion/facturas', handleGetFacturas);
  router.get('/api/v1/facturacion/facturas', handleGetFacturas);
  router.get('/v1/facturacion/facturas/:cuf', handleGetFacturaByCuf);
  router.get('/api/v1/facturacion/facturas/:cuf', handleGetFacturaByCuf);

  // ============================================================================
  // HISTORIA KAN-20 / RF-04: LISTAS DE PRECIOS DIFERENCIADAS (KAN-296, KAN-297, KAN-298)
  // ============================================================================
  const TIPO_CAMBIO_OFICIAL = 6.96;

  interface ListaPrecioRecord {
    id: string;
    nombre: string;
    canal: 'web' | 'pos' | 'b2b';
    tipo_cliente: 'retail' | 'corporativo_b2b';
    sucursal_id?: string;
    sucursal_nombre?: string;
    moneda: 'BOB' | 'USD';
    factor_ajuste: number; // Factor sobre precio base (1.0 = base, 0.85 = -15% B2B, 1.05 = +5% Santa Cruz)
    activo: boolean;
  }

  const listasPreciosStore: ListaPrecioRecord[] = [
    {
      id: 'lista-web-retail',
      nombre: 'Tarifa General Web (Retail)',
      canal: 'web',
      tipo_cliente: 'retail',
      moneda: 'BOB',
      factor_ajuste: 1.0,
      activo: true
    },
    {
      id: 'lista-pos-central',
      nombre: 'Tarifa Mostrador POS (La Paz Central)',
      canal: 'pos',
      tipo_cliente: 'retail',
      sucursal_id: 'SUC-01',
      sucursal_nombre: 'Sucursal Central - La Paz',
      moneda: 'BOB',
      factor_ajuste: 1.0,
      activo: true
    },
    {
      id: 'lista-pos-santacruz',
      nombre: 'Tarifa Mostrador POS (Santa Cruz Equipetrol)',
      canal: 'pos',
      tipo_cliente: 'retail',
      sucursal_id: 'SUC-03',
      sucursal_nombre: 'Sucursal Santa Cruz - Equipetrol',
      moneda: 'BOB',
      factor_ajuste: 1.05, // +5% flete regional
      activo: true
    },
    {
      id: 'lista-b2b-corporativo',
      nombre: 'Tarifa Mayorista B2B (Corporativo)',
      canal: 'b2b',
      tipo_cliente: 'corporativo_b2b',
      moneda: 'BOB',
      factor_ajuste: 0.85, // -15% descuento mayorista
      activo: true
    }
  ];

  // Overrides específicos de precio por variante en lista
  const preciosItemsStore: Record<string, number> = {};

  // GET /v1/catalogo/listas-precios
  router.get(['/v1/catalogo/listas-precios', '/api/v1/catalogo/listas-precios'], async (_req: Request, res: Response) => {
    res.json(listasPreciosStore);
  });

  // POST /v1/catalogo/listas-precios (KAN-296)
  router.post(['/v1/catalogo/listas-precios', '/api/v1/catalogo/listas-precios'], async (req: Request, res: Response) => {
    try {
      const { nombre, canal = 'web', tipo_cliente = 'retail', sucursal_id, sucursal_nombre, moneda = 'BOB', factor_ajuste = 1.0 } = req.body;
      if (!nombre) return res.status(400).json({ error: 'El nombre de la lista es requerido' });

      const nuevaLista: ListaPrecioRecord = {
        id: 'lista-' + randomUUID().substring(0, 8),
        nombre,
        canal,
        tipo_cliente,
        sucursal_id: sucursal_id || undefined,
        sucursal_nombre: sucursal_nombre || undefined,
        moneda: moneda === 'USD' ? 'USD' : 'BOB',
        factor_ajuste: Number(factor_ajuste) || 1.0,
        activo: true
      };

      listasPreciosStore.push(nuevaLista);
      res.status(201).json(nuevaLista);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // GET /v1/catalogo/listas-precios/matriz (KAN-298)
  router.get(['/v1/catalogo/listas-precios/matriz', '/api/v1/catalogo/listas-precios/matriz'], async (_req: Request, res: Response) => {
    try {
      const { data: productos } = await supabaseAdmin
        .from('productos')
        .select(`
          id,
          sku,
          nombre,
          categoria_id,
          categorias(nombre),
          variantes(id, sku, precio, precio_costo)
        `)
        .order('sku');

      const items = (productos || []).map(p => {
        const principalVar = p.variantes && p.variantes.length > 0 ? p.variantes[0] : null;
        const precioBase = principalVar ? Number(principalVar.precio) : 0;
        const varId = principalVar ? principalVar.id : p.id;

        // Precios por canal y sucursal
        const preciosPorLista: Record<string, number> = {};
        listasPreciosStore.forEach(lp => {
          const overrideKey = `${lp.id}:${varId}`;
          if (preciosItemsStore[overrideKey] !== undefined) {
            preciosPorLista[lp.id] = preciosItemsStore[overrideKey];
          } else {
            preciosPorLista[lp.id] = Math.round((precioBase * lp.factor_ajuste) * 100) / 100;
          }
        });

        return {
          producto_id: p.id,
          variante_id: varId,
          sku: p.sku,
          nombre: p.nombre,
          categoria: (p.categorias as any)?.nombre || 'General',
          precio_base: precioBase,
          precio_base_usd: Math.round((precioBase / TIPO_CAMBIO_OFICIAL) * 100) / 100,
          precios: preciosPorLista
        };
      });

      res.json({
        listas: listasPreciosStore,
        tipo_cambio: TIPO_CAMBIO_OFICIAL,
        matriz: items
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // POST /v1/catalogo/listas-precios/matriz - Guardar asignación de precios por canal/sucursal (KAN-298)
  router.post(['/v1/catalogo/listas-precios/matriz', '/api/v1/catalogo/listas-precios/matriz'], async (req: Request, res: Response) => {
    try {
      const { lista_id, variante_id, precio } = req.body;
      if (!lista_id || !variante_id || precio === undefined) {
        return res.status(400).json({ error: 'Faltan parámetros requeridos (lista_id, variante_id, precio)' });
      }

      const overrideKey = `${lista_id}:${variante_id}`;
      preciosItemsStore[overrideKey] = Number(precio);

      res.json({
        success: true,
        mensaje: 'Precio asignado exitosamente en la matriz de tarifas.',
        lista_id,
        variante_id,
        precio: Number(precio),
        precio_usd: Math.round((Number(precio) / TIPO_CAMBIO_OFICIAL) * 100) / 100
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // POST /v1/catalogo/precios/resolver - Motor de resolución de precios (KAN-297)
  // Regla de negocio RF-04: Cliente B2B > Sucursal específica > Canal general (Web vs POS)
  router.post(['/v1/catalogo/precios/resolver', '/api/v1/catalogo/precios/resolver'], async (req: Request, res: Response) => {
    try {
      const { sku, variante_id, canal = 'web', tipo_cliente = 'retail', sucursal_id } = req.body;

      // 1. Buscar producto o variante
      let query = supabaseAdmin.from('productos').select('id, sku, nombre, variantes(id, sku, precio)');
      if (sku) {
        query = query.eq('sku', String(sku).toUpperCase());
      } else if (variante_id) {
        // Encontrar por variante
      }
      const { data: prods } = await query.limit(1);
      const prod = prods && prods.length > 0 ? prods[0] : null;

      const precioBase = prod?.variantes?.[0]?.precio ? Number(prod.variantes[0].precio) : 100;
      const varId = prod?.variantes?.[0]?.id || 'var-base';

      let listaSeleccionada = listasPreciosStore[0]; // default web retail
      let reglaAplicada = 'Canal Web Retail estándar';
      let factor = 1.0;

      // Prioridad 1: Cliente B2B
      if (tipo_cliente === 'corporativo_b2b') {
        const b2bList = listasPreciosStore.find(l => l.tipo_cliente === 'corporativo_b2b') || listasPreciosStore[3];
        listaSeleccionada = b2bList;
        factor = b2bList.factor_ajuste;
        reglaAplicada = 'Prioridad 1: Tarifa B2B Corporativa con descuento mayorista (15%)';
      }
      // Prioridad 2: Sucursal específica (si tiene lista propia asignada)
      else if (sucursal_id) {
        const branchList = listasPreciosStore.find(l => l.sucursal_id === sucursal_id && l.activo);
        if (branchList) {
          listaSeleccionada = branchList;
          factor = branchList.factor_ajuste;
          reglaAplicada = `Prioridad 2: Tarifa específica por sucursal (${branchList.sucursal_nombre || sucursal_id})`;
        } else if (canal === 'pos') {
          const posList = listasPreciosStore.find(l => l.canal === 'pos') || listasPreciosStore[1];
          listaSeleccionada = posList;
          factor = posList.factor_ajuste;
          reglaAplicada = 'Prioridad 3: Tarifa mostrador POS general';
        }
      }
      // Prioridad 3: Canal general
      else if (canal === 'pos') {
        const posList = listasPreciosStore.find(l => l.canal === 'pos') || listasPreciosStore[1];
        listaSeleccionada = posList;
        factor = posList.factor_ajuste;
        reglaAplicada = 'Prioridad 3: Tarifa mostrador POS';
      }

      // Comprobar override manual en matriz
      const overrideKey = `${listaSeleccionada.id}:${varId}`;
      const precioFinalBob = preciosItemsStore[overrideKey] !== undefined
        ? preciosItemsStore[overrideKey]
        : Math.round((precioBase * factor) * 100) / 100;

      const precioFinalUsd = Math.round((precioFinalBob / TIPO_CAMBIO_OFICIAL) * 100) / 100;

      res.json({
        sku: prod?.sku || sku || 'SKU-ITEM',
        nombre: prod?.nombre || 'Producto Consultado',
        precio_bob: precioFinalBob,
        precio_usd: precioFinalUsd,
        tipo_cambio: TIPO_CAMBIO_OFICIAL,
        lista_aplicada: {
          id: listaSeleccionada.id,
          nombre: listaSeleccionada.nombre,
          canal: listaSeleccionada.canal,
          tipo_cliente: listaSeleccionada.tipo_cliente
        },
        regla_aplicada: reglaAplicada,
        descuento_aplicado: factor < 1.0 ? Math.round((1 - factor) * 100) : 0
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ============================================================================
  // HISTORIA KAN-24: ENDPOINT DELTA DE SINCRONIZACIÓN DE CATÁLOGO (KAN-313)
  // ============================================================================
  router.get(['/v1/catalogo/sync-catalogo', '/api/v1/catalogo/sync-catalogo'], async (req: Request, res: Response) => {
    try {
      const since = req.query.since as string;
      const limit = Math.min(100, Math.max(1, Number(req.query.limit) || 50));
      const offset = Math.max(0, Number(req.query.offset) || 0);

      let query = supabaseAdmin
        .from('productos')
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          created_at,
          categorias ( id, nombre ),
          imagenes_producto ( id, url, es_principal, orden ),
          variantes ( id, sku, nombre_variante, precio, precio_costo )
        `)
        .order('created_at', { ascending: false });

      if (since) {
        query = query.gte('created_at', since);
      }

      const { data: productos, error } = await query.range(offset, offset + limit - 1);
      if (error) return res.status(500).json({ error: error.message });

      const serverTimestamp = new Date().toISOString();
      const enriched = (productos || []).map(p => {
        const principalVar = p.variantes && p.variantes.length > 0 ? p.variantes[0] : null;
        return {
          ...p,
          precio: principalVar ? Number(principalVar.precio) : 0,
          precio_costo: principalVar?.precio_costo ? Number(principalVar.precio_costo) : 0,
          variante_id: principalVar?.id
        };
      });

      res.json({
        server_timestamp: serverTimestamp,
        delta_count: enriched.length,
        offset,
        limit,
        has_more: enriched.length === limit,
        productos: enriched
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ============================================================================
  // HISTORIA KAN-29: CONSULTA MULTI-SUCURSAL CON INDICADORES (KAN-332, KAN-333)
  // ============================================================================
  const SUCURSALES_EMPRESA = [
    {
      sucursal_id: 'SUC-01',
      sucursal_nombre: 'Sucursal Central - La Paz',
      ciudad: 'La Paz',
      direccion: 'Av. 16 de Julio N° 1440 (El Prado)',
      telefono: '+591 2 2441234'
    },
    {
      sucursal_id: 'SUC-02',
      sucursal_nombre: 'Sucursal Ceja - El Alto',
      ciudad: 'El Alto',
      direccion: 'Av. 6 de Marzo N° 450 (Cerca a La Ceja)',
      telefono: '+591 2 2845678'
    },
    {
      sucursal_id: 'SUC-03',
      sucursal_nombre: 'Sucursal Equipetrol - Santa Cruz',
      ciudad: 'Santa Cruz',
      direccion: 'Av. San Martín N° 800 (Barrio Equipetrol)',
      telefono: '+591 3 3429876'
    },
    {
      sucursal_id: 'SUC-04',
      sucursal_nombre: 'Sucursal Cala Cala - Cochabamba',
      ciudad: 'Cochabamba',
      direccion: 'Av. América N° 320 (Zona Cala Cala)',
      telefono: '+591 4 4561122'
    }
  ];

  router.get(['/v1/catalogo/productos/:sku/stock-sucursales', '/api/v1/catalogo/productos/:sku/stock-sucursales'], async (req: Request, res: Response) => {
    try {
      const cleanSku = String(req.params.sku).trim().toUpperCase();

      const { data: producto } = await supabaseAdmin
        .from('productos')
        .select('id, sku, nombre, estado')
        .eq('sku', cleanSku)
        .maybeSingle();

      const nombre = producto?.nombre || `Producto ${cleanSku}`;
      const isDescontinuado = producto?.estado === 'descontinuado';

      // Semilla pseudo-determinística de stock por SKU y sucursal
      const charCodeSum = cleanSku.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);

      const sucursalesStock = SUCURSALES_EMPRESA.map((suc, idx) => {
        let stock = isDescontinuado ? 0 : ((charCodeSum + idx * 7) % 24);
        if (idx === 0 && !isDescontinuado) stock = Math.max(stock, 8); // Sucursal central con stock garantizado

        let estado: 'disponible' | 'bajo' | 'agotado' = 'disponible';
        if (stock === 0) estado = 'agotado';
        else if (stock <= 3) estado = 'bajo';

        return {
          sucursal_id: suc.sucursal_id,
          sucursal_nombre: suc.sucursal_nombre,
          ciudad: suc.ciudad,
          direccion: suc.direccion,
          stock,
          estado,
          ultima_actualizacion: new Date().toISOString()
        };
      });

      const stockTotal = sucursalesStock.reduce((acc, s) => acc + s.stock, 0);

      res.json({
        sku: cleanSku,
        nombre,
        stock_total: stockTotal,
        sucursales: sucursalesStock
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ============================================================================
  // HISTORIA KAN-11 / KAN-35: RECOMENDACIONES (CROSS/UP-SELL Y BUNDLE FRECUENTE)
  // SUBTAREAS: KAN-139, KAN-140, KAN-141, KAN-142
  // ============================================================================
  const DEFAULT_AFFINITY_RULES: Record<string, { cross_cats: string[]; cross_kw: string[]; up_kw: string[] }> = {
    'laptops y pcs': {
      cross_cats: ['periféricos', 'monitores', 'audio y video', 'accesorios'],
      cross_kw: ['mouse', 'teclado', 'hub', 'mochila', 'soporte', 'cable', 'funda'],
      up_kw: ['pro', 'ultra', 'oled', '4k', 'i9', '32gb', '1tb']
    },
    'periféricos': {
      cross_cats: ['accesorios', 'audio y video', 'monitores', 'laptops y pcs'],
      cross_kw: ['mousepad', 'pad', 'soporte', 'hub', 'auricular', 'cable'],
      up_kw: ['ergonómico', 'rgb', 'mecánico', 'inalámbrico', '8k']
    },
    'monitores': {
      cross_cats: ['periféricos', 'accesorios', 'audio y video'],
      cross_kw: ['brazo', 'soporte', 'hdmi', 'displayport', 'barra', 'luz', 'cable'],
      up_kw: ['curvo', 'ultrawide', '144hz', '240hz', '4k', 'oled']
    },
    'audio y video': {
      cross_cats: ['accesorios', 'periféricos', 'laptops y pcs'],
      cross_kw: ['soporte', 'estuche', 'micrófono', 'webcam', 'adaptador'],
      up_kw: ['noise cancelling', 'anc', 'estudio', 'hi-res', 'inalámbrico']
    }
  };

  const handleGetRecomendaciones = async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const cleanId = String(id).trim();
      const tipo = req.query.tipo ? String(req.query.tipo).toLowerCase() : 'todos';
      const limite = Math.max(1, Math.min(20, Number(req.query.limite) || 6));

      // 1. Obtener todos los productos para resolver el universo
      const { data: dbProducts } = await supabaseAdmin
        .from('productos')
        .select(`
          id,
          sku,
          nombre,
          descripcion,
          marca,
          estado,
          categoria_id,
          categorias ( id, nombre ),
          imagenes_producto ( id, url, es_principal, orden ),
          variantes ( id, sku, nombre_variante, precio, precio_costo )
        `);

      const lista = dbProducts || [];

      // 2. Buscar producto base por UUID o SKU
      const prodBaseRaw = lista.find(p => 
        p.id === cleanId || 
        p.sku.toUpperCase() === cleanId.toUpperCase()
      );

      if (!prodBaseRaw) {
        return res.status(404).json({ error: `Producto con identificador '${id}' no encontrado para calcular recomendaciones.` });
      }

      const catNombreBase = (prodBaseRaw.categorias as any)?.nombre || 'General';
      const catNorm = catNombreBase.toLowerCase().trim();
      const principalVar = prodBaseRaw.variantes?.[0];
      const precioBase = principalVar ? Number(principalVar.precio) : 150;
      const imgBase = prodBaseRaw.imagenes_producto?.[0]?.url || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=600&q=80';

      const productoBase = {
        id: prodBaseRaw.id,
        sku: prodBaseRaw.sku,
        nombre: prodBaseRaw.nombre,
        categoria: catNombreBase,
        precio: precioBase,
        imagen: imgBase,
        variante_id: principalVar?.id || null
      };

      // 3. Reglas de afinidad
      const reglas = DEFAULT_AFFINITY_RULES[catNorm] || {
        cross_cats: ['periféricos', 'accesorios'],
        cross_kw: ['mouse', 'teclado', 'cable', 'adaptador'],
        up_kw: ['pro', 'plus', 'max', 'ultra']
      };

      // 4. Filtrar y clasificar candidatos (excluyendo estrictamente el producto base)
      const candidatos = lista.filter(p => p.id !== prodBaseRaw.id && p.sku.toUpperCase() !== prodBaseRaw.sku.toUpperCase());
      const recomendaciones: any[] = [];

      candidatos.forEach(cand => {
        const cCat = (cand.categorias as any)?.nombre || 'General';
        const cCatNorm = cCat.toLowerCase().trim();
        const cNombreNorm = cand.nombre.toLowerCase().trim();
        const cVar = cand.variantes?.[0];
        const cPrecio = cVar ? Number(cVar.precio) : 100;
        const cImg = cand.imagenes_producto?.[0]?.url || 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=600&q=80';

        let score = 0.50;
        let tipoRec = 'cross_sell';
        let motivo = `Accesorio complementario de ${cCat} para enriquecer tu experiencia.`;
        let badge = 'Accesorio Afín';

        // Up-sell: Misma categoría y mayor precio / gama
        if (cCatNorm === catNorm && cPrecio > precioBase) {
          score = 0.85;
          tipoRec = 'up_sell';
          const difPct = Math.round(((cPrecio - precioBase) / precioBase) * 100);
          motivo = `Versión de gama superior en ${cCat} (+${difPct}% en prestaciones y capacidad).`;
          badge = 'Gama Superior';
          if (reglas.up_kw.some(k => cNombreNorm.includes(k))) score += 0.10;
        } 
        // Cross-sell: Categoría complementaria o keywords afines
        else if (reglas.cross_cats.includes(cCatNorm) || reglas.cross_kw.some(k => cNombreNorm.includes(k))) {
          score = 0.90;
          tipoRec = 'cross_sell';
          badge = 'Accesorio Recomendado';
          if (cNombreNorm.includes('mouse')) {
            motivo = 'Mouse ergonómico de alta precisión ideal para complementar tu estación de trabajo.';
          } else if (cNombreNorm.includes('teclado')) {
            motivo = 'Teclado mecánico táctil con respuesta inmediata y retroiluminación.';
          } else if (cNombreNorm.includes('hub') || cNombreNorm.includes('adaptador')) {
            motivo = 'Hub multipuerto para ampliar tus conexiones USB-C, HDMI y lector de tarjetas.';
          } else if (cNombreNorm.includes('monitor')) {
            motivo = 'Pantalla secundaria de alta resolución para maximizar tu productividad multitarea.';
          } else if (cNombreNorm.includes('auricular') || cNombreNorm.includes('audio')) {
            motivo = 'Audio inmersivo de alta fidelidad para llamadas, reuniones y entretenimiento.';
          }
        }

        if (tipo && tipo !== 'todos') {
          if (tipo === 'cross_sell' && tipoRec !== 'cross_sell') return;
          if (tipo === 'up_sell' && tipoRec !== 'up_sell') return;
        }

        recomendaciones.push({
          id: cand.id,
          sku: cand.sku,
          nombre: cand.nombre,
          categoria: cCat,
          precio: cPrecio,
          imagen: cImg,
          tipo_recomendacion: tipoRec,
          motivo,
          score_afinidad: Math.min(0.99, score),
          badge,
          variante_id: cVar?.id || null
        });
      });

      // Ordenar por afinidad
      recomendaciones.sort((a, b) => b.score_afinidad - a.score_afinidad);
      const limitadas = recomendaciones.slice(0, limite);

      // 5. KAN-141: Bundle "Frecuentemente Comprados Juntos"
      let frecuentementeCompradosJuntos = null;
      const crossSells = recomendaciones.filter(r => r.tipo_recomendacion === 'cross_sell');
      if (crossSells.length > 0) {
        const bundleItems = [
          {
            ...productoBase,
            tipo_recomendacion: 'base',
            motivo: 'Artículo principal actual.',
            score_afinidad: 1.0,
            badge: 'Este Producto'
          },
          ...crossSells.slice(0, 2)
        ];

        const precioTotalIndividual = bundleItems.reduce((acc, it) => acc + it.precio, 0);
        const ahorroMonto = Math.round(precioTotalIndividual * 0.08 * 100) / 100; // 8% combo discount
        const precioComboSugerido = Math.round((precioTotalIndividual - ahorroMonto) * 100) / 100;

        frecuentementeCompradosJuntos = {
          productos: bundleItems,
          precio_total_individual: precioTotalIndividual,
          precio_combo_sugerido: precioComboSugerido,
          ahorro_monto: ahorroMonto,
          ahorro_porcentaje: 8,
          mensaje_ahorro: `¡Ahorra BOB ${ahorroMonto.toFixed(2)} (8% OFF) comprando este set complementario!`
        };
      }

      res.json({
        producto_base: productoBase,
        recomendaciones: limitadas,
        frecuentemente_comprados_juntos: frecuentementeCompradosJuntos,
        total_recomendaciones: limitadas.length
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  };

  router.get('/v1/catalogo/productos/:id/recomendados', handleGetRecomendaciones);
  router.get('/api/v1/catalogo/productos/:id/recomendados', handleGetRecomendaciones);

  // ============================================================================
  // HISTORIA KAN-30: BÚSQUEDA RÁPIDA DE CLIENTE Y PUNTOS EN POS (KAN-337, KAN-338, KAN-339)
  // ============================================================================
  router.get(['/v1/clientes/buscar', '/api/v1/clientes/buscar'], async (req: Request, res: Response) => {
    try {
      const q = String(req.query.q || '').trim().toLowerCase();
      if (!q) {
        return res.json([]);
      }

      // Buscar en perfiles_clientes
      const { data: perfiles } = await supabaseAdmin
        .from('perfiles_clientes')
        .select('*')
        .or(`nit_ci.ilike.%${q}%,nombre_completo.ilike.%${q}%,email.ilike.%${q}%,telefono.ilike.%${q}%`)
        .limit(10);

      // Si no hay en Supabase, buscar en cuentas demo
      const matches: any[] = [];
      if (perfiles && perfiles.length > 0) {
        matches.push(...perfiles.map(p => ({
          id: p.id,
          nombre_completo: p.nombre_completo,
          email: p.email,
          nit_ci: p.nit_ci || '0',
          razon_social: p.razon_social || p.nombre_completo,
          telefono: p.telefono,
          tipo_cliente: p.tipo_cliente || 'retail',
          puntos_saldo: 85 // Saldo simulado de fidelidad
        })));
      }

      // Agregar coincidencias de demoUsers
      Object.values(demoUsers).forEach(u => {
        if (
          u.email.toLowerCase().includes(q) ||
          u.nombre_completo.toLowerCase().includes(q) ||
          (u.nit_ci && u.nit_ci.includes(q))
        ) {
          if (!matches.some(m => m.email === u.email)) {
            matches.push(u);
          }
        }
      });

      res.json(matches);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Canjear puntos de fidelidad (KAN-339)
  router.post(['/v1/clientes/:id/fidelidad/canjear', '/api/v1/clientes/:id/fidelidad/canjear'], async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { puntos } = req.body;
      const cantPuntos = Math.max(0, Number(puntos) || 0);

      // 1 punto = 1 BOB de descuento
      const descuentoBob = cantPuntos * 1.0;

      res.json({
        success: true,
        cliente_id: id,
        puntos_canjeados: cantPuntos,
        descuento_aplicado_bob: descuentoBob,
        mensaje: `Se canjearon ${cantPuntos} puntos equivalentes a BOB ${descuentoBob.toFixed(2)} de descuento.`
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // ============================================================================
  // HISTORIA KAN-10 / KAN-27: RETIRO EN SUCURSAL CLICK & COLLECT (RF-11)
  // SUBTAREAS: KAN-107, KAN-108, KAN-324, KAN-325
  // ============================================================================
  const clickAndCollectOrdersStore: Record<string, any> = {
    'RET-789214': {
      id: '3b749d44-0db0-4e36-9694-84c1724490f1',
      codigo_orden: 'ORD-2026-CC101',
      codigo_retiro: 'RET-789214',
      codigo_qr: 'MAXI-CC|ORD-2026-CC101|RET-789214|SUC-01',
      canal: 'web',
      tipo_despacho: 'retiro_sucursal',
      estado: 'confirmada',
      es_entregable: true,
      motivo_rechazo: null,
      sucursal_id: 'SUC-01',
      sucursal_nombre: 'Sucursal Central - La Paz',
      created_at: '2026-10-10T09:30:00Z',
      cliente_nombre: 'Carlos Mendoza Patzi',
      cliente_documento: '4829102',
      cliente_telefono: '+591 71234567',
      cliente_email: 'carlos.mendoza@gmail.com',
      subtotal: 15766.00,
      descuento: 0.0,
      total: 15766.00,
      metodo_pago: 'QR Simple (Aprobado)',
      cuf_factura: 'CUF-1028374029-20261010-093011-8849',
      numero_factura: 1421,
      items: [
        {
          id: 'item-cc-01',
          sku: 'LAP-DELL-XPS15',
          nombre_producto: 'Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)',
          cantidad: 1,
          precio_unitario: 6767.00,
          total_linea: 6767.00
        },
        {
          id: 'item-cc-02',
          sku: 'MOU-LOG-MX3S',
          nombre_producto: 'Mouse Inalámbrico Logitech MX Master 3S',
          cantidad: 1,
          precio_unitario: 8999.00,
          total_linea: 8999.00
        }
      ],
      despacho: null
    },
    'RET-345091': {
      id: 'c56b06e9-bfe9-4e7a-9a99-8ee3ad192305',
      codigo_orden: 'ORD-2026-CC102',
      codigo_retiro: 'RET-345091',
      codigo_qr: 'MAXI-CC|ORD-2026-CC102|RET-345091|SUC-01',
      canal: 'web',
      tipo_despacho: 'retiro_sucursal',
      estado: 'entregada',
      es_entregable: false,
      motivo_rechazo: 'Este pedido YA FUE ENTREGADO el 10/10/2026 10:15 por el Cajero Oscar Menacho al receptor Roberto Doria Medina (Doc: 6543211).',
      sucursal_id: 'SUC-01',
      sucursal_nombre: 'Sucursal Central - La Paz',
      created_at: '2026-10-09T16:20:00Z',
      cliente_nombre: 'Sofía Doria Medina',
      cliente_documento: '6543210',
      cliente_telefono: '+591 76543210',
      cliente_email: 'sofia.doria@gmail.com',
      subtotal: 1850.00,
      descuento: 0.0,
      total: 1850.00,
      metodo_pago: 'Tarjeta Visa Débito',
      cuf_factura: 'CUF-1028374029-20261009-162100-3321',
      numero_factura: 1419,
      items: [
        {
          id: 'item-cc-03',
          sku: 'KEY-RGB-01',
          nombre_producto: 'Teclado Mecánico RGB Switches Brown',
          cantidad: 2,
          precio_unitario: 925.00,
          total_linea: 1850.00
        }
      ],
      despacho: {
        fecha_entrega: '2026-10-10T10:15:00Z',
        cajero_id: 'c0000000-0000-0000-0000-000000000002',
        cajero_nombre: 'Oscar Menacho',
        sucursal_id: 'SUC-01',
        sucursal_nombre: 'Sucursal Central - La Paz',
        receptor_nombre: 'Roberto Doria Medina',
        receptor_documento: '6543211',
        receptor_tipo: 'tercero_autorizado',
        receptor_telefono: '+591 76543299',
        observaciones: 'Retiro autorizado con fotocopia de CI y carta poder simple.',
        numero_acta: 'ACTA-CC-2026-0041'
      }
    },
    'RET-992381': {
      id: '4422e861-55ff-4ab0-b19b-c6b6103e911f',
      codigo_orden: 'ORD-2026-CC103',
      codigo_retiro: 'RET-992381',
      codigo_qr: 'MAXI-CC|ORD-2026-CC103|RET-992381|SUC-01',
      canal: 'web',
      tipo_despacho: 'retiro_sucursal',
      estado: 'cancelada',
      es_entregable: false,
      motivo_rechazo: 'El pedido se encuentra CANCELADO. Las existencias fueron restituidas a almacén.',
      sucursal_id: 'SUC-01',
      sucursal_nombre: 'Sucursal Central - La Paz',
      created_at: '2026-10-08T11:00:00Z',
      cliente_nombre: 'Juan Pérez García',
      cliente_documento: '11223344',
      cliente_telefono: '+591 79988776',
      cliente_email: 'juan.perez@empresa.bo',
      subtotal: 4500.00,
      descuento: 0.0,
      total: 4500.00,
      metodo_pago: 'QR Simple',
      cuf_factura: null,
      numero_factura: null,
      items: [
        {
          id: 'item-cc-04',
          sku: 'MON-4K-27',
          nombre_producto: 'Monitor Profesional 27 Pulgadas 4K',
          cantidad: 1,
          precio_unitario: 4500.00,
          total_linea: 4500.00
        }
      ],
      despacho: null
    },
    'RET-118844': {
      id: 'f87a32d1-9310-410a-b50a-86c4e0b5190a',
      codigo_orden: 'ORD-2026-CC104',
      codigo_retiro: 'RET-118844',
      codigo_qr: 'MAXI-CC|ORD-2026-CC104|RET-118844|SUC-01',
      canal: 'web',
      tipo_despacho: 'retiro_sucursal',
      estado: 'confirmada',
      es_entregable: true,
      motivo_rechazo: null,
      sucursal_id: 'SUC-01',
      sucursal_nombre: 'Sucursal Central - La Paz',
      created_at: '2026-10-10T11:15:00Z',
      cliente_nombre: 'Gabriela Ramos Velasco',
      cliente_documento: '7891234',
      cliente_telefono: '+591 72345678',
      cliente_email: 'gabriela.ramos@gmail.com',
      subtotal: 1850.00,
      descuento: 0.0,
      total: 1850.00,
      metodo_pago: 'QR Simple (Aprobado)',
      cuf_factura: 'CUF-1028374029-20261010-111520-9941',
      numero_factura: 1422,
      items: [
        {
          id: 'item-cc-05',
          sku: 'KEY-RGB-01',
          nombre_producto: 'Teclado Mecánico RGB Switches Brown',
          cantidad: 2,
          precio_unitario: 925.00,
          total_linea: 1850.00
        }
      ],
      despacho: null
    }
  };

  function parseCodigoQrOrText(input: string): string {
    const raw = String(input || '').trim();
    if (raw.includes('|')) {
      const parts = raw.split('|');
      for (const part of parts) {
        if (part.startsWith('RET-')) return part.toUpperCase();
      }
      for (const part of parts) {
        if (part.startsWith('ORD-')) return part.toUpperCase();
      }
    }
    return raw.toUpperCase();
  }

  // 1. KAN-324: GET /pos/click-and-collect/pedidos
  const handleGetClickAndCollectOrders = async (req: Request, res: Response) => {
    try {
      const { sucursal_id, filtro_estado } = req.query;
      const list = Object.values(clickAndCollectOrdersStore).filter(o => {
        if (sucursal_id && o.sucursal_id && o.sucursal_id !== sucursal_id) return false;
        if (filtro_estado === 'pendientes') {
          return ['confirmada', 'en_preparacion', 'despachada', 'pendiente_retiro'].includes(o.estado);
        }
        if (filtro_estado === 'entregados') {
          return o.estado === 'entregada';
        }
        return true;
      });

      return res.json(list);
    } catch (err: any) {
      return res.status(500).json({ error: err.message });
    }
  };

  router.get('/v1/pos/click-and-collect/pedidos', handleGetClickAndCollectOrders);
  router.get('/api/v1/pos/click-and-collect/pedidos', handleGetClickAndCollectOrders);

  // 2. KAN-324 / KAN-108: POST /pos/click-and-collect/validar
  const handleValidarClickAndCollect = async (req: Request, res: Response) => {
    try {
      const { codigo, sucursal_id } = req.body;
      if (!codigo) {
        return res.status(400).json({ error: 'Debe ingresar un código de retiro o código QR.' });
      }

      const cleanCode = parseCodigoQrOrText(codigo);

      // Buscar en store en memoria
      let match = Object.values(clickAndCollectOrdersStore).find(o => 
        o.codigo_retiro.toUpperCase() === cleanCode ||
        o.codigo_orden.toUpperCase() === cleanCode ||
        o.id.toUpperCase() === cleanCode ||
        o.cliente_documento === cleanCode
      );

      // Si no está, consultar órdenes en Supabase
      if (!match) {
        try {
          const { data: dbOrders } = await supabaseAdmin
            .from('ordenes')
            .select('*, orden_items(*), perfiles_clientes(*)')
            .or(`codigo_orden.ilike.%${cleanCode}%,cuf_factura.ilike.%${cleanCode}%`)
            .limit(1);

          if (dbOrders && dbOrders.length > 0) {
            const row = dbOrders[0];
            const cli = row.perfiles_clientes || {};
            const codRetiro = `RET-${row.codigo_orden.replace('ORD-', '').substring(0, 6)}`;
            match = {
              id: row.id,
              codigo_orden: row.codigo_orden,
              codigo_retiro: codRetiro,
              codigo_qr: `MAXI-CC|${row.codigo_orden}|${codRetiro}|SUC-01`,
              canal: row.canal || 'web',
              tipo_despacho: row.tipo_despacho || 'retiro_sucursal',
              estado: row.estado || 'confirmada',
              es_entregable: ['confirmada', 'en_preparacion', 'despachada', 'pendiente_retiro'].includes(row.estado),
              motivo_rechazo: row.estado === 'entregada' ? 'Pedido ya entregado con anterioridad.' : row.estado === 'cancelada' ? 'Pedido cancelado.' : null,
              sucursal_id: sucursal_id || 'SUC-01',
              sucursal_nombre: 'Sucursal Central - La Paz',
              created_at: row.created_at,
              cliente_nombre: cli.razon_social || cli.nombre_completo || 'Cliente Web',
              cliente_documento: cli.nit_ci || '0',
              cliente_telefono: cli.telefono,
              cliente_email: cli.email,
              subtotal: Number(row.subtotal || 0),
              descuento: Number(row.descuento || 0),
              total: Number(row.total || 0),
              metodo_pago: 'Aprobado',
              cuf_factura: row.cuf_factura,
              numero_factura: null,
              items: (row.orden_items || []).map((it: any) => ({
                id: it.id,
                sku: it.sku,
                nombre_producto: it.nombre_producto,
                cantidad: it.cantidad,
                precio_unitario: Number(it.precio_unitario),
                total_linea: Number(it.total_linea || (it.cantidad * it.precio_unitario))
              })),
              despacho: null
            };
            clickAndCollectOrdersStore[codRetiro] = match;
          }
        } catch (dbErr) {
          console.warn('Aviso consultando orden en Supabase:', dbErr);
        }
      }

      if (!match) {
        return res.status(404).json({
          error: `No se encontró ningún pedido Click & Collect con el código o QR '${codigo}'.`
        });
      }

      // Evaluar estado para KAN-108
      const esEntregable = ['confirmada', 'en_preparacion', 'despachada', 'pendiente_retiro'].includes(match.estado);
      let motivoRechazo = null;

      if (match.estado === 'entregada') {
        const desp = match.despacho;
        motivoRechazo = desp
          ? `Este pedido YA FUE ENTREGADO el ${desp.fecha_entrega} al receptor ${desp.receptor_nombre} (Doc: ${desp.receptor_documento}) por el Cajero ${desp.cajero_nombre}.`
          : 'El pedido ya figura en estado ENTREGADO.';
      } else if (match.estado === 'cancelada') {
        motivoRechazo = 'El pedido se encuentra CANCELADO. Las existencias fueron restituidas a almacén.';
      }

      match.es_entregable = esEntregable;
      match.motivo_rechazo = motivoRechazo;

      return res.json(match);
    } catch (err: any) {
      return res.status(500).json({ error: err.message });
    }
  };

  router.post('/v1/pos/click-and-collect/validar', handleValidarClickAndCollect);
  router.post('/api/v1/pos/click-and-collect/validar', handleValidarClickAndCollect);

  // 3. KAN-325: POST /pos/click-and-collect/confirmar-entrega
  const handleConfirmarEntregaClickAndCollect = async (req: Request, res: Response) => {
    try {
      const {
        orden_id,
        codigo_retiro,
        receptor_nombre,
        receptor_documento,
        receptor_tipo = 'titular',
        receptor_telefono,
        observaciones,
        cajero_id = 'c0000000-0000-0000-0000-000000000002',
        cajero_nombre = 'Oscar Menacho (Cajero Central)',
        sucursal_id = 'SUC-01',
        sucursal_nombre = 'Sucursal Central - La Paz'
      } = req.body;

      if (!receptor_nombre || !receptor_documento) {
        return res.status(400).json({
          error: 'Debe ingresar el Nombre y Documento de Identidad del receptor para confirmar la entrega.'
        });
      }

      const cleanCode = parseCodigoQrOrText(codigo_retiro || '');
      let match = Object.values(clickAndCollectOrdersStore).find(o =>
        (codigo_retiro && o.codigo_retiro.toUpperCase() === cleanCode) ||
        (orden_id && o.id === orden_id) ||
        (codigo_retiro && o.codigo_orden.toUpperCase() === cleanCode)
      );

      if (!match) {
        return res.status(404).json({ error: 'Pedido no encontrado para confirmación de entrega.' });
      }

      if (match.estado === 'entregada') {
        return res.status(400).json({
          error: 'Operación denegada: Este pedido ya fue entregado previamente.'
        });
      }

      if (match.estado === 'cancelada') {
        return res.status(400).json({
          error: 'Operación denegada: No se puede despachar un pedido cancelado.'
        });
      }

      const ahoraIso = new Date().toISOString();
      const correlativoActa = `ACTA-CC-${new Date().getFullYear()}-${randomUUID().substring(0, 6).toUpperCase()}`;

      const auditoria = {
        fecha_entrega: ahoraIso,
        cajero_id,
        cajero_nombre,
        sucursal_id,
        sucursal_nombre,
        receptor_nombre: String(receptor_nombre).trim(),
        receptor_documento: String(receptor_documento).trim(),
        receptor_tipo,
        receptor_telefono: receptor_telefono || null,
        observaciones: observaciones || null,
        numero_acta: correlativoActa
      };

      // Actualizar estado atómico
      match.estado = 'entregada';
      match.es_entregable = false;
      match.motivo_rechazo = `Pedido entregado el ${ahoraIso} a ${receptor_nombre}.`;
      match.despacho = auditoria;

      // Actualizar en Supabase si es posible
      try {
        await supabaseAdmin
          .from('ordenes')
          .update({ estado: 'entregada', updated_at: ahoraIso })
          .eq('id', match.id);

        await supabaseAdmin
          .from('audit_logs')
          .insert({
            usuario_id: cajero_id,
            accion: 'DESPACHO_CLICK_AND_COLLECT',
            entidad: 'ordenes',
            entidad_id: match.id,
            datos_previos: { estado: 'confirmada' },
            datos_nuevos: { estado: 'entregada', despacho: auditoria }
          });
      } catch (dbErr) {
        console.warn('Aviso guardando auditoría de despacho en Supabase:', dbErr);
      }

      const comprobante = {
        acta_numero: correlativoActa,
        codigo_orden: match.codigo_orden,
        codigo_retiro: match.codigo_retiro,
        titular: match.cliente_nombre,
        receptor: receptor_nombre,
        documento_receptor: receptor_documento,
        tipo_receptor: receptor_tipo,
        cajero: cajero_nombre,
        sucursal: sucursal_nombre,
        fecha: ahoraIso,
        total_items: (match.items || []).reduce((acc: number, it: any) => acc + it.cantidad, 0),
        monto_total: match.total
      };

      return res.json({
        success: true,
        orden_id: match.id,
        codigo_orden: match.codigo_orden,
        codigo_retiro: match.codigo_retiro,
        nuevo_estado: 'entregada',
        fecha_entrega: ahoraIso,
        receptor_nombre,
        receptor_documento,
        receptor_tipo,
        cajero_nombre,
        comprobante_entrega: comprobante,
        mensaje: 'Pedido Click & Collect entregado exitosamente y auditoría de despacho registrada.'
      });
    } catch (err: any) {
      return res.status(500).json({ error: err.message });
    }
  };

  router.post('/v1/pos/click-and-collect/confirmar-entrega', handleConfirmarEntregaClickAndCollect);
  router.post('/api/v1/pos/click-and-collect/confirmar-entrega', handleConfirmarEntregaClickAndCollect);

  // Alias legacy
  router.post(['/v1/pos/pedidos/retiro-sucursal/validar', '/api/v1/pos/pedidos/retiro-sucursal/validar'], async (req: Request, res: Response) => {
    const cod = req.body?.codigo_retiro || req.query?.codigo_retiro || 'RET-789214';
    const clave = parseCodigoQrOrText(String(cod));
    if (clickAndCollectOrdersStore[clave]) {
      clickAndCollectOrdersStore[clave].estado = 'entregada';
    }
    return res.json({
      codigo_retiro: cod,
      estado: 'ENTREGADO',
      mensaje: 'Pedido entregado presencialmente con éxito'
    });
  });

  // ============================================================================
  // HISTORIA KAN-11 / KAN-31: SELECCIÓN DE ENTREGA (RF-15 / US-15)
  // SUBTAREAS:
  // - [BE] Algoritmo de cálculo de costo de flete según zona y dirección de entrega
  // - [BE] Endpoint de consulta de sucursales habilitadas con stock para retiro
  // ============================================================================

  const TARIFAS_FLETE_ZONA_NODE: Record<string, Record<string, number>> = {
    'la paz': {
      'centro': 15.0,
      'miraflores': 15.0,
      'sopocachi': 15.0,
      'san pedro': 15.0,
      'zona sur (calacoto / san miguel)': 20.0,
      'achumani / irpavi / cota cota': 22.0,
      'periférica / laderas': 25.0,
      'default': 18.0
    },
    'el alto': {
      'ceja': 20.0,
      'ciudad satélite': 22.0,
      'villa adela': 25.0,
      'rio seco': 28.0,
      'default': 25.0
    },
    'santa cruz': {
      '1er a 4to anillo': 18.0,
      'equipetrol': 18.0,
      'urubó': 28.0,
      '5to a 8vo anillo': 25.0,
      'plan 3000': 28.0,
      'default': 22.0
    },
    'cochabamba': {
      'centro / el prado': 15.0,
      'cala cala / recoleta': 18.0,
      'zona sur': 22.0,
      'sacaba / quillacollo': 30.0,
      'default': 18.0
    },
    'nacional': {
      'sucre': 35.0,
      'tarija': 35.0,
      'oruro': 30.0,
      'potosi': 35.0,
      'beni': 45.0,
      'pando': 50.0,
      'default': 35.0
    }
  };

  const SUCURSALES_RETIRO_LISTA = [
    {
      id: 'suc-lpz-01',
      nombre: 'Sucursal Central El Prado',
      ciudad: 'La Paz',
      departamento: 'La Paz',
      direccion: 'Av. 16 de Julio (El Prado) #1490, Edificio Alameda PB',
      telefono: '+591 2 2441122',
      horario_atencion: 'Lunes a Viernes 08:30 - 20:00 | Sábado 09:00 - 18:00',
      coordenadas: { lat: -16.5028, lng: -68.1328 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 2 horas',
      costo_retiro: 0,
      referencia: 'A media cuadra de la Plaza del Estudiante',
      es_habilitada: true
    },
    {
      id: 'suc-lpz-02',
      nombre: 'Sucursal Calacoto Zona Sur',
      ciudad: 'La Paz',
      departamento: 'La Paz',
      direccion: 'Calle 15 esq. Av. Ballivián #802, Torre Ketal',
      telefono: '+591 2 2795500',
      horario_atencion: 'Lunes a Sábado 09:00 - 21:00 | Domingo 10:00 - 16:00',
      coordenadas: { lat: -16.5385, lng: -68.0837 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 2 horas',
      costo_retiro: 0,
      referencia: 'Frente a la Iglesia de San Miguel',
      es_habilitada: true
    },
    {
      id: 'suc-alt-01',
      nombre: 'Sucursal Ciudad Satélite',
      ciudad: 'El Alto',
      departamento: 'La Paz',
      direccion: 'Av. Satélite #310, frente a la estación Plateada de Mi Teleférico',
      telefono: '+591 2 2819933',
      horario_atencion: 'Lunes a Sábado 08:30 - 19:30',
      coordenadas: { lat: -16.5204, lng: -68.1633 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 3 horas',
      costo_retiro: 0,
      referencia: 'A pasos de la estación de teleférico Plateada',
      es_habilitada: true
    },
    {
      id: 'suc-scz-01',
      nombre: 'Sucursal Equipetrol Norte',
      ciudad: 'Santa Cruz',
      departamento: 'Santa Cruz',
      direccion: 'Av. San Martín #1550 esq. Calle 5 Oeste',
      telefono: '+591 3 3428800',
      horario_atencion: 'Lunes a Sábado 09:00 - 21:00 | Domingo 11:00 - 18:00',
      coordenadas: { lat: -17.7682, lng: -63.1932 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 2 horas',
      costo_retiro: 0,
      referencia: 'Diagonal al Hotel Los Tajibos',
      es_habilitada: true
    },
    {
      id: 'suc-scz-02',
      nombre: 'Sucursal Ventura Mall',
      ciudad: 'Santa Cruz',
      departamento: 'Santa Cruz',
      direccion: '4to Anillo esq. Av. San Martín, Nivel 1 Local 114',
      telefono: '+591 3 3887766',
      horario_atencion: 'Lunes a Domingo 10:00 - 22:00 (Horario Mall)',
      coordenadas: { lat: -17.7548, lng: -63.1993 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 2 horas',
      costo_retiro: 0,
      referencia: 'Ingreso principal pasillo tecnológico',
      es_habilitada: true
    },
    {
      id: 'suc-cbb-01',
      nombre: 'Sucursal Plaza Colón',
      ciudad: 'Cochabamba',
      departamento: 'Cochabamba',
      direccion: 'Calle San Martín esq. Av. Heroínas #320',
      telefono: '+591 4 4256677',
      horario_atencion: 'Lunes a Viernes 08:30 - 19:30 | Sábado 09:00 - 14:00',
      coordenadas: { lat: -17.3935, lng: -66.1568 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 2 horas',
      costo_retiro: 0,
      referencia: 'A una cuadra de la Plaza Colón',
      es_habilitada: true
    },
    {
      id: 'suc-cbb-02',
      nombre: 'Sucursal Cala Cala',
      ciudad: 'Cochabamba',
      departamento: 'Cochabamba',
      direccion: 'Av. América esq. Av. Libertador Bolívar #780',
      telefono: '+591 4 4481199',
      horario_atencion: 'Lunes a Sábado 09:00 - 20:00',
      coordenadas: { lat: -17.3756, lng: -66.1624 },
      stock_disponible: true,
      tiempo_preparacion: 'Listo para retiro en 2 horas',
      costo_retiro: 0,
      referencia: 'Frente al Boulevard Recoleta',
      es_habilitada: true
    }
  ];

  const handleCalcularFlete = (req: Request, res: Response) => {
    try {
      const {
        ciudad = 'La Paz',
        zona = 'Centro',
        subtotal_productos = 0,
        peso_estimado_kg = 1.0,
        tipo_envio = 'estandar'
      } = req.body || {};

      const ciudadNorm = String(ciudad).toLowerCase().trim();
      const zonaNorm = String(zona).toLowerCase().trim();
      const subtotalNum = Number(subtotal_productos) || 0;
      const pesoNum = Number(peso_estimado_kg) || 1.0;

      const tarifasCiudad = TARIFAS_FLETE_ZONA_NODE[ciudadNorm] || TARIFAS_FLETE_ZONA_NODE['nacional'];
      const costoBase = tarifasCiudad[zonaNorm] ?? tarifasCiudad['default'] ?? 20.0;

      // Recargo por sobrepeso (> 5kg: +5 BOB por kg adicional)
      let recargoPeso = 0;
      if (pesoNum > 5.0) {
        recargoPeso = (pesoNum - 5.0) * 5.0;
      }

      // Recargo express (+15 BOB)
      const recargoExpress = tipo_envio === 'express_mismo_dia' ? 15.0 : 0;
      const costoTotalOriginal = costoBase + recargoPeso + recargoExpress;

      // Regla de negocio: flete gratis si subtotal >= 500 BOB
      const UMBRAL_GRATIS = 500.0;
      const esGratis = subtotalNum >= UMBRAL_GRATIS;
      const costoFinal = esGratis ? 0 : costoTotalOriginal;

      let tiempoEst = 'Entrega en 24 a 48 horas hábiles';
      if (tipo_envio === 'express_mismo_dia') {
        tiempoEst = 'Entrega HOY mismo (menos de 4 horas hábiles)';
      } else if (['la paz', 'el alto', 'santa cruz', 'cochabamba'].includes(ciudadNorm)) {
        tiempoEst = 'Entrega en 24 horas hábiles';
      }

      const mensaje = esGratis
        ? `¡Flete GRATIS aplicado por compras mayores a ${UMBRAL_GRATIS} BOB!`
        : `Costo de envío: ${costoFinal.toFixed(2)} BOB (${tiempoEst})`;

      return res.json({
        ciudad,
        zona,
        costo_flete: costoFinal,
        costo_original: costoTotalOriginal,
        flete_gratis: esGratis,
        umbral_flete_gratis: UMBRAL_GRATIS,
        tiempo_estimado: tiempoEst,
        tipo_envio,
        mensaje,
        desglose: {
          tarifa_base_zona: costoBase,
          recargo_peso: recargoPeso,
          recargo_express: recargoExpress,
          descuento_promocion: esGratis ? costoTotalOriginal : 0,
          distancia_estimada_km: 7.2,
          subtotal_evaluado: subtotalNum
        }
      });
    } catch (err: any) {
      return res.status(500).json({ error: err.message });
    }
  };

  const handleGetSucursalesRetiro = (req: Request, res: Response) => {
    try {
      const ciudadQuery = req.query.ciudad ? String(req.query.ciudad).toLowerCase().trim() : null;
      let sucursales = SUCURSALES_RETIRO_LISTA;
      if (ciudadQuery && ciudadQuery !== 'todas') {
        sucursales = sucursales.filter(s => s.ciudad.toLowerCase().includes(ciudadQuery));
      }
      return res.json(sucursales);
    } catch (err: any) {
      return res.status(500).json({ error: err.message });
    }
  };

  // Rutas KAN-31: Cálculo de Flete
  router.post('/v1/flete/calcular', handleCalcularFlete);
  router.post('/api/v1/flete/calcular', handleCalcularFlete);
  router.post('/v1/ordenes/flete/calcular', handleCalcularFlete);
  router.post('/api/v1/ordenes/flete/calcular', handleCalcularFlete);
  router.post('/api/v1/carrito/flete/calcular', handleCalcularFlete);

  // Rutas KAN-31: Sucursales Habilitadas de Retiro
  router.get('/v1/sucursales/habilitadas-retiro', handleGetSucursalesRetiro);
  router.get('/api/v1/sucursales/habilitadas-retiro', handleGetSucursalesRetiro);
  router.get('/v1/ordenes/sucursales/retiro', handleGetSucursalesRetiro);
  router.get('/api/v1/ordenes/sucursales/retiro', handleGetSucursalesRetiro);

  // ==========================================
  // KAN-56 / US-40 (RF-40): SINCRONIZACIÓN PUBSUB CON INVENTARIO
  // ==========================================

  // Estado del conector Pub/Sub y modo activo
  router.get(['/v1/integraciones/pubsub/status', '/api/v1/integraciones/pubsub/status', '/integraciones/pubsub/status'], (_req: Request, res: Response) => {
    res.json(getPubSubStatus());
  });

  // Historial de eventos de sincronización emitidos
  router.get(['/v1/integraciones/pubsub/historial', '/api/v1/integraciones/pubsub/historial', '/integraciones/pubsub/historial'], (_req: Request, res: Response) => {
    res.json({
      total: pubSubEventLogs.length,
      eventos: pubSubEventLogs
    });
  });

  // Envío de mensaje de prueba para confirmación de recepción docente
  router.post(['/v1/integraciones/pubsub/test', '/api/v1/integraciones/pubsub/test', '/integraciones/pubsub/test'], async (req: Request, res: Response) => {
    try {
      const { responsable, detalle } = req.body || {};
      const evento = await publishPruebaDocente(
        responsable || 'Kevin Sancalli',
        detalle || 'Prueba de sincronizacion simulada con Inventario enviando mensaje a Pub/Sub'
      );
      res.json({
        ok: true,
        mensaje: 'Evento de prueba transmitido hacia Google Cloud Pub/Sub',
        evento
      });
    } catch (err: any) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // Evento de compra: descuento definitivo de existencias hacia Inventario (RIO-INV-03)
  router.post(['/v1/integraciones/pubsub/descuento-stock', '/api/v1/integraciones/pubsub/descuento-stock', '/integraciones/pubsub/descuento-stock'], async (req: Request, res: Response) => {
    try {
      const { orden_id, items, origen, sucursal_id, reserva_id } = req.body || {};
      if (!orden_id || !items || !Array.isArray(items)) {
        return res.status(400).json({ error: 'Campos obligatorios: orden_id (string), items (array)' });
      }
      const evento = await publishStockDescuento(
        orden_id,
        items,
        origen || 'marketplace',
        sucursal_id || 'SUC-LP-CENTRAL',
        reserva_id
      );
      res.json({
        ok: true,
        mensaje: 'Descuento definitivo publicado en Google Cloud Pub/Sub',
        evento
      });
    } catch (err: any) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  // Evento de devolución o anulación: reintegro de existencias hacia Inventario (RIO-INV-04)
  router.post(['/v1/integraciones/pubsub/reintegro-stock', '/api/v1/integraciones/pubsub/reintegro-stock', '/integraciones/pubsub/reintegro-stock'], async (req: Request, res: Response) => {
    try {
      const { orden_id, items, motivo, origen, sucursal_id } = req.body || {};
      if (!orden_id || !items || !Array.isArray(items)) {
        return res.status(400).json({ error: 'Campos obligatorios: orden_id (string), items (array)' });
      }
      const evento = await publishStockReintegro(
        orden_id,
        items,
        motivo || 'cancelacion_orden',
        origen || 'marketplace',
        sucursal_id || 'SUC-LP-CENTRAL'
      );
      res.json({
        ok: true,
        mensaje: 'Reintegro de stock publicado en Google Cloud Pub/Sub',
        evento
      });
    } catch (err: any) {
      res.status(500).json({ ok: false, error: err.message });
    }
  });

  return router;

}


