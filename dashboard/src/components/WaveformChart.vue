<template>
  <div class="waveform-chart">
    <h3 class="panel-title">📊 实时振动波形</h3>
    <div ref="chartRef" class="chart-box"></div>
    <div class="no-data" v-if="!hasData">等待数据...</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: Object })
const chartRef = ref(null)
let chart = null

const hasData = ref(false)

function initChart() {
  chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['X轴', 'Y轴', 'Z轴', 'Sound'],
      bottom: 0, textStyle: { color: '#7eb8da', fontSize: 10 },
    },
    grid: { top: 10, right: 15, bottom: 30, left: 45 },
    xAxis: {
      type: 'category', data: [],
      axisLine: { lineStyle: { color: '#1a3a5c' } },
      axisLabel: { color: '#5a7a9a', fontSize: 9,
        formatter: v => (v % 200 === 0 ? v : '') },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#1a2a40' } },
      axisLabel: { color: '#5a7a9a', fontSize: 9 },
    },
    series: [
      { name: 'X轴', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1, color: '#00e5ff' }, symbol: 'none' },
      { name: 'Y轴', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1, color: '#ff6d00' }, symbol: 'none' },
      { name: 'Z轴', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1, color: '#76ff03' }, symbol: 'none' },
      { name: 'Sound', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1, color: '#e040fb' }, symbol: 'none' },
    ],
  })
}

function updateChart(data) {
  if (!chart || !data) return
  hasData.value = true
  const idx = Array.from({ length: 1024 }, (_, i) => i)
  chart.setOption({
    xAxis: { data: idx },
    series: [
      { data: data.x },
      { data: data.y },
      { data: data.z },
      { data: data.sound },
    ],
  })
}

watch(() => props.data, (val) => {
  if (!chart && chartRef.value) { initChart() }
  updateChart(val)
}, { deep: true })

onMounted(() => {
  if (props.data) { initChart(); updateChart(props.data) }
})
onUnmounted(() => { chart?.dispose() })

const resizeHandler = () => chart?.resize()
onMounted(() => window.addEventListener('resize', resizeHandler))
onUnmounted(() => window.removeEventListener('resize', resizeHandler))
</script>

<style scoped>
.waveform-chart { padding: 10px 16px; height: 100%; position: relative; }
.panel-title { font-size: 15px; color: #7eb8da; margin-bottom: 4px; font-weight: 600; }
.chart-box { width: 100%; height: calc(100% - 30px); }
.no-data {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  color: #3a5a7a; font-size: 14px; pointer-events: none;
}
</style>
