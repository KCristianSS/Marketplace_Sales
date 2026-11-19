<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Toaster } from 'vue-sonner';
import { AlertTriangle, CircleHelp, X } from 'lucide-vue-next';
import { activeConfirmation, cancelConfirmations, settleConfirmation } from '@/lib/feedback';

const route = useRoute();
const dialog = ref<HTMLDialogElement | null>(null);
const cancelButton = ref<HTMLButtonElement | null>(null);

function answer(accepted: boolean) {
  if (activeConfirmation.value) settleConfirmation(accepted, activeConfirmation.value.id);
}

watch(activeConfirmation, async request => {
  if (dialog.value?.open) dialog.value.close();
  if (!request) return;
  await nextTick();
  if (activeConfirmation.value?.id !== request.id) return;
  dialog.value?.showModal();
  cancelButton.value?.focus();
});
watch(() => route.fullPath, cancelConfirmations);
onBeforeUnmount(cancelConfirmations);
</script>

<template>
  <Toaster
    position="top-right"
    rich-colors
    close-button
    :duration="5500"
    :visible-toasts="3"
    :offset="80"
    :mobile-offset="16"
    theme="light"
    container-aria-label="Notificaciones"
    :toast-options="{ closeButtonAriaLabel: 'Cerrar notificación', style: { fontFamily: 'inherit', borderRadius: '14px' } }"
  />
  <Teleport to="body">
    <dialog
      ref="dialog"
      aria-modal="true"
      aria-labelledby="confirmation-title"
      aria-describedby="confirmation-description"
      class="app-confirmation m-auto w-[calc(100%_-_2rem)] max-w-md rounded-2xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl"
      @cancel.prevent="answer(false)"
      @click.self="answer(false)"
    >
      <div v-if="activeConfirmation" class="p-6 sm:p-7">
        <div class="flex items-start justify-between gap-4">
          <div :class="['flex h-11 w-11 items-center justify-center rounded-xl', activeConfirmation.danger ? 'bg-rose-50 text-rose-600' : 'bg-blue-50 text-blue-600']">
            <component :is="activeConfirmation.danger ? AlertTriangle : CircleHelp" class="h-6 w-6" />
          </div>
          <button type="button" aria-label="Cerrar confirmación" class="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-blue-600" @click="answer(false)"><X class="h-5 w-5" /></button>
        </div>
        <h2 id="confirmation-title" class="mt-4 text-lg font-bold">{{ activeConfirmation.title }}</h2>
        <p id="confirmation-description" class="mt-2 whitespace-pre-line text-sm leading-6 text-slate-600">{{ activeConfirmation.message }}</p>
        <div class="mt-6 flex flex-wrap justify-end gap-2">
          <button ref="cancelButton" type="button" autofocus class="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold hover:bg-slate-50 focus-visible:outline-blue-600" @click="answer(false)">{{ activeConfirmation.cancelLabel }}</button>
          <button type="button" :class="['rounded-xl px-4 py-2.5 text-sm font-semibold text-white focus-visible:outline-offset-2', activeConfirmation.danger ? 'bg-rose-600 hover:bg-rose-700 focus-visible:outline-rose-600' : 'bg-blue-600 hover:bg-blue-700 focus-visible:outline-blue-600']" @click="answer(true)">{{ activeConfirmation.confirmLabel }}</button>
        </div>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.app-confirmation::backdrop { background: rgb(15 23 42 / 55%); backdrop-filter: blur(3px); }
</style>
