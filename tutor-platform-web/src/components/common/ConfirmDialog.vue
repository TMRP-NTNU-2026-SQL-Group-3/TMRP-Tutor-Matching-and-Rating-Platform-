<template>
  <Teleport to="body">
    <Transition name="confirm-fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center p-4"
           role="dialog" aria-modal="true" :aria-labelledby="TITLE_ID"
           @keydown.escape.window="cancel">
        <div class="absolute inset-0 bg-black/40" @click="cancel" />
        <div class="relative bg-white rounded-xl shadow-xl max-w-sm w-full p-6 space-y-4">
          <h3 :id="TITLE_ID" class="text-base font-semibold text-gray-900">{{ options.title }}</h3>
          <p v-if="options.message" class="text-sm text-gray-600">{{ options.message }}</p>
          <div class="flex gap-3 justify-end">
            <button @click="cancel" autofocus
              class="px-4 py-2 text-sm rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors">
              取消
            </button>
            <button @click="accept"
              :class="options.destructive
                ? 'bg-red-600 hover:bg-red-700 focus-visible:ring-red-500'
                : 'bg-primary-600 hover:bg-primary-700 focus-visible:ring-primary-500'"
              class="px-4 py-2 text-sm rounded-lg text-white font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2">
              {{ options.confirmLabel }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { confirmDialogState } from '@/composables/useConfirm'

const TITLE_ID = 'confirm-dialog-title'
const { visible, options, accept, cancel } = confirmDialogState
</script>

<style scoped>
.confirm-fade-enter-active,
.confirm-fade-leave-active { transition: opacity 0.15s ease; }
.confirm-fade-enter-from,
.confirm-fade-leave-to { opacity: 0; }
</style>
