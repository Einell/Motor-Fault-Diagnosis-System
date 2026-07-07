<template>
  <div class="dashboard" :class="{ 'alert-active': faultAlert }">
    <!-- 顶部标题栏 -->
    <header class="header">
      <div class="header-line left"></div>
      <h1>⚙️ 电机智能故障诊断系统 — 实时监控大屏</h1>
      <div class="header-line right"></div>
    </header>

    <!-- 告警横幅 -->
    <div class="alert-banner" v-if="faultAlert">
      <span class="alert-icon">⚠️</span>
      <span class="alert-text">故障告警：检测到 {{ latest?.label_name }} &nbsp; 置信度 {{ (latest?.confidence * 100).toFixed(0) }}%</span>
      <button class="alert-dismiss" @click="dismissAlert">静音</button>
    </div>

    <!-- 主体区域 -->
    <main class="main-grid">
      <!-- 左上：健康状态仪表盘 -->
      <div class="border-panel panel-status" :class="{ 'panel-danger': faultAlert }">
        <StatusGauge :data="latest" />
      </div>

      <!-- 右上：故障统计饼图 -->
      <div class="border-panel panel-pie">
        <FaultPie :data="statistics" />
      </div>

      <!-- 中左：实时波形图 -->
      <div class="border-panel panel-wave">
        <WaveformChart :data="waveform" />
      </div>

      <!-- 中右：实时频谱图 -->
      <div class="border-panel panel-spectrum">
        <SpectrumChart :data="spectrum" />
      </div>

      <!-- 下左：RMS 趋势图 -->
      <div class="border-panel panel-trend">
        <RmsTrend :data="trend" />
      </div>

      <!-- 下右：历史回放 -->
      <div class="border-panel panel-history">
        <HistoryPlayback />
      </div>
    </main>

    <!-- 底部信息条 -->
    <footer class="footer">
      <span>📡 HUSTmotor 多模态电机故障数据集</span>
      <span>|</span>
      <span>🔗 MQTT Broker: localhost:1883</span>
      <span>|</span>
      <span>🧠 模型: Random Forest (准确率 98.43%)</span>
      <span>|</span>
      <span>🕐 {{ timeStr }}</span>
      <span>|</span>
      <span :class="apiOk ? 'api-ok' : 'api-err'">
        {{ apiOk ? '✅ API 在线' : '⏳ API 等待...' }}
      </span>
      <span>|</span>
      <span class="alert-status" :class="{ muted: alertMuted }">
        {{ alertMuted ? '🔕 告警已静音' : '🔔 告警开启' }}
      </span>
    </footer>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import {
  fetchLatest, fetchTrend, fetchStatistics, fetchWaveform, fetchSpectrum,
} from './api/index.js'
import StatusGauge from './components/StatusGauge.vue'
import WaveformChart from './components/WaveformChart.vue'
import SpectrumChart from './components/SpectrumChart.vue'
import RmsTrend from './components/RmsTrend.vue'
import FaultPie from './components/FaultPie.vue'
import HistoryPlayback from './components/HistoryPlayback.vue'

const latest = ref(null)
const trend = ref(null)
const statistics = ref(null)
const waveform = ref(null)
const spectrum = ref(null)
const timeStr = ref('')
const apiOk = ref(false)

// 告警状态
const faultAlert = ref(false)
const alertMuted = ref(false)
let lastFaultId = null  // 避免同一故障重复弹窗

function dismissAlert() {
  alertMuted.value = true
  faultAlert.value = false
}

// 监听最新诊断结果，发现故障时触发告警
watch(latest, (val) => {
  if (!val || alertMuted.value) return
  if (val.predicted_label !== 'H' && val.correct !== false) {
    faultAlert.value = true
    // 同一故障不重复弹浏览器通知
    const faultKey = `${val.predicted_label}_${val.file_name}`
    if (faultKey !== lastFaultId && window.Notification && Notification.permission === 'granted') {
      lastFaultId = faultKey
      try {
        new Notification('⚠️ 电机故障告警', {
          body: `检测到 ${val.label_name}，置信度 ${(val.confidence * 100).toFixed(0)}%`,
          icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">⚠️</text></svg>',
        })
      } catch (e) { /* 浏览器不支持 */ }
    }
  } else if (val.predicted_label === 'H') {
    faultAlert.value = false
    lastFaultId = null
  }
})

let timers = []

function startPolling() {
  // 请求浏览器通知权限
  if (window.Notification && Notification.permission === 'default') {
    Notification.requestPermission()
  }

  const fetchLatest_ = async () => {
    try { latest.value = await fetchLatest(); apiOk.value = true }
    catch (e) { console.warn('[fetch] latest 失败:', e.message) }
  }
  const fetchWaveform_ = async () => {
    try { waveform.value = await fetchWaveform() } catch (e) {}
  }
  const fetchSpectrum_ = async () => {
    try { spectrum.value = await fetchSpectrum() } catch (e) {}
  }
  const fetchTrend_ = async () => {
    try { trend.value = await fetchTrend(100) } catch (e) {}
  }
  const fetchStats_ = async () => {
    try { statistics.value = await fetchStatistics() } catch (e) {}
  }

  fetchLatest_(); fetchWaveform_(); fetchSpectrum_(); fetchTrend_(); fetchStats_()

  const t1  = setInterval(fetchLatest_,    1000)
  const t1b = setInterval(fetchWaveform_,  1000)
  const t1c = setInterval(fetchSpectrum_,  1000)
  const t3  = setInterval(fetchTrend_,     3000)
  const t5  = setInterval(fetchStats_,     5000)

  const tClock = setInterval(() => {
    timeStr.value = new Date().toLocaleTimeString('zh-CN')
  }, 1000)

  timers = [t1, t1b, t1c, t3, t5, tClock]
}

onMounted(startPolling)
onUnmounted(() => timers.forEach(clearInterval))
</script>

<style>
:root {
  --bg-primary: #080e24;
  --bg-panel: rgba(6, 16, 40, 0.85);
  --border-color: rgba(0, 180, 255, 0.25);
  --border-glow: rgba(0, 180, 255, 0.12);
  --text-primary: #dce6f2;
  --text-secondary: #7a8fa8;
  --accent: #00b8ff;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', sans-serif;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}

.dashboard {
  width: 100vw;
  min-height: 100vh;
  background:
    radial-gradient(ellipse at 25% 0%, rgba(0, 140, 255, 0.06) 0%, transparent 55%),
    radial-gradient(ellipse at 75% 100%, rgba(0, 200, 255, 0.04) 0%, transparent 55%),
    var(--bg-primary);
  padding: 12px 20px 8px;
}

/* 告警横幅 */
.alert-banner {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  background: linear-gradient(90deg, rgba(255,23,68,0.2), rgba(255,23,68,0.35), rgba(255,23,68,0.2));
  border: 1px solid rgba(255,23,68,0.5); border-radius: 4px;
  padding: 6px 20px; margin-bottom: 8px;
  animation: alertPulse 2s infinite;
}
.alert-icon { font-size: 18px; }
.alert-text { font-size: 14px; color: #ff8a80; font-weight: 600; }
.alert-dismiss {
  background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);
  color: #ccc; padding: 2px 12px; border-radius: 3px; cursor: pointer; font-size: 12px;
}
.alert-dismiss:hover { background: rgba(255,255,255,0.2); }
@keyframes alertPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* 顶部标题栏 */
.header {
  display: flex; align-items: center; justify-content: center; gap: 20px;
  margin-bottom: 12px; padding: 10px 0;
}
.header h1 {
  font-size: 28px; font-weight: 700; letter-spacing: 5px;
  background: linear-gradient(90deg, #00c8ff, #0078ff, #00c8ff);
  background-size: 200% 100%;
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  animation: titleShine 4s ease-in-out infinite;
}
@keyframes titleShine {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
.header-line { flex: 1; height: 1px; background: linear-gradient(90deg, transparent, var(--border-color), transparent); }
.header-line.right { background: linear-gradient(270deg, transparent, var(--border-color), transparent); }

/* DataV 风格边框面板 */
.border-panel {
  position: relative; background: var(--bg-panel);
  border: 1px solid var(--border-color); overflow: hidden;
}
.border-panel::before, .border-panel::after {
  content: ''; position: absolute; width: 16px; height: 16px; z-index: 1; pointer-events: none;
}
.border-panel::before { top: 1px; left: 1px; border-top: 2px solid var(--accent); border-left: 2px solid var(--accent); }
.border-panel::after  { bottom: 1px; right: 1px; border-bottom: 2px solid var(--accent); border-right: 2px solid var(--accent); }
.border-panel:hover { border-color: rgba(0, 200, 255, 0.45); }

/* 面板告警闪烁 */
.panel-danger { animation: dangerBorder 1s infinite; }
@keyframes dangerBorder {
  0%, 100% { border-color: var(--border-color); }
  50% { border-color: rgba(255,23,68,0.7); box-shadow: 0 0 15px rgba(255,23,68,0.3); }
}

/* 网格布局 */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 280px 280px 260px;
  gap: 12px;
  height: calc(100vh - 150px);
}
.panel-status  { grid-row: 1; grid-column: 1; }
.panel-pie     { grid-row: 1; grid-column: 2; }
.panel-wave    { grid-row: 2; grid-column: 1; }
.panel-spectrum{ grid-row: 2; grid-column: 2; }
.panel-trend   { grid-row: 3; grid-column: 1; }
.panel-history { grid-row: 3; grid-column: 2; }

/* 故障告警时面板变红 */
.dashboard.alert-active .panel-status .border-panel { border-color: rgba(255,23,68,0.5); }

/* 底部信息条 */
.footer {
  display: flex; justify-content: center; gap: 18px;
  padding: 8px 0 4px; font-size: 11px; color: var(--text-secondary);
}
.api-ok { color: #4caf50; }
.api-err { color: #ff9800; animation: blink 1.2s infinite; }
.alert-status { color: #7eb8da; }
.alert-status.muted { color: #5a5a5a; }
@keyframes blink { 50% { opacity: 0.4; } }
</style>
