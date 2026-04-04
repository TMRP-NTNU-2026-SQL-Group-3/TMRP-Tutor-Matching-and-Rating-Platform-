<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none" style="max-width: 380px">
      <TransitionGroup
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0 translate-x-8"
        enter-to-class="opacity-100 translate-x-0"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100 translate-x-0"
        leave-to-class="opacity-0 translate-x-8"
        move-class="transition duration-200 ease-in-out">
        <div v-for="toast in store.toasts" :key="toast.id"
             :class="[
               'pointer-events-auto flex items-start gap-3 rounded-lg px-4 py-3 shadow-lg border text-sm',
               colorMap[toast.type]
             ]">
          <span class="text-base leading-none mt-0.5">{{ iconMap[toast.type] }}</span>
          <span class="flex-1">{{ toast.message }}</span>
          <button @click="store.remove(toast.id)"
                  class="text-current opacity-50 hover:opacity-100 transition-opacity ml-2 shrink-0">
            ✕
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToastStore } from '@/stores/toast'

const store = useToastStore()

const colorMap = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
}

const iconMap = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
}
</script>
