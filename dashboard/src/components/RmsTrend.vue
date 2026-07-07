<template>
  <div class="rms-trend">
    <h3 class="panel-title">📉 RMS 振动趋势 (最近100条)</h3>
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
      data: ['X RMS', 'Y RMS', 'Z RMS', 'Sound RMS'],
      bottom: 0, textStyle: { color: '#7eb8da', fontSize: 10 },
    },
    grid: { top: 10, right: 15, bottom: 30, left: 45 },
    xAxis: {
      type: 'category', data: [],
      axisLabel: { color: '#5a7a9a', fontSize: 9, show: false },
      axisLine: { lineStyle: { color: '#1a3a5c' } },
    },
    yAxis: {
      type: 'value', name: 'RMS',
      nameTextStyle: { color: '#5a7a9a', fontSize: 9 },
      splitLine: { lineStyle: { color: '#1a2a40' } },
      axisLabel: { color: '#5a7a9a', fontSize: 9 },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      { name: 'X RMS', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1.5, color: '#00e5ff' }, symbol: 'none' },
      { name: 'Y RMS', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1.5, color: '#ff6d00' }, symbol: 'none' },
      { name: 'Z RMS', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1.5, color: '#76ff03' }, symbol: 'none' },
      { name: 'Sound RMS', type: 'line', data: [], smooth: true,
        lineStyle: { width: 1.5, color: '#e040fb' }, symbol: 'none' },
    ],
  })
}

function updateChart(data) {
  if (!chart || !data) return
  hasData.value = true
  const idx = Array.from({ length: data.timestamps.length }, (_, i) => i)
  chart.setOption({
    xAxis: { data: idx },
    series: [
      { data: data.x_rms },
      { data: data.y_rms },
      { data: data.z_rms },
      { data: data.sound_rms },
    ],
  })
}

watch(() => props.data, (val) => {
  if (!chart && chartRef.value) { initChart() }
  updateChart(val)
}, { deep: true })
onMounted(() => { if (props.data) { initChart(); updateChart(props.data) } })
onUnmounted(() => { chart?.dispose() })

const rh = () => chart?.resize()
onMounted(() => window.addEventListener('resize', rh))
onUnmounted(() => window.removeEventListener('resize', rh))
</script>

<style scoped>
.rms-trend { padding: 10px 16px; height: 100%; position: relative; }
.panel-title { font-size: 15px; color: #7eb8da; margin-bottom: 4px; font-weight: 600; }
.chart-box { width: 100%; height: calc(100% - 30px); }
.no-data {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  color: #3a5a7a; font-size: 14px; pointer-events: none;
}
</style>
