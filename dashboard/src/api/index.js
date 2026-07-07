/**
 * Flask API 接口封装
 * 通过 Vite proxy 转发到 http://localhost:5000
 */

const BASE = '/api'

export async function fetchLatest() {
  const res = await fetch(`${BASE}/latest`)
  if (!res.ok) throw new Error(`/api/latest: ${res.status}`)
  return res.json()
}

export async function fetchTrend(n = 100) {
  const res = await fetch(`${BASE}/trend?n=${n}`)
  if (!res.ok) throw new Error(`/api/trend: ${res.status}`)
  return res.json()
}

export async function fetchStatistics() {
  const res = await fetch(`${BASE}/statistics`)
  if (!res.ok) throw new Error(`/api/statistics: ${res.status}`)
  return res.json()
}

export async function fetchWaveform() {
  const res = await fetch(`${BASE}/waveform`)
  if (!res.ok) throw new Error(`/api/waveform: ${res.status}`)
  return res.json()
}

export async function fetchSpectrum() {
  const res = await fetch(`${BASE}/spectrum`)
  if (!res.ok) throw new Error(`/api/spectrum: ${res.status}`)
  return res.json()
}

export async function fetchHistory(id) {
  const res = await fetch(`${BASE}/history/${id}`)
  if (!res.ok) throw new Error(`/api/history/${id}: ${res.status}`)
  return res.json()
}

export async function fetchRecords(page = 1, limit = 50, label = null) {
  let url = `${BASE}/records?page=${page}&limit=${limit}`
  if (label) url += `&label=${label}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`/api/records: ${res.status}`)
  return res.json()
}
