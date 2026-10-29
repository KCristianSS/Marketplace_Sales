<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { apiClient } from '@/api/client';
import type { Producto, ImagenProducto } from '@/types';
import { 
  UploadCloud, 
  Image as ImageIcon, 
  Trash2, 
  Star, 
  ArrowLeft, 
  ArrowRight, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  Maximize2, 
  X, 
  Sparkles,
  Layers,
  GripVertical,
  ExternalLink
} from 'lucide-vue-next';

const props = defineProps<{
  producto: Producto;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'updated', productoId: string): void;
}>();

// Estado de imágenes
const imagenes = ref<ImagenProducto[]>([]);
const isLoading = ref(false);
const isUploading = ref(false);
const uploadProgress = ref<{ [key: string]: { name: string; progress: number; preview: string; size: string } }>({});
const errorMsg = ref<string | null>(null);
const successMsg = ref<string | null>(null);

// Estado de Drag and drop del uploader
const isDraggingOver = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

// Estado de Drag and drop de reordenamiento
const draggedIndex = ref<number | null>(null);
const isReordering = ref(false);

// Modal de confirmación de eliminación
const imageToDelete = ref<ImagenProducto | null>(null);
const isDeleting = ref(false);

// Modal de vista previa en alta resolución
const previewImage = ref<ImagenProducto | null>(null);

// Cargar imágenes del producto
async function loadImagenes() {
  if (!props.producto?.id) return;
  isLoading.value = true;
  errorMsg.value = null;
  try {
    const res = await apiClient.get(`/productos/${props.producto.id}/imagenes`);
    imagenes.value = res.data.imagenes || [];
  } catch (err: any) {
    console.error('Error cargando imágenes:', err);
    errorMsg.value = err.response?.data?.error || 'No se pudieron cargar las imágenes de este producto.';
  } finally {
    isLoading.value = false;
  }
}

watch(() => props.producto?.id, () => {
  loadImagenes();
}, { immediate: true });

// Formatear tamaño de archivo en bytes
function formatBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Manejar selección de archivos para subir
async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    await uploadFiles(Array.from(target.files));
    target.value = '';
  }
}

// Manejar Drag & Drop en el uploader
function onDragOver(e: DragEvent) {
  e.preventDefault();
  isDraggingOver.value = true;
}

function onDragLeave(e: DragEvent) {
  e.preventDefault();
  isDraggingOver.value = false;
}

async function onDrop(e: DragEvent) {
  e.preventDefault();
  isDraggingOver.value = false;
  if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
    const imageFiles = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) {
      errorMsg.value = 'Solo se admiten archivos de formato imagen (JPG, PNG, WebP, etc.).';
      return;
    }
    await uploadFiles(imageFiles);
  }
}

// Subir archivos mediante multipart/form-data
// KAN-75 & KAN-76
async function uploadFiles(files: File[]) {
  if (!props.producto?.id) return;
  isUploading.value = true;
  errorMsg.value = null;
  successMsg.value = null;

  // Previsualización inmediata en el cliente
  const currentUploads: typeof uploadProgress.value = {};
  files.forEach((file, idx) => {
    const key = `upload-${Date.now()}-${idx}`;
    currentUploads[key] = {
      name: file.name,
      progress: 20,
      preview: URL.createObjectURL(file),
      size: formatBytes(file.size)
    };
  });
  uploadProgress.value = currentUploads;

  const formData = new FormData();
  files.forEach(file => {
    formData.append('imagenes', file);
  });

  try {
    const res = await apiClient.post(`/productos/${props.producto.id}/imagenes`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 90) / progressEvent.total);
          Object.keys(uploadProgress.value).forEach(k => {
            uploadProgress.value[k].progress = Math.max(percent, 30);
          });
        }
      }
    });

    successMsg.value = `¡${files.length} imagen(es) procesada(s) y optimizada(s) con Sharp exitosamente en Supabase Storage!`;
    await loadImagenes();
    emit('updated', props.producto.id);
  } catch (err: any) {
    console.error('Error subiendo imágenes:', err);
    errorMsg.value = err.response?.data?.error || 'Error al subir y optimizar las imágenes.';
  } finally {
    isUploading.value = false;
    // Limpiar URLs de blob
    Object.values(uploadProgress.value).forEach(u => URL.revokeObjectURL(u.preview));
    uploadProgress.value = {};
  }
}

// KAN-78: Marcar como portada principal
async function setPrincipal(img: ImagenProducto) {
  if (img.es_principal || !props.producto?.id) return;
  errorMsg.value = null;
  try {
    await apiClient.patch(`/productos/${props.producto.id}/imagenes/${img.id}/principal`);
    // Actualizar estado local inmediatamente
    imagenes.value.forEach(i => {
      i.es_principal = (i.id === img.id);
    });
    successMsg.value = 'Imagen designada como portada principal del producto.';
    emit('updated', props.producto.id);
  } catch (err: any) {
    console.error('Error al cambiar portada:', err);
    errorMsg.value = err.response?.data?.error || 'No se pudo actualizar la imagen de portada.';
  }
}

// KAN-78: Confirmar y eliminar recurso
function confirmDelete(img: ImagenProducto) {
  imageToDelete.value = img;
}

async function executeDelete() {
  if (!imageToDelete.value || !props.producto?.id) return;
  isDeleting.value = true;
  errorMsg.value = null;
  try {
    await apiClient.delete(`/productos/${props.producto.id}/imagenes/${imageToDelete.value.id}`);
    successMsg.value = 'Recurso multimedia eliminado de Supabase Storage y catálogo.';
    imageToDelete.value = null;
    await loadImagenes();
    emit('updated', props.producto.id);
  } catch (err: any) {
    console.error('Error eliminando imagen:', err);
    errorMsg.value = err.response?.data?.error || 'Error al eliminar el recurso multimedia.';
  } finally {
    isDeleting.value = false;
  }
}

// KAN-77: Reordenamiento mediante drag and drop o botones de flechas
function handleDragStart(index: number) {
  draggedIndex.value = index;
}

function handleDragOverItem(e: DragEvent, index: number) {
  e.preventDefault();
  if (draggedIndex.value === null || draggedIndex.value === index) return;
  
  // Reordenar temporalmente en el cliente
  const moved = imagenes.value.splice(draggedIndex.value, 1)[0];
  imagenes.value.splice(index, 0, moved);
  draggedIndex.value = index;
}

async function handleDragEnd() {
  draggedIndex.value = null;
  await saveOrder();
}

async function moveItem(index: number, direction: 'left' | 'right') {
  const targetIndex = direction === 'left' ? index - 1 : index + 1;
  if (targetIndex < 0 || targetIndex >= imagenes.value.length) return;

  const temp = imagenes.value[index];
  imagenes.value[index] = imagenes.value[targetIndex];
  imagenes.value[targetIndex] = temp;

  await saveOrder();
}

async function saveOrder() {
  if (!props.producto?.id) return;
  isReordering.value = true;
  try {
    const ordenes = imagenes.value.map((img, idx) => ({
      id: img.id,
      orden: idx
    }));
    await apiClient.put(`/productos/${props.producto.id}/imagenes/reordenar`, { ordenes });
    successMsg.value = 'Nuevo orden de la galería guardado exitosamente.';
    emit('updated', props.producto.id);
  } catch (err: any) {
    console.error('Error guardando orden:', err);
    errorMsg.value = 'No se pudo guardar el nuevo orden de imágenes.';
  } finally {
    isReordering.value = false;
  }
}
</script>

<template>
  <div id="product-multimedia-manager" class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden flex flex-col">
    <!-- Header del Gestor de Multimedia -->
    <div class="px-6 py-5 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50/75 dark:bg-slate-950/50">
      <div class="flex items-center gap-3">
        <button
          id="btn-back-multimedia"
          @click="$emit('close')"
          class="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-slate-600 dark:text-slate-300"
          title="Regresar a lista de productos"
        >
          <ArrowLeft class="w-4 h-4" />
        </button>
        <div>
          <div class="flex items-center gap-2">
            <h2 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <ImageIcon class="w-5 h-5 text-blue-600" />
              Galería Multimedia: {{ producto.nombre }}
            </h2>
            <span class="text-xs px-2 py-0.5 rounded-md font-mono font-semibold bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
              {{ producto.sku }}
            </span>
          </div>
          <p class="text-xs text-slate-500 mt-0.5">
            RF-03: Carga, optimización WebP, generación de thumbnails y reordenamiento con Supabase Storage.
          </p>
        </div>
      </div>

      <!-- Resumen / Badges -->
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200/50 dark:border-blue-900/50">
          <Layers class="w-3.5 h-3.5" />
          {{ imagenes.length }} {{ imagenes.length === 1 ? 'imagen' : 'imágenes' }}
        </span>
        <button
          id="btn-close-studio"
          @click="$emit('close')"
          class="text-xs px-3 py-1.5 rounded-lg font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-200/60 dark:hover:bg-slate-800"
        >
          Cerrar
        </button>
      </div>
    </div>

    <!-- Contenido Principal -->
    <div class="p-6 space-y-6 flex-1 overflow-y-auto max-h-[calc(100vh-14rem)]">
      <!-- Mensajes de Alerta -->
      <div v-if="errorMsg" class="p-3.5 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50 text-rose-700 dark:text-rose-300 text-xs rounded-xl flex items-center justify-between">
        <div class="flex items-center gap-2">
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span>{{ errorMsg }}</span>
        </div>
        <button @click="errorMsg = null" class="text-rose-500 hover:text-rose-700"><X class="w-3.5 h-3.5" /></button>
      </div>

      <div v-if="successMsg" class="p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900/50 text-emerald-700 dark:text-emerald-300 text-xs rounded-xl flex items-center justify-between">
        <div class="flex items-center gap-2">
          <CheckCircle2 class="w-4 h-4 shrink-0" />
          <span>{{ successMsg }}</span>
        </div>
        <button @click="successMsg = null" class="text-emerald-500 hover:text-emerald-700"><X class="w-3.5 h-3.5" /></button>
      </div>

      <!-- KAN-77: Uploader Drag & Drop con Previsualización Inmediata -->
      <div
        id="multimedia-dropzone"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
        @click="fileInputRef?.click()"
        :class="[
          'relative border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all duration-200',
          isDraggingOver
            ? 'border-blue-500 bg-blue-50/60 dark:bg-blue-950/30 ring-4 ring-blue-500/10 scale-[1.005]'
            : 'border-slate-300 dark:border-slate-700 hover:border-blue-400 dark:hover:border-blue-600 bg-slate-50/50 dark:bg-slate-900/40'
        ]"
      >
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml"
          class="hidden"
          @change="handleFileSelect"
        />

        <div class="max-w-md mx-auto flex flex-col items-center space-y-3 pointer-events-none">
          <div class="w-14 h-14 rounded-2xl bg-gradient-to-tr from-blue-600 to-cyan-500 text-white flex items-center justify-center shadow-lg shadow-blue-500/20">
            <UploadCloud class="w-7 h-7 animate-pulse" />
          </div>
          <div class="space-y-1">
            <p class="text-sm font-bold text-slate-800 dark:text-slate-100">
              Arrastra y suelta imágenes aquí, o <span class="text-blue-600 dark:text-blue-400 underline decoration-blue-400/50 underline-offset-2">haz clic para examinar</span>
            </p>
            <p class="text-xs text-slate-500">
              Formatos soportados: PNG, JPG, WebP, SVG. Máximo 10 MB por archivo.
            </p>
          </div>
          <div class="flex items-center gap-2 text-[11px] font-medium text-slate-400 bg-white dark:bg-slate-800 px-3 py-1 rounded-full border border-slate-200 dark:border-slate-700 shadow-sm">
            <Sparkles class="w-3 h-3 text-amber-500" />
            Compresión automática WebP (85%) y Thumbnails (320px) vía Sharp + Supabase
          </div>
        </div>
      </div>

      <!-- KAN-77: Previsualización Inmediata durante subida -->
      <div v-if="isUploading && Object.keys(uploadProgress).length > 0" class="space-y-3">
        <h4 class="text-xs font-bold text-slate-600 dark:text-slate-300 flex items-center gap-2">
          <Loader2 class="w-3.5 h-3.5 animate-spin text-blue-600" />
          Subiendo y optimizando imágenes en tiempo real...
        </h4>
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          <div
            v-for="(item, key) in uploadProgress"
            :key="key"
            class="relative bg-white dark:bg-slate-800 border border-blue-300 dark:border-blue-700 rounded-xl p-3 shadow-sm flex items-center gap-3 overflow-hidden"
          >
            <img :src="item.preview" class="w-12 h-12 object-cover rounded-lg border border-slate-200 dark:border-slate-700 shrink-0" alt="Preview" />
            <div class="min-w-0 flex-1 space-y-1">
              <p class="text-xs font-semibold text-slate-800 dark:text-white truncate">{{ item.name }}</p>
              <p class="text-[11px] text-slate-400">{{ item.size }}</p>
              <!-- Barra de progreso -->
              <div class="w-full bg-slate-100 dark:bg-slate-700 h-1.5 rounded-full overflow-hidden">
                <div
                  class="bg-blue-600 h-full rounded-full transition-all duration-300"
                  :style="{ width: `${item.progress}%` }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- KAN-77 & KAN-78: Galería Interactiva con Reordenamiento y Portada -->
      <div class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <span>Galería del Producto</span>
            <span class="text-xs font-normal text-slate-500">(Arrastra las tarjetas o usa las flechas para reordenar)</span>
          </h3>

          <div v-if="isReordering" class="flex items-center gap-1.5 text-xs text-blue-600 font-semibold animate-pulse">
            <Loader2 class="w-3.5 h-3.5 animate-spin" /> Guardando orden...
          </div>
        </div>

        <!-- Estado de carga inicial -->
        <div v-if="isLoading" class="py-12 flex flex-col items-center justify-center space-y-2 text-slate-400">
          <Loader2 class="w-8 h-8 animate-spin text-blue-600" />
          <p class="text-xs">Cargando recursos multimedia...</p>
        </div>

        <!-- Galería vacía -->
        <div v-else-if="imagenes.length === 0" class="py-12 border border-slate-200 dark:border-slate-800 rounded-2xl text-center space-y-2 bg-slate-50/40 dark:bg-slate-900/20">
          <ImageIcon class="w-10 h-10 text-slate-300 mx-auto" />
          <p class="text-sm font-semibold text-slate-700 dark:text-slate-300">No hay recursos multimedia cargados</p>
          <p class="text-xs text-slate-400 max-w-sm mx-auto">
            Utiliza el recuadro superior para cargar las fotos del producto. Se optimizarán automáticamente y se almacenarán en Supabase Storage.
          </p>
        </div>

        <!-- Grid de Imágenes -->
        <div
          v-else
          class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4"
        >
          <div
            v-for="(img, index) in imagenes"
            :key="img.id"
            draggable="true"
            @dragstart="handleDragStart(index)"
            @dragover="(e) => handleDragOverItem(e, index)"
            @dragend="handleDragEnd"
            :class="[
              'group relative bg-white dark:bg-slate-800 rounded-xl border transition-all duration-200 overflow-hidden shadow-sm flex flex-col',
              img.es_principal
                ? 'border-emerald-500 ring-2 ring-emerald-500/20 shadow-emerald-500/5'
                : 'border-slate-200 dark:border-slate-700 hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-md'
            ]"
          >
            <!-- Card Image Area -->
            <div class="relative aspect-square bg-slate-100 dark:bg-slate-950 overflow-hidden flex items-center justify-center">
              <img
                :src="img.thumbnailUrl || img.url"
                :alt="`Imagen ${index + 1}`"
                class="w-full h-full object-cover object-center group-hover:scale-105 transition-transform duration-300"
                loading="lazy"
              />

              <!-- Badge de Posición / Orden -->
              <span class="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md text-[11px] font-bold bg-black/60 text-white backdrop-blur-sm shadow">
                #{{ index + 1 }}
              </span>

              <!-- Badge de Portada Principal (KAN-78) -->
              <div v-if="img.es_principal" class="absolute top-2.5 right-2.5 inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500 text-white shadow-md">
                <Star class="w-3 h-3 fill-current" /> Portada
              </div>

              <!-- Drag Handle Icon -->
              <div class="absolute bottom-2.5 left-2.5 p-1 rounded-md bg-black/50 text-white/80 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab active:cursor-grabbing">
                <GripVertical class="w-3.5 h-3.5" />
              </div>

              <!-- Botón de Maximizar / Ver Alta Resolución -->
              <button
                @click="previewImage = img"
                class="absolute bottom-2.5 right-2.5 p-1.5 rounded-lg bg-black/60 hover:bg-black/80 text-white opacity-0 group-hover:opacity-100 transition-opacity shadow"
                title="Ampliar imagen"
              >
                <Maximize2 class="w-3.5 h-3.5" />
              </button>
            </div>

            <!-- Card Controls / Metadata -->
            <div class="p-3 bg-white dark:bg-slate-800 space-y-2 flex-1 flex flex-col justify-between">
              <!-- Información de URL y fecha -->
              <div class="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                <span class="truncate max-w-[140px]" :title="img.url">
                  {{ img.url.split('/').pop() }}
                </span>
                <a :href="img.url" target="_blank" class="hover:text-blue-500 flex items-center gap-0.5" title="Abrir enlace público">
                  <ExternalLink class="w-3 h-3" />
                </a>
              </div>

              <!-- Barra de Acciones: Reordenar flechas + Portada + Eliminar -->
              <div class="pt-2 border-t border-slate-100 dark:border-slate-700/60 flex items-center justify-between gap-1">
                <!-- Flechas de reordenamiento (KAN-77) -->
                <div class="flex items-center gap-0.5">
                  <button
                    @click="moveItem(index, 'left')"
                    :disabled="index === 0"
                    class="p-1 rounded text-slate-500 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none"
                    title="Mover a la izquierda"
                  >
                    <ArrowLeft class="w-3.5 h-3.5" />
                  </button>
                  <button
                    @click="moveItem(index, 'right')"
                    :disabled="index === imagenes.length - 1"
                    class="p-1 rounded text-slate-500 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none"
                    title="Mover a la derecha"
                  >
                    <ArrowRight class="w-3.5 h-3.5" />
                  </button>
                </div>

                <!-- Botón de portada (KAN-78) -->
                <button
                  @click="setPrincipal(img)"
                  :disabled="img.es_principal"
                  :class="[
                    'text-[11px] px-2 py-1 rounded-md font-semibold transition-all flex items-center gap-1',
                    img.es_principal
                      ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 cursor-default'
                      : 'bg-slate-100 dark:bg-slate-700 hover:bg-amber-50 dark:hover:bg-amber-950/30 hover:text-amber-600 dark:hover:text-amber-400 text-slate-600 dark:text-slate-300'
                  ]"
                  :title="img.es_principal ? 'Esta es la portada actual' : 'Establecer como imagen de portada'"
                >
                  <Star :class="['w-3 h-3', img.es_principal ? 'fill-current text-emerald-500' : 'text-slate-400']" />
                  <span class="hidden sm:inline">{{ img.es_principal ? 'Principal' : 'Hacer Portada' }}</span>
                </button>

                <!-- Botón de eliminar (KAN-78) -->
                <button
                  @click="confirmDelete(img)"
                  class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded transition-colors"
                  title="Eliminar recurso multimedia"
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- MODAL: Confirmación de Eliminación (KAN-78) -->
    <div
      v-if="imageToDelete"
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-sm w-full p-6 border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4">
        <div class="flex items-center gap-3 text-rose-600">
          <div class="p-2.5 rounded-xl bg-rose-100 dark:bg-rose-950/50">
            <Trash2 class="w-5 h-5" />
          </div>
          <div>
            <h4 class="text-base font-bold text-slate-900 dark:text-white">¿Eliminar imagen?</h4>
            <p class="text-xs text-slate-500">Esta acción no se puede deshacer.</p>
          </div>
        </div>

        <div class="aspect-video w-full rounded-xl bg-slate-100 dark:bg-slate-800 overflow-hidden border border-slate-200 dark:border-slate-700">
          <img :src="imageToDelete.url" class="w-full h-full object-cover" alt="Recurso a eliminar" />
        </div>

        <p class="text-xs text-slate-600 dark:text-slate-300">
          Se eliminará permanentemente de <strong class="text-slate-900 dark:text-white">Supabase Storage</strong> y se desvinculará de la base de datos del producto.
        </p>

        <div class="flex justify-end gap-2 pt-2">
          <button
            @click="imageToDelete = null"
            :disabled="isDeleting"
            class="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            Cancelar
          </button>
          <button
            @click="executeDelete"
            :disabled="isDeleting"
            class="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white shadow-sm flex items-center gap-1.5"
          >
            <Loader2 v-if="isDeleting" class="w-3.5 h-3.5 animate-spin" />
            <span>{{ isDeleting ? 'Eliminando...' : 'Eliminar' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: Vista Previa en Alta Resolución -->
    <div
      v-if="previewImage"
      class="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4"
      @click.self="previewImage = null"
    >
      <div class="relative max-w-3xl w-full bg-slate-900 rounded-2xl overflow-hidden border border-slate-700 shadow-2xl flex flex-col max-h-[90vh]">
        <div class="p-3 border-b border-slate-800 flex justify-between items-center text-white">
          <span class="text-xs font-mono text-slate-300">{{ previewImage.url.split('/').pop() }}</span>
          <button @click="previewImage = null" class="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="p-4 flex-1 flex items-center justify-center bg-black/40 overflow-hidden">
          <img :src="previewImage.url" class="max-h-[60vh] max-w-full object-contain rounded-lg shadow-lg" alt="Vista previa completa" />
        </div>
        <div class="p-4 border-t border-slate-800 text-xs text-slate-400 flex flex-wrap justify-between gap-2 bg-slate-950">
          <div>
            <span class="font-semibold text-slate-300">URL Pública: </span>
            <a :href="previewImage.url" target="_blank" class="text-blue-400 hover:underline break-all">{{ previewImage.url }}</a>
          </div>
          <div class="flex items-center gap-2">
            <span v-if="previewImage.es_principal" class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold">
              ⭐ Portada Principal
            </span>
            <span class="text-[11px] text-slate-400">Orden: #{{ previewImage.orden + 1 }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
