<template>
  <nav class="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="flex items-center justify-between h-14">
        <!-- Logo -->
        <router-link to="/" class="text-xl font-bold text-primary-600 shrink-0 hover:no-underline">
          TMRP
        </router-link>

        <!-- Desktop nav links -->
        <div class="hidden md:flex items-center gap-1">
          <router-link v-for="link in navLinks" :key="link.to" :to="link.to"
            class="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 hover:text-primary-600 hover:bg-primary-50 transition-colors hover:no-underline"
            active-class="!text-primary-600 !bg-primary-50 font-semibold">
            {{ link.label }}
          </router-link>
        </div>

        <!-- Right side: user + logout -->
        <div class="hidden md:flex items-center gap-3">
          <span class="text-sm text-gray-600">{{ auth.user?.display_name }}</span>
          <button @click="$emit('logout')"
            class="px-3 py-1.5 text-sm font-medium text-gray-500 hover:text-danger bg-transparent hover:bg-red-50 rounded-lg transition-colors">
            登出
          </button>
        </div>

        <!-- Mobile hamburger -->
        <button @click="mobileOpen = !mobileOpen" class="md:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 bg-transparent">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path v-if="!mobileOpen" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
            <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <!-- Mobile menu -->
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 -translate-y-1"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-1">
        <div v-if="mobileOpen" class="md:hidden pb-3 border-t border-gray-100 mt-1">
          <div class="pt-2 space-y-1">
            <router-link v-for="link in navLinks" :key="link.to" :to="link.to"
              class="block px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:text-primary-600 hover:bg-primary-50 transition-colors hover:no-underline"
              active-class="!text-primary-600 !bg-primary-50"
              @click="mobileOpen = false">
              {{ link.label }}
            </router-link>
          </div>
          <div class="mt-3 pt-3 border-t border-gray-100 px-3 flex items-center justify-between">
            <span class="text-sm text-gray-600">{{ auth.user?.display_name }}</span>
            <button @click="$emit('logout')"
              class="px-3 py-1.5 text-sm font-medium text-danger hover:bg-red-50 rounded-lg bg-transparent transition-colors">
              登出
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </nav>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  auth: {
    type: Object,
    required: true,
    // 預期：{ role: string, user: { display_name: string } }
  },
})

defineEmits(['logout'])

const mobileOpen = ref(false)

const navLinks = computed(() => {
  const role = props.auth.role
  if (role === 'parent') {
    return [
      { to: '/parent', label: '首頁' },
      { to: '/parent/search', label: '搜尋老師' },
      { to: '/parent/students', label: '管理子女' },
      { to: '/parent/expense', label: '支出統計' },
      { to: '/messages', label: '訊息' },
    ]
  }
  if (role === 'tutor') {
    return [
      { to: '/tutor', label: '首頁' },
      { to: '/tutor/profile', label: '個人檔案' },
      { to: '/tutor/income', label: '收入統計' },
      { to: '/messages', label: '訊息' },
    ]
  }
  if (role === 'admin') {
    return [{ to: '/admin', label: '管理後台' }]
  }
  return []
})
</script>
