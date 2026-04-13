<template>
  <div class="mb-6">
    <div class="flex items-center gap-3">
      <button v-if="showBack" type="button" @click="handleBack"
        class="inline-flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
        aria-label="返回上一頁">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5" aria-hidden="true">
          <path fill-rule="evenodd" d="M12.79 5.23a.75.75 0 0 1 0 1.06L9.06 10l3.73 3.71a.75.75 0 1 1-1.06 1.06l-4.25-4.24a.75.75 0 0 1 0-1.06l4.25-4.24a.75.75 0 0 1 1.06 0Z" clip-rule="evenodd" />
        </svg>
      </button>
      <h1 class="text-2xl font-bold text-gray-900">{{ title }}</h1>
    </div>
    <p v-if="subtitle" class="text-gray-500 mt-1">{{ subtitle }}</p>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  showBack: { type: Boolean, default: false },
  // Optional router-link target; when absent we fall back to history.back().
  // Explicit target lets callers pin the destination even if the user
  // landed on this page via a deep link with no history entry to pop.
  backTo: { type: [String, Object], default: null },
})

const router = useRouter()

function handleBack() {
  if (props.backTo) {
    router.push(props.backTo)
  } else if (typeof window !== 'undefined' && window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>
