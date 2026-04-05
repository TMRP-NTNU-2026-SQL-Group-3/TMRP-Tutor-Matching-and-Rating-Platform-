<template>
  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
    <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">成績趨勢</h3>
    <Line v-if="chartData.labels.length" :data="chartData" :options="chartOptions" />
    <p v-else class="text-gray-400 text-sm text-center py-4">無考試紀錄</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const props = defineProps({
  exams: { type: Array, default: () => [] },
})

const COLORS = [
  { bg: 'rgba(59, 130, 246, 0.15)', border: 'rgba(59, 130, 246, 1)' },
  { bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 1)' },
  { bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 1)' },
  { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 1)' },
  { bg: 'rgba(139, 92, 246, 0.15)', border: 'rgba(139, 92, 246, 1)' },
]

const chartData = computed(() => {
  // 依科目分群
  const grouped = {}
  for (const e of props.exams) {
    const key = e.subject_name
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(e)
  }

  const subjects = Object.keys(grouped)

  // 取得所有不重複日期作為 x 軸，並按時間排序
  const allDates = [...new Set(props.exams.map(e => {
    const d = new Date(e.exam_date)
    return d.toLocaleDateString('zh-TW')
  }))].sort((a, b) => new Date(a) - new Date(b))

  const datasets = subjects.map((subj, i) => {
    const color = COLORS[i % COLORS.length]
    const dataMap = {}
    for (const e of grouped[subj]) {
      const label = new Date(e.exam_date).toLocaleDateString('zh-TW')
      if (!dataMap[label]) dataMap[label] = []
      dataMap[label].push(e.score)
    }
    return {
      label: subj,
      data: allDates.map(d => {
        const arr = dataMap[d]
        return arr ? arr.reduce((a, b) => a + b, 0) / arr.length : null
      }),
      borderColor: color.border,
      backgroundColor: color.bg,
      tension: 0.3,
      spanGaps: true,
      pointRadius: 5,
      pointHoverRadius: 7,
    }
  })

  return { labels: allDates, datasets }
})

const chartOptions = {
  responsive: true,
  plugins: {
    legend: { position: 'bottom' },
    tooltip: {
      callbacks: {
        label: (ctx) => ctx.raw != null ? `${ctx.dataset.label}：${ctx.raw} 分` : null,
      },
    },
  },
  scales: {
    y: {
      beginAtZero: true,
      max: 100,
      title: { display: true, text: '分數' },
    },
  },
}
</script>
