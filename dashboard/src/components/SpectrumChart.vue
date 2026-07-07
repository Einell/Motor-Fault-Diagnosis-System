<template>
  <div class="spectrum-chart">
    <h3 class="panel-title">📈 实时频谱分析 (FFT)</h3>
    <div class="channel-tabs" v-if="hasData">
      <button v-for="ch in channels" :key="ch.key"
        :class="{ active: activeCh === ch.key }"
        @click="switchChannel(ch.key)">{{ ch.label }}</button>
    </div>
    <div ref="chartRef" class="chart-box"></div>
    <div class="no-data" v-if="!hasData">等待数据...</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: Object })
const chartRef = ref(null)
let chart = null
const hasData = ref(false)
const activeCh = ref('x')
let lastSpeed = 0

const channels = [
  { key: 'x', label: 'X轴', color: '#00e5ff' },
  { key: 'y', label: 'Y轴', color: '#ff6d00' },
  { key: 'z', label: 'Z轴', color: '#76ff03' },
  { key: 'sound', label: 'Sound', color: '#e040fb' },
]

function pickSpectrum(data, channel) {
  const ch = channel || activeCh.value
  if (data[ch] && data[ch].freqs && data[ch].freqs.length > 0) return data[ch]
  if (data.freqs && data.freqs.length > 0) return { freqs: data.freqs, amps: data.amps }
  return null
}

function buildMarkLines(speed) {
  if (!speed || speed <= 0) return []
  return [
    { h: 1, label: '1×fr', color: '#ff9100' },
    { h: 2, label: '2×fr', color: '#ff1744' },
    { h: 3, label: '3×fr', color: '#e040fb' },
  ].map(({ h, label, color }) => ({
    silent: true, symbol: 'none',
    lineStyle: { type: 'dashed', color, width: 1.2, opacity: 0.7 },
    label: { show: true, formatter: label, color, fontSize: 10,
              position: 'end', distance: 3 },
    data: [{ xAxis: speed * h }],
  }))
}

// 按通道颜色生成 areaStyle 渐变（hex → rgba 转换）
function makeAreaGradient(hexColor) {
  const r = parseInt(hexColor.slice(1, 3), 16)
  const g = parseInt(hexColor.slice(3, 5), 16)
  const b = parseInt(hexColor.slice(5, 7), 16)
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: `rgba(${r},${g},${b},0.25)` },
    { offset: 1, color: `rgba(${r},${g},${b},0.02)` },
  ])
}

// 构建完整 ECharts option，用于 notMerge 模式避免合并问题
function buildFullOption(data, chKey) {
  const ch = channels.find(c => c.key === chKey) || channels[0]
  const sp = data ? pickSpectrum(data, chKey) : null
  const pts = (sp && sp.freqs && sp.freqs.length > 0)
    ? sp.freqs.map((f, i) => [f, sp.amps[i] || 0])
    : []
  const speed = (data && data.speed) ? data.speed : lastSpeed

  const option = {
    tooltip: {
      trigger: 'axis',
      formatter: p => `频率: ${p[0].data[0].toFixed(1)} Hz<br>幅值: ${p[0].data[1].toFixed(2)}`,
    },
    grid: { top: 10, right: 15, bottom: 25, left: 45 },
    xAxis: {
      type: 'value', name: 'Hz',
      nameTextStyle: { color: '#5a7a9a', fontSize: 9 },
      axisLine: { lineStyle: { color: '#1a3a5c' } },
      axisLabel: { color: '#5a7a9a', fontSize: 9 },
      splitLine: { lineStyle: { color: '#1a2a40' } },
      max: 500,
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#1a2a40' } },
      axisLabel: { color: '#5a7a9a', fontSize: 9 },
    },
    series: [{
      type: 'line', data: pts, smooth: false,
      lineStyle: { width: 1.5, color: ch.color },
      areaStyle: { color: makeAreaGradient(ch.color) },
      symbol: 'none',
      markLine: (speed > 0 && pts.length > 0) ? {
        silent: false, symbol: ['none', 'none'],
        data: buildMarkLines(speed),
      } : undefined,
    }],
  }
  return option
}

function ensureChart() {
  if (chart) return true
  if (!chartRef.value) return false
  chart = echarts.init(chartRef.value)
  chart.setOption(buildFullOption(null, activeCh.value))
  return true
}

function refreshChart(data) {
  if (!data) return
  if (!ensureChart()) return

  lastSpeed = data.speed || lastSpeed

  const sp = pickSpectrum(data)
  if (!sp || !sp.freqs || sp.freqs.length === 0) {
    // 无数据通道 → 清空曲线，保留坐标轴
    chart.setOption(buildFullOption(null, activeCh.value), true)
    return
  }

  hasData.value = true
  // 关键：使用 notMerge: true，每次完整替换 option，避免 ECharts 合并 bug
  chart.setOption(buildFullOption(data, activeCh.value), true)
}

function switchChannel(key) {
  activeCh.value = key
  if (props.data) refreshChart(props.data)
}

watch(() => props.data, async (val) => {
  await nextTick()
  refreshChart(val)
}, { deep: true })

onMounted(async () => {
  await nextTick()
  if (props.data) refreshChart(props.data)
})

onUnmounted(() => { chart?.dispose(); chart = null })

const rh = () => chart?.resize()
onMounted(() => window.addEventListener('resize', rh))
onUnmounted(() => window.removeEventListener('resize', rh))
</script>

<style scoped>
.spectrum-chart { padding: 10px 16px; height: 100%; position: relative; display: flex; flex-direction: column; }
.panel-title { font-size: 15px; color: #7eb8da; margin-bottom: 4px; font-weight: 600; }
.chart-box { flex: 1; width: 100%; }
.channel-tabs { display: flex; gap: 4px; margin-bottom: 4px; }
.channel-tabs button {
  background: rgba(10,20,50,0.6); border: 1px solid #1a3a5c;
  color: #5a7a9a; padding: 2px 10px; border-radius: 3px;
  font-size: 11px; cursor: pointer; transition: all 0.2s;
}
.channel-tabs button.active { border-color: #00b8ff; color: #00b8ff; background: rgba(0,184,255,0.1); }
.channel-tabs button:hover { border-color: #00b8ff; }
.no-data { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); color: #3a5a7a; font-size: 14px; pointer-events: none; }
</style>
