/**
 * API client composable — fetches data from the FastAPI backend.
 * Handles base URL, polling, and error states.
 */

import { ref, onMounted, onUnmounted, type Ref } from 'vue'

const API_BASE = '/api/v1'

/**
 * Generic fetch wrapper with error handling.
 */
async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, v)
      }
    })
  }

  const response = await fetch(url.toString())
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface NodeData {
  id: string
  name: string
  latitude: number
  longitude: number
  node_type: string
  warning_threshold: number
  alert_threshold: number
  current_water_level: number | null
  status: 'normal' | 'warning' | 'alert'
}

export interface WaterLevelReading {
  timestamp: string
  seconds: number | null
  water_level: number
}

export interface ForecastData {
  node_id: string
  node_name: string
  latitude: number
  longitude: number
  warning_threshold: number
  alert_threshold: number
  readings: WaterLevelReading[]
  total_readings: number
}

export interface AlertData {
  alert_definition_id: string
  onset_time: string | null
  end_time: string | null
  priority: string | null
  target_id: string | null
  target_type: string | null
  category: string | null
  peak_value: number | null
  peak_value_units: string | null
  peak_time: string | null
  is_active: boolean
}

export interface AlertListData {
  alerts: AlertData[]
  total_active: number
}

export interface DashboardSummaryData {
  total_nodes: number
  active_alerts: number
  latest_update: string | null
  max_water_level: number | null
  max_water_level_node: string | null
  nodes_in_warning: number
  nodes_in_alert: number
}

export interface GeoJSONFeatureProperties {
  Zone?: string
  Depth?: number
  depth?: number
  Elevation?: number
  elevation?: number
  MaxDepth?: number
  Hazard?: string
  Timestep?: string
  timestep?: string
  timestep_label?: string
  [key: string]: any
}

export interface ContourGeoJSON {
  type: string
  features: Array<{
    type: string
    geometry: any
    properties: GeoJSONFeatureProperties
  }>
}

// ─── API Functions ──────────────────────────────────────────────────────────

export async function fetchNodes(): Promise<NodeData[]> {
  return apiFetch<NodeData[]>(`${API_BASE}/nodes`)
}

export async function fetchNodeForecast(nodeId: string): Promise<ForecastData> {
  return apiFetch<ForecastData>(`${API_BASE}/node-forecast`, { node_id: nodeId })
}

export async function fetchActiveAlerts(): Promise<AlertListData> {
  return apiFetch<AlertListData>(`${API_BASE}/alerts/active`)
}

export async function fetchDashboardSummary(): Promise<DashboardSummaryData> {
  return apiFetch<DashboardSummaryData>(`${API_BASE}/dashboard/summary`)
}

export async function fetchContourTimesteps(): Promise<string[]> {
  return apiFetch<string[]>(`${API_BASE}/contours/timesteps`)
}

export async function fetchContourGeoJSON(timestamp: string): Promise<ContourGeoJSON> {
  return apiFetch<ContourGeoJSON>(`${API_BASE}/contours/${timestamp}`)
}

export async function checkHasMaxima(): Promise<{ available: boolean; timestep: string | null; filename: string | null }> {
  return apiFetch<{ available: boolean; timestep: string | null; filename: string | null }>(`${API_BASE}/contours/has-maxima`)
}

// ─── Polling Composable ─────────────────────────────────────────────────────

export function usePolling<T>(
  fetchFn: () => Promise<T>,
  intervalMs: number = 60000
) {
  const data: Ref<T | null> = ref(null)
  const loading = ref(true)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  async function refresh() {
    try {
      error.value = null
      data.value = await fetchFn()
    } catch (e: any) {
      error.value = e.message || 'Unknown error'
      console.error('Polling error:', e)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    refresh()
    timer = setInterval(refresh, intervalMs)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  return { data, loading, error, refresh }
}
