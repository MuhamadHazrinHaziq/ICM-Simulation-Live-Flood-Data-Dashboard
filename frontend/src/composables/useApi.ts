/**
 * API client composable — fetches data from the FastAPI backend.
 * Handles base URL, polling, and error states.
 */

import { ref, onMounted, onUnmounted, type Ref } from 'vue'

const API_BASE = '/api/v1'

// ─── Fallback Demo Data for Static Deployment (GitHub Pages) ─────────────────

const FALLBACK_NODES: NodeData[] = [
  {
    id: 'Drain_46',
    name: 'Drain 46 - Sungai Padungan',
    latitude: 1.5535,
    longitude: 110.3485,
    node_type: '2D_Inundation',
    warning_threshold: 2.0,
    alert_threshold: 3.0,
    current_water_level: 2.78,
    status: 'warning'
  },
  {
    id: 'Drain_102',
    name: 'Drain 102 - Sungai Sarawak',
    latitude: 1.5601,
    longitude: 110.3422,
    node_type: '1D_Channel',
    warning_threshold: 2.2,
    alert_threshold: 3.2,
    current_water_level: 1.85,
    status: 'normal'
  }
]

const FALLBACK_SUMMARY: DashboardSummaryData = {
  total_nodes: 2,
  active_alerts: 0,
  latest_update: '01 Sept 2026, 07:09',
  max_water_level: 2.78,
  max_water_level_node: 'Drain_46',
  nodes_in_warning: 1,
  nodes_in_alert: 0
}

function getFallbackForecast(nodeId: string): ForecastData {
  const isDrain46 = nodeId === 'Drain_46'
  const times = ['09:30', '10:30', '11:30', '12:30', '13:30', '14:30', '15:30', '16:30', '17:30']
  const readings: WaterLevelReading[] = times.map((t, idx) => {
    const baseLevel = isDrain46 ? 1.35 : 1.15
    const peak = isDrain46 ? 1.43 : 0.8
    const val = baseLevel + Math.sin((idx / (times.length - 1)) * Math.PI) * peak
    return {
      timestamp: `2026-09-01T${t}:00`,
      seconds: idx * 3600,
      water_level: parseFloat(val.toFixed(2))
    }
  })
  return {
    node_id: nodeId,
    node_name: isDrain46 ? 'Drain 46 - Sungai Padungan' : 'Drain 102 - Sungai Sarawak',
    latitude: isDrain46 ? 1.5535 : 1.5601,
    longitude: isDrain46 ? 110.3485 : 110.3422,
    warning_threshold: isDrain46 ? 2.0 : 2.2,
    alert_threshold: isDrain46 ? 3.0 : 3.2,
    readings,
    total_readings: readings.length
  }
}

const FALLBACK_TIMESTEPS = ['0930', '1030', '1130', '1230', '1330', '1430', '1530', '1630', '1730']

const FALLBACK_GEOJSON: ContourGeoJSON = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [110.342, 1.558],
            [110.347, 1.556],
            [110.352, 1.553],
            [110.350, 1.550],
            [110.344, 1.552],
            [110.340, 1.555],
            [110.342, 1.558]
          ]
        ]
      },
      properties: {
        Zone: 'Padungan Inundation Zone',
        Depth: 0.84,
        depth: 0.84,
        Elevation: 3.25,
        elevation: 3.25,
        Hazard: 'MEDIUM',
        timestep_label: '13:30'
      }
    }
  ]
}

function getFallbackData(path: string, params?: Record<string, string>): any {
  if (path.includes('/nodes')) return FALLBACK_NODES
  if (path.includes('/node-forecast')) {
    const id = params?.node_id || 'Drain_46'
    return getFallbackForecast(id)
  }
  if (path.includes('/alerts/active')) return { alerts: [], total_active: 0 }
  if (path.includes('/dashboard/summary')) return FALLBACK_SUMMARY
  if (path.includes('/contours/timesteps')) return FALLBACK_TIMESTEPS
  if (path.includes('/contours/has-maxima')) return { available: true, timestep: 'maxima', filename: 'FloodContours_260826_maxima.shp' }
  if (path.includes('/contours/')) return FALLBACK_GEOJSON
  return undefined
}

/**
 * Generic fetch wrapper with error handling and static demo fallback.
 */
async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const configuredApiBase = (import.meta.env.VITE_API_URL as string | undefined) || ''

  let targetUrl: string
  if (configuredApiBase && configuredApiBase.startsWith('http')) {
    const cleanPath = path.startsWith('/api/v1') ? path.replace('/api/v1', '') : path
    const url = new URL(configuredApiBase.replace(/\/$/, '') + '/api/v1' + cleanPath)
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') {
          url.searchParams.set(k, v)
        }
      })
    }
    targetUrl = url.toString()
  } else {
    const url = new URL(path, window.location.origin)
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') {
          url.searchParams.set(k, v)
        }
      })
    }
    targetUrl = url.toString()
  }

  try {
    const response = await fetch(targetUrl)
    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`)
    }
    return await response.json()
  } catch (err) {
    const fallback = getFallbackData(path, params)
    if (fallback !== undefined) {
      return fallback as T
    }
    throw err
  }
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
