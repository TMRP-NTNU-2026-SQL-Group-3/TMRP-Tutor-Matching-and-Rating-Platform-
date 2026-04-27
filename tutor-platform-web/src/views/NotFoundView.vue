<template>
  <div class="min-h-[60vh] flex items-center justify-center">
    <div class="text-center space-y-4">
      <p class="text-7xl font-bold text-gray-200">404</p>
      <h1 class="text-xl font-semibold text-gray-700">找不到這個頁面</h1>
      <p class="text-sm text-gray-500">您所尋找的網址不存在或已移除。</p>
      <router-link to="/"
        class="inline-block mt-2 px-5 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors hover:no-underline">
        回首頁
      </router-link>
    </div>
  </div>
</template>
