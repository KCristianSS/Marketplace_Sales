<script setup lang="ts">
import { computed } from 'vue';
import { useAuthStore } from '@/stores/auth';
import type { UserProfile } from '@/types';

type Role = UserProfile['role'];

const props = withDefaults(defineProps<{
  role?: Role;
  roles?: Role[];
}>(), {
  roles: () => []
});

const authStore = useAuthStore();

const allowedRoles = computed(() => {
  const roles = [...props.roles];
  if (props.role) roles.push(props.role);
  return new Set(roles);
});

const hasPermission = computed(() => allowedRoles.value.has(authStore.userRole));
</script>

<template>
  <slot v-if="hasPermission" />
  <slot v-else name="fallback" />
</template>
