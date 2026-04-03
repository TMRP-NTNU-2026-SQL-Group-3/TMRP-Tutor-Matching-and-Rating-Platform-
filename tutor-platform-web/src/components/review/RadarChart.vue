<template>
  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
    <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">{{ title }}</h3>
    <div class="flex justify-center">
      <div style="max-width: 320px; width: 100%;">
        <Radar :data="chartData" :options="chartOptions" />
      </div>
    </div>
    <p v-if="reviewCount" class="text-center text-xs text-gray-400 mt-2">共 {{ reviewCount }} 則評價</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Radar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from 'chart.js'

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip)

const props = defineProps({
  title: { type: String, default: '評分雷達圖' },
  labels: { type: Array, default: () => ['教學能力', '溝通態度', '準時出席', '整體滿意度'] },
  values: { type: Array, default: () => [0, 0, 0, 0] },
  reviewCount: { type: Number, default: 0 },
})

const chartData = computed(() => ({
  labels: props.labels,
  datasets: [
    {
      label: '平均評分',
      data: props.values,
      backgroundColor: 'rgba(59, 130, 246, 0.15)',
      borderColor: 'rgba(59, 130, 246, 0.8)',
      pointBackgroundColor: 'rgba(59, 130, 246, 1)',
      pointBorderColor: '#fff',
      pointRadius: 4,
      borderWidth: 2,
    },
  ],
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: true,
  scales: {
    r: {
      min: 0,
      max: 5,
      ticks: { stepSize: 1, display: false },
      pointLabels: { font: { size: 12 }, color: '#6b7280' },
      grid: { color: 'rgba(0, 0, 0, 0.06)' },
      angleLines: { color: 'rgba(0, 0, 0, 0.06)' },
    },
  },
  plugins: {
    tooltip: {
      callbacks: {
        label: (ctx) => `${ctx.label}：${ctx.raw.toFixed(1)}`,
      },
    },
  },
}
</script>
