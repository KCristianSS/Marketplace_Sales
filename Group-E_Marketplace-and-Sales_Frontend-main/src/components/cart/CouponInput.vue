<script setup lang="ts">
import { ref } from 'vue';
import { Tag, X, Loader2, CheckCircle2, AlertCircle } from 'lucide-vue-next';
import { useCartStore } from '@/stores/cart';

/**
 * RF-17 [FE]: input interactivo de cupón con feedback inmediato de ahorro.
 * La validación (vigencia, monto mínimo, límite de canjes) la hace el backend;
 * este componente solo muestra el resultado y el ahorro calculado.
 */
const cartStore = useCartStore();
const codigo = ref('');
const validando = ref(false);
const feedback = ref<{ texto: string; ok: boolean } | null>(null);

async function aplicar() {
  if (validando.value || !codigo.value.trim()) return;
  validando.value = true;
  feedback.value = null;
  try {
    const res = await cartStore.aplicarCupon(codigo.value);
    feedback.value = { texto: res.mensaje, ok: res.ok };
    if (res.ok) codigo.value = '';
  } finally {
    validando.value = false;
  }
}

function quitar() {
  cartStore.removerCupon();
  feedback.value = null;
}
</script>

<template>
  <div class="space-y-1.5" data-testid="coupon-input">
    <!-- Cupón aplicado -->
    <div
      v-if="cartStore.cupon"
      class="flex items-center justify-between gap-2 p-2 rounded-xl border text-xs"
      :class="cartStore.descuento > 0
        ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800'
        : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800'"
    >
      <span
        class="flex items-center gap-1.5 font-bold"
        :class="cartStore.descuento > 0 ? 'text-emerald-800 dark:text-emerald-300' : 'text-amber-800 dark:text-amber-300'"
      >
        <Tag class="w-3.5 h-3.5 shrink-0" />
        <span>
          Cupón {{ cartStore.cupon }}
          <template v-if="cartStore.descuento > 0">· ahorras Bs. {{ cartStore.descuento.toFixed(2) }}</template>
          <template v-else>· pendiente</template>
        </span>
      </span>
      <button type="button" @click="quitar" class="text-slate-400 hover:text-rose-600 p-0.5 rounded" title="Quitar cupón">
        <X class="w-3.5 h-3.5" />
      </button>
    </div>
    <p v-if="cartStore.cuponAdvertencia" class="flex items-start gap-1 text-[11px] font-medium text-amber-700 dark:text-amber-400">
      <AlertCircle class="w-3 h-3 mt-0.5 shrink-0" /> {{ cartStore.cuponAdvertencia }}
    </p>

    <!-- Entrada de código -->
    <div v-if="!cartStore.cupon" class="space-y-1">
      <div class="flex gap-2">
        <input
          v-model="codigo"
          @keydown.enter.prevent="aplicar"
          type="text"
          maxlength="50"
          placeholder="Código de cupón"
          :disabled="validando"
          class="flex-1 min-w-0 px-3 py-1.5 text-xs uppercase font-mono bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60"
        />
        <button
          type="button"
          @click="aplicar"
          :disabled="validando || !codigo.trim()"
          class="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-bold bg-slate-900 hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          <Loader2 v-if="validando" class="w-3 h-3 animate-spin" />
          Aplicar
        </button>
      </div>
    </div>

    <p
      v-if="feedback"
      class="flex items-start gap-1 text-[11px] font-semibold"
      :class="feedback.ok ? 'text-emerald-600' : 'text-rose-500'"
      role="status"
    >
      <CheckCircle2 v-if="feedback.ok" class="w-3 h-3 mt-0.5 shrink-0" />
      <AlertCircle v-else class="w-3 h-3 mt-0.5 shrink-0" />
      {{ feedback.texto }}
    </p>
  </div>
</template>
