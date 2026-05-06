<template>
  <div>
    <PageHeader title="收入統計" />

    <div class="flex items-center gap-3 mb-6 flex-wrap">
      <label class="text-sm font-medium text-gray-700">選擇月份：</label>
      <input type="month" v-model="month" :max="maxMonth" @change="fetchData"
        class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
      <button @click="printPage" type="button"
        class="ml-auto text-sm text-gray-500 hover:text-gray-700 transition-colors print:hidden">
        列印
      </button>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="data">
      <!-- Stat cards -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <StatCard title="總堂數" :value="data.session_count" />
        <StatCard title="總時數" :value="data.total_hours" />
        <StatCard title="總收入" highlight>
          NT$ {{ (data.total_income ?? 0).toLocaleString() }}
        </StatCard>
      </div>

      <!-- Income chart -->
      <IncomeChart v-if="data.breakdown.length" :breakdown="data.breakdown" class="mb-6" />

      <!-- Breakdown table -->
      <div v-if="data.breakdown.length" class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200">
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">學生姓名</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">科目</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">時數</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">收入 (TWD)</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="row in data.breakdown" :key="`${row.student_name}\u0001${row.subject_name}`" class="hover:bg-gray-50 transition-colors">
              <td class="px-4 py-3 text-sm text-gray-900">{{ row.student_name }}</td>
              <td class="px-4 py-3 text-sm text-gray-700">{{ row.subject_name }}</td>
              <td class="px-4 py-3 text-sm text-gray-700 text-right">{{ row.hours }}</td>
              <td class="px-4 py-3 text-sm text-gray-900 font-semibold text-right">NT$ {{ (row.income ?? 0).toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-else message="本月無上課紀錄" />
    </div>

    <p v-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3 mt-4">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { statsApi } from '@/api/stats'
import PageHeader from '@/components/common/PageHeader.vue'
import StatCard from '@/components/common/StatCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import IncomeChart from '@/components/stats/IncomeChart.vue'

const now = new Date()
const maxMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
const month = ref(maxMonth)
const data = ref(null)
const loading = ref(false)
const error = ref('')

let _fetchSeq = 0
async function fetchData() {
  const seq = ++_fetchSeq
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const result = await statsApi.getIncome({ month: month.value })
    if (seq !== _fetchSeq) return
    data.value = result
  } catch (e) {
    if (seq === _fetchSeq) error.value = e.message
  } finally {
    if (seq === _fetchSeq) loading.value = false
  }
}

function printPage() { window.print() }

onMounted(fetchData)
</script>
