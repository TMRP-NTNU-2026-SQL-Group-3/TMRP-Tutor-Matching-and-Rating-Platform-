<template>
  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
    <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">收入分佈</h3>
    <Bar v-if="chartData.labels.length" :data="chartData" :options="chartOptions" />
    <p v-else class="text-gray-400 text-sm text-center py-4">無資料</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const props = defineProps({
  breakdown: { type: Array, default: () => [] },
})

const chartData = computed(() => ({
  labels: props.breakdown.map(r => `${r.student_name} - ${r.subject_name}`),
  datasets: [
    {
      label: '收入 (NT$)',
      data: props.breakdown.map(r => r.income),
      backgroundColor: 'rgba(59, 130, 246, 0.6)',
      borderColor: 'rgba(59, 130, 246, 1)',
      borderWidth: 1,
      borderRadius: 4,
    },
  ],
}))

const chartOptions = {
  responsive: true,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx) => `NT$ ${ctx.raw.toLocaleString()}`,
      },
    },
  },
  scales: {
    y: {
      beginAtZero: true,
      ticks: { callback: (v) => `$${v.toLocaleString()}` },
    },
  },
}
</script>
