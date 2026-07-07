<template>
  <div class="status-gauge">
    <h3 class="panel-title">🔍 健康状态监测</h3>
    <div class="gauge-body" v-if="data">
      <!-- 状态指示灯 -->
      <div class="status-light" :class="statusClass">
        <div class="light-ring"></div>
        <div class="light-core"></div>
      </div>

      <!-- 状态文字 -->
      <div class="status-info">
        <div class="status-label">{{ faultName }}</div>
        <div class="status-detail" :class="{ danger: !data.correct }">
          {{ data.correct ? '✅ 诊断正确' : '❌ 诊断错误' }}
        </div>
      </div>

      <!-- 置信度仪表 -->
      <div class="confidence-bar">
        <div class="conf-label">置信度</div>
        <div class="conf-track">
          <div class="conf-fill" :style="{ width: confPercent + '%' }"
               :class="confLevel"></div>
        </div>
        <div class="conf-value">{{ confPercent }}%</div>
      </div>

      <!-- 元信息 -->
      <div class="meta-row">
        <div class="meta-item">
          <span class="meta-key">数据文件</span>
          <span class="meta-val">{{ data.file_name }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">运行转速</span>
          <span class="meta-val">{{ data.speed }} Hz</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">真实标签</span>
          <span class="meta-val">{{ data.true_label }}</span>
        </div>
      </div>
    </div>
    <div class="no-data" v-else>等待数据...</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ data: Object })

const faultName = computed(() => props.data?.label_name || '--')
const confPercent = computed(() =>
  props.data ? Math.round(props.data.confidence * 100) : 0
)

const statusClass = computed(() => {
  if (!props.data) return ''
  if (!props.data.correct) return 'danger'
  if (props.data.predicted_label === 'H') return 'healthy'
  return 'fault'
})

const confLevel = computed(() => {
  const p = confPercent.value
  if (p >= 90) return 'high'
  if (p >= 70) return 'mid'
  return 'low'
})
</script>

<style scoped>
.status-gauge { padding: 12px 20px; height: 100%; display: flex; flex-direction: column; }
.panel-title { font-size: 15px; color: #7eb8da; margin-bottom: 10px; font-weight: 600; }

.gauge-body { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 12px; }

/* 状态指示灯 */
.status-light { position: relative; width: 80px; height: 80px; }
.light-ring {
  width: 80px; height: 80px; border-radius: 50%;
  border: 4px solid #1a3a5c; position: absolute;
  animation: pulse 2s infinite;
}
.light-core {
  width: 40px; height: 40px; border-radius: 50%;
  position: absolute; top: 20px; left: 20px;
  transition: all 0.5s;
}
.healthy .light-ring { border-color: #00e676; box-shadow: 0 0 30px rgba(0,230,118,0.4); }
.healthy .light-core { background: #00e676; box-shadow: 0 0 20px rgba(0,230,118,0.6); }
.fault .light-ring   { border-color: #ff9100; box-shadow: 0 0 30px rgba(255,145,0,0.4); }
.fault .light-core   { background: #ff9100; box-shadow: 0 0 20px rgba(255,145,0,0.6); }
.danger .light-ring  { border-color: #ff1744; box-shadow: 0 0 30px rgba(255,23,68,0.4); }
.danger .light-core  { background: #ff1744; box-shadow: 0 0 20px rgba(255,23,68,0.6); }

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.08); opacity: 0.7; }
}

.status-label { font-size: 24px; font-weight: 700; color: #e0e6f0; }
.status-detail { font-size: 13px; }
.status-detail.danger { color: #ff5252; }

/* 置信度条 */
.confidence-bar { width: 100%; display: flex; align-items: center; gap: 10px; }
.conf-label { font-size: 12px; color: #5a7a9a; width: 45px; }
.conf-track { flex: 1; height: 10px; background: #1a2a40; border-radius: 5px; overflow: hidden; }
.conf-fill { height: 100%; border-radius: 5px; transition: width 0.8s ease; }
.conf-fill.high { background: linear-gradient(90deg, #00e676, #69f0ae); }
.conf-fill.mid  { background: linear-gradient(90deg, #ff9100, #ffab40); }
.conf-fill.low  { background: linear-gradient(90deg, #ff1744, #ff5252); }
.conf-value { font-size: 14px; font-weight: 700; color: #e0e6f0; width: 40px; text-align: right; }

/* 元信息 */
.meta-row { width: 100%; display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.meta-item { display: flex; justify-content: space-between; font-size: 12px; }
.meta-key { color: #5a7a9a; }
.meta-val { color: #a0b8d0; }

.no-data { display: flex; align-items: center; justify-content: center; height: 200px; color: #3a5a7a; font-size: 14px; }
</style>
