<template>
  <div class="fault-pie">
    <h3 class="panel-title"><PieChart :size="16" class="panel-title-icon" /> 故障诊断统计</h3>
    <div class="pie-body" v-if="data">
      <div ref="chartRef" class="pie-chart"></div>
      <div class="pie-stats">
        <div class="stat-big">
          <span class="stat-num">{{ accPercent }}%</span>
          <span class="stat-label">诊断准确率</span>
        </div>
        <div class="stat-small">
          <span>总诊断次数: <b>{{ data.total }}</b></span>
        </div>
        <div class="stat-list">
          <div v-for="d in data.distribution" :key="d.label" class="stat-row">
            <span class="dot" :style="{ background: colorMap[d.label] }"></span>
            <span class="s-name">{{ d.name }}</span>
            <span class="s-count">{{ d.count }}</span>
            <span class="s-ratio">{{ (d.ratio * 100).toFixed(1) }}%</span>
          </div>
        </div>
      </div>
    </div>
    <div class="no-data" v-else>等待数据...</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { PieChart } from 'lucide-vue-next'

const props = defineProps({ data: Object })
const chartRef = ref(null)
let chart = null

const colorMap = {
  BF: '#ff6d00', BOW: '#00e5ff', BR: '#76ff03',
  H: '#00e676', MIS: '#e040fb', UV: '#ff1744',
}

const accPercent = computed(() =>
  props.data ? (props.data.accuracy * 100).toFixed(1) : '--'
)

function initChart() {
  chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['55%', '78%'],
      center: ['50%', '52%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 3, borderColor: '#0a0e27', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: [],
    }],
  })
}

function updateChart(data) {
  if (!chart || !data) return
  const pieData = data.distribution
    .filter(d => d.count > 0)
    .map(d => ({ name: d.label, value: d.count, itemStyle: { color: colorMap[d.label] } }))
  chart.setOption({ series: [{ data: pieData }] })
}

watch(() => props.data, (val) => {
  if (!chart && chartRef.value) { initChart() }
  updateChart(val)
}, { deep: true })

onMounted(() => {
  if (props.data) { initChart(); updateChart(props.data) }
})
onUnmounted(() => { chart?.dispose() })

const rh = () => chart?.resize()
onMounted(() => window.addEventListener('resize', rh))
onUnmounted(() => window.removeEventListener('resize', rh))
</script>

<style scoped>
.fault-pie { padding: 12px 20px; height: 100%; display: flex; flex-direction: column; }
.panel-title { font-size: 15px; color: #7eb8da; margin-bottom: 6px; font-weight: 600; }

.pie-body { flex: 1; display: flex; gap: 8px; }
.pie-chart { flex: 1; min-width: 0; }
.pie-stats { width: 170px; display: flex; flex-direction: column; justify-content: center; gap: 6px; }

.stat-big { text-align: center; }
.stat-num { font-size: 32px; font-weight: 800; color: #00e676; }
.stat-label { display: block; font-size: 11px; color: #5a7a9a; }
.stat-small { text-align: center; font-size: 11px; color: #5a7a9a; }

.stat-list { display: flex; flex-direction: column; gap: 3px; }
.stat-row { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.s-name { flex: 1; color: #a0b8d0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s-count { color: #7eb8da; min-width: 30px; text-align: right; }
.s-ratio { color: #5a7a9a; min-width: 40px; text-align: right; }

.no-data { display: flex; align-items: center; justify-content: center; height: 200px; color: #3a5a7a; font-size: 14px; }
</style>
