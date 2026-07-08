<template>
  <div class="history-playback">
    <h3 class="panel-title">
      <History :size="16" class="panel-title-icon" /> 历史回放
      <span class="record-count" v-if="total">共 {{ total }} 条</span>
    </h3>

    <!-- 回放控制栏 -->
    <div class="playback-controls">
      <button @click="goFirst" title="最早"><ChevronsLeft :size="14" /></button>
      <button @click="goPrev" title="上一条"><ChevronLeft :size="14" /></button>
      <span class="record-info" v-if="current">
        #{{ current.id }} / {{ total }} &nbsp; {{ current.label_name }}
        <span :class="current.correct ? 'ok' : 'err'">
          <Check v-if="current.correct" :size="12" />
          <X v-else :size="12" />
        </span>
      </span>
      <span class="record-info" v-else>点击列表加载记录</span>
      <button @click="goNext" title="下一条"><ChevronRight :size="14" /></button>
      <button @click="goLast" title="最新"><ChevronsRight :size="14" /></button>
      <label class="auto-btn" :class="{ active: autoPlay }">
        <input type="checkbox" v-model="autoPlay" /> 自动
      </label>
    </div>

    <!-- 主区域：记录列表 + 详情 -->
    <div class="playback-body">
      <!-- 左侧：记录列表 -->
      <div class="record-list" ref="listRef">
        <div v-for="r in records" :key="r.id"
          class="record-item"
          :class="{ selected: current && current.id === r.id, wrong: !r.correct }"
          @click="loadRecord(r.id)">
          <span class="rec-id">#{{ r.id }}</span>
          <span class="rec-label">{{ r.label_name }}</span>
          <span class="rec-conf">{{ (r.confidence * 100).toFixed(0) }}%</span>
          <span class="rec-file">{{ r.file_name }}</span>
        </div>
      </div>

      <!-- 右侧：选中记录波形 -->
      <div class="playback-detail">
        <div ref="waveRef" class="mini-wave"></div>
        <div class="detail-meta" v-if="current">
          <div class="meta-line"><b>文件:</b> {{ current.file_name }}</div>
          <div class="meta-line"><b>转速:</b> {{ current.speed }} Hz &nbsp; <b>真实:</b> {{ current.true_label }} &nbsp; <b>预测:</b> {{ current.predicted_label }}</div>
          <div class="meta-line"><b>置信度:</b> {{ (current.confidence * 100).toFixed(1) }}% &nbsp;&nbsp; <b>X RMS:</b> {{ current.x_rms?.toFixed(3) }} &nbsp; <b>Y RMS:</b> {{ current.y_rms?.toFixed(3) }} &nbsp; <b>Z RMS:</b> {{ current.z_rms?.toFixed(3) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { fetchHistory, fetchRecords } from '../api/index.js'
import { History, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, Check, X } from 'lucide-vue-next'

const records = ref([])
const current = ref(null)
const total = ref(0)
const autoPlay = ref(false)
const page = ref(1)
const waveRef = ref(null)
const listRef = ref(null)
let waveChart = null
let autoTimer = null

async function refreshList() {
  try {
    const res = await fetchRecords(page.value, 50)
    records.value = res.records
    total.value = res.total
  } catch (e) { console.warn('[history] 加载列表失败:', e.message) }
}

async function loadRecord(id) {
  try {
    const data = await fetchHistory(id)
    current.value = data
    await nextTick()
    renderMiniWave(data)
  } catch (e) { console.warn('[history] 加载记录失败:', e.message) }
}

function renderMiniWave(data) {
  if (!waveRef.value) return
  if (!waveChart) {
    waveChart = echarts.init(waveRef.value)
  }
  const xData = Array.from({ length: data.x.length }, (_, i) => i)
  waveChart.setOption({
    grid: { top: 5, right: 8, bottom: 25, left: 40 },
    xAxis: { type: 'category', data: xData, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#1a3a5c' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a2a40' } }, axisLabel: { color: '#5a7a9a', fontSize: 8 } },
    tooltip: { trigger: 'axis' },
    series: [
      { name: 'X', type: 'line', data: data.x, smooth: true, lineStyle: { width: 1, color: '#00e5ff' }, symbol: 'none' },
      { name: 'Y', type: 'line', data: data.y, smooth: true, lineStyle: { width: 1, color: '#ff6d00' }, symbol: 'none' },
      { name: 'Z', type: 'line', data: data.z, smooth: true, lineStyle: { width: 1, color: '#76ff03' }, symbol: 'none' },
      { name: 'Sound', type: 'line', data: data.sound, smooth: true, lineStyle: { width: 1, color: '#e040fb' }, symbol: 'none' },
    ],
  })
}

function goNext() {
  const idx = records.value.findIndex(r => r.id === current.value?.id)
  if (idx > 0) loadRecord(records.value[idx - 1].id)
  else if (records.value.length > 0) loadRecord(records.value[0].id)
}

function goPrev() {
  const idx = records.value.findIndex(r => r.id === current.value?.id)
  if (idx >= 0 && idx < records.value.length - 1) loadRecord(records.value[idx + 1].id)
}

function goFirst() {
  if (records.value.length > 0) loadRecord(records.value[records.value.length - 1].id)
}

function goLast() {
  if (records.value.length > 0) loadRecord(records.value[0].id)
}

// 自动播放
watch(autoPlay, (on) => {
  if (on) {
    autoTimer = setInterval(goNext, 1500)
  } else {
    clearInterval(autoTimer)
  }
})

onMounted(async () => {
  await refreshList()
  if (records.value.length > 0) loadRecord(records.value[0].id)
})
onUnmounted(() => {
  waveChart?.dispose()
  clearInterval(autoTimer)
})

const resizeHandler = () => {
  waveChart?.resize()
  if (listRef.value) {
    listRef.value.style.maxHeight = (listRef.value.parentElement.clientHeight - 40) + 'px'
  }
}
onMounted(() => window.addEventListener('resize', resizeHandler))
onUnmounted(() => window.removeEventListener('resize', resizeHandler))
</script>

<style scoped>
.history-playback { padding: 10px 16px; height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.panel-title { font-size: 15px; color: #7eb8da; margin-bottom: 4px; font-weight: 600; }
.record-count { font-size: 11px; color: #5a7a9a; font-weight: 400; margin-left: 8px; }

.playback-controls { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.playback-controls button {
  background: rgba(10,20,50,0.6); border: 1px solid #1a3a5c; color: #7eb8da;
  padding: 2px 8px; border-radius: 3px; font-size: 13px; cursor: pointer;
}
.playback-controls button:hover { border-color: #00b8ff; color: #00b8ff; }
.record-info { font-size: 12px; color: #a0b8d0; min-width: 160px; }
.record-info .ok { color: #00e676; }
.record-info .err { color: #ff5252; }
.auto-btn { font-size: 11px; color: #5a7a9a; cursor: pointer; display: flex; align-items: center; gap: 3px; }
.auto-btn.active { color: #00b8ff; }

.playback-body { flex: 1; display: flex; gap: 8px; overflow: hidden; }
.record-list { width: 230px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.record-list::-webkit-scrollbar { width: 4px; }
.record-list::-webkit-scrollbar-thumb { background: #1a3a5c; border-radius: 2px; }

.record-item { display: flex; gap: 6px; padding: 3px 6px; font-size: 11px; cursor: pointer;
  border: 1px solid transparent; border-radius: 3px; color: #7a8fa8; }
.record-item:hover { background: rgba(0,180,255,0.08); border-color: rgba(0,180,255,0.2); }
.record-item.selected { background: rgba(0,180,255,0.12); border-color: #00b8ff; color: #dce6f2; }
.record-item.wrong { border-left: 2px solid #ff5252; }
.rec-id { width: 36px; color: #5a7a9a; flex-shrink: 0; }
.rec-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rec-conf { color: #7eb8da; width: 32px; text-align: right; flex-shrink: 0; }
.rec-file { color: #5a7a9a; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80px; }

.playback-detail { flex: 1; display: flex; flex-direction: column; gap: 4px; overflow: hidden; }
.mini-wave { flex: 1; min-height: 0; }
.detail-meta { font-size: 11px; color: #5a7a9a; }
.meta-line { margin-bottom: 2px; }
.meta-line b { color: #7eb8da; }
</style>
