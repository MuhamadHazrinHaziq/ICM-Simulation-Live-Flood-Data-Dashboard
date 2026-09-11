<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  fetchContourTimesteps,
  fetchContourGeoJSON,
  checkHasMaxima,
  type NodeData,
  type ContourGeoJSON,
} from '@/composables/useApi'

const props = defineProps<{ nodes: NodeData[] }>()
const emit = defineEmits<{ (e: 'select-node', nodeId: string): void }>()

const mapEl = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let markers: L.LayerGroup | null = null
let inundationLayer: L.GeoJSON | null = null
let hasFittedContours = false

const COLORS: Record<string, string> = { normal: '#34c471', warning: '#e6a020', alert: '#e04848' }

// ─── Simulation Time-Lapse & Layer State ──────────────────────────────────────
const timesteps = ref<string[]>([])
const currentIndex = ref<number>(0)
const isPlaying = ref<boolean>(false)
const isLoadingLayer = ref<boolean>(false)
const showInundation = ref<boolean>(true)
const hasMaxima = ref<boolean>(false)
const isMaximaActive = ref<boolean>(false)
const maximaTimestepKey = ref<string>('Maxima')
let playTimer: ReturnType<typeof setInterval> | null = null

// In-memory cache for seamless frame scrubbing without network lag
const geoJsonCache = new Map<string, ContourGeoJSON>()

const currentTimestep = computed(() => timesteps.value[currentIndex.value] || '')

const currentFormattedTime = computed(() => {
  const ts = currentTimestep.value
  if (!ts) return '—'
  if (ts.length === 4 && /^\d{4}$/.test(ts)) {
    return `${ts.slice(0, 2)}:${ts.slice(2)}`
  }
  return ts
})

// ─── Node Markers ────────────────────────────────────────────────────────────

function icon(status: string): L.DivIcon {
  const c = COLORS[status] || COLORS.normal
  const ring = status !== 'normal'
  return L.divIcon({
    className: '',
    html: `<span style="display:block;width:14px;height:14px;border-radius:50%;background:${c};border:2px solid ${c}40;${ring ? `box-shadow:0 0 0 4px ${c}22;animation:blink 2s ease-in-out infinite` : ''}"></span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -12],
  })
}

function nodePopup(n: NodeData): string {
  const level = n.current_water_level !== null ? `${n.current_water_level.toFixed(3)} m` : '—'
  const statusTag = `<span style="display:inline-flex;align-items:center;gap:4px;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;
    background:${n.status === 'alert' ? 'rgba(224,72,72,.12)' : n.status === 'warning' ? 'rgba(230,160,32,.12)' : 'rgba(52,196,113,.12)'};
    color:${COLORS[n.status]}">
    <span style="width:6px;height:6px;border-radius:50%;background:${COLORS[n.status]}"></span>${n.status}
  </span>`

  return `<div style="padding:14px 16px;font-family:Inter,sans-serif;min-width:210px;">
    <div style="font-weight:600;font-size:13px;color:#e2e4ea;margin-bottom:6px">${n.name}</div>
    <div style="margin-bottom:10px">${statusTag}</div>
    <table style="font-size:12px;color:#8b8fa3;line-height:1.8;border-collapse:collapse">
      <tr><td style="padding-right:12px;color:#5c6178">Level</td><td style="font-family:'JetBrains Mono',monospace;color:#e2e4ea;font-weight:500">${level}</td></tr>
      <tr><td style="padding-right:12px;color:#5c6178">Warn</td><td style="font-family:'JetBrains Mono',monospace">${n.warning_threshold} m</td></tr>
      <tr><td style="padding-right:12px;color:#5c6178">Alert</td><td style="font-family:'JetBrains Mono',monospace">${n.alert_threshold} m</td></tr>
      <tr><td style="padding-right:12px;color:#5c6178">Coords</td><td style="font-family:'JetBrains Mono',monospace;font-size:11px">${n.latitude.toFixed(4)}, ${n.longitude.toFixed(4)}</td></tr>
    </table>
    <button onclick="window.__pickNode('${n.id}')" style="margin-top:10px;width:100%;padding:7px;background:#4a7cff;border:none;border-radius:6px;color:white;font-weight:600;font-size:12px;cursor:pointer;font-family:Inter,sans-serif">View Hydrograph</button>
  </div>`
}

// ─── 2D Flood Inundation Contour Styling & Popups ────────────────────────────

function contourStyle(feature: any) {
  const depth = feature?.properties?.depth ?? feature?.properties?.Depth ?? 0.5

  // Depth-graded colors: shallow (cyan) -> moderate (blue) -> deep (dark blue)
  let fillColor = '#0284c7'
  let fillOpacity = 0.55
  if (depth < 0.5) {
    fillColor = '#38bdf8'
    fillOpacity = 0.45
  } else if (depth >= 1.2) {
    fillColor = '#1d4ed8'
    fillOpacity = 0.70
  }

  return {
    color: '#38bdf8',
    weight: 1,
    fillColor,
    fillOpacity,
  }
}

function onEachContourFeature(feature: any, layer: L.Layer) {
  const p = feature.properties || {}
  const depth = p.depth ?? p.Depth ?? '—'
  const elev = p.elevation ?? p.Elevation ?? '—'
  const zone = p.Zone || 'Flood Inundation Polygon'
  const ts = p.timestep_label || p.timestep || p.Timestep || ''
  const hazard = p.Hazard || (typeof depth === 'number' && depth > 1.2 ? 'HIGH' : typeof depth === 'number' && depth > 0.5 ? 'MEDIUM' : 'LOW')

  const hazardColor = hazard === 'HIGH' ? '#e04848' : hazard === 'MEDIUM' ? '#e6a020' : '#38bdf8'

  const popupHtml = `
    <div style="padding:12px 14px;font-family:Inter,sans-serif;min-width:190px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <span style="font-weight:600;font-size:12px;color:#e2e4ea">${zone}</span>
        <span style="font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;background:${hazardColor}22;color:${hazardColor}">${hazard}</span>
      </div>
      <table style="font-size:11px;color:#8b8fa3;line-height:1.8;border-collapse:collapse;width:100%">
        <tr>
          <td style="color:#5c6178">Depth</td>
          <td style="font-family:'JetBrains Mono',monospace;color:#38bdf8;font-weight:600;text-align:right">
            ${typeof depth === 'number' ? depth.toFixed(3) + ' m' : depth}
          </td>
        </tr>
        <tr>
          <td style="color:#5c6178">Elevation</td>
          <td style="font-family:'JetBrains Mono',monospace;color:#e2e4ea;font-weight:500;text-align:right">
            ${typeof elev === 'number' ? elev.toFixed(3) + ' m AD' : elev}
          </td>
        </tr>
        ${ts ? `<tr>
          <td style="color:#5c6178">Timestep</td>
          <td style="font-family:'JetBrains Mono',monospace;color:#8b8fa3;text-align:right">${ts} hrs</td>
        </tr>` : ''}
      </table>
    </div>
  `

  layer.bindPopup(popupHtml, { maxWidth: 260 })

  // Hover highlighting
  layer.on('mouseover', (e: any) => {
    const l = e.target
    l.setStyle({
      weight: 2,
      color: '#ffffff',
      fillOpacity: 0.85,
    })
  })

  layer.on('mouseout', (e: any) => {
    if (inundationLayer) {
      inundationLayer.resetStyle(e.target)
    }
  })
}

// ─── GeoJSON Frame Loading & Layer Swapping ──────────────────────────────────

async function loadContourLayerData(layerKey: string) {
  if (!layerKey || !map) return

  try {
    let geojsonData = geoJsonCache.get(layerKey)
    if (!geojsonData) {
      isLoadingLayer.value = true
      geojsonData = await fetchContourGeoJSON(layerKey)
      geoJsonCache.set(layerKey, geojsonData)
    }

    // Cleanly remove previous layer to prevent memory leaks or duplicate overlays
    if (inundationLayer && map.hasLayer(inundationLayer)) {
      map.removeLayer(inundationLayer)
      inundationLayer = null
    }

    inundationLayer = L.geoJSON(geojsonData as any, {
      style: contourStyle,
      onEachFeature: onEachContourFeature,
    })

    if (showInundation.value) {
      inundationLayer.addTo(map)
      // Ensure node telemetry markers stay on top
      bringMarkersToTop()

      if (!hasFittedContours && inundationLayer.getBounds().isValid()) {
        map.fitBounds(inundationLayer.getBounds().pad(0.35), { maxZoom: 16 })
        hasFittedContours = true
      }
    }
  } catch (err) {
    console.error(`Failed to load contour layer for ${layerKey}:`, err)
  } finally {
    isLoadingLayer.value = false
  }
}

async function loadContourFrame(index: number) {
  if (index < 0 || index >= timesteps.value.length) return
  const ts = timesteps.value[index]
  if (!ts) return
  await loadContourLayerData(ts)
}

async function toggleMaximaMode() {
  if (isMaximaActive.value) {
    // Exit Maxima mode, restore current hourly frame
    isMaximaActive.value = false
    if (timesteps.value.length > 0) {
      await loadContourFrame(currentIndex.value)
    }
  } else {
    // Enter Maxima mode
    pause()
    isMaximaActive.value = true
    await loadContourLayerData(maximaTimestepKey.value)
    fitToFloodExtent()
  }
}

// ─── Playback Controls ───────────────────────────────────────────────────────

function togglePlay() {
  if (isPlaying.value) {
    pause()
  } else {
    play()
  }
}

function play() {
  if (timesteps.value.length === 0) return
  if (isMaximaActive.value) {
    isMaximaActive.value = false
  }
  isPlaying.value = true
  if (playTimer) clearInterval(playTimer)

  playTimer = setInterval(() => {
    if (currentIndex.value >= timesteps.value.length - 1) {
      // Loop back to start
      currentIndex.value = 0
    } else {
      currentIndex.value++
    }
    loadContourFrame(currentIndex.value)
  }, 1000) // 1 second interval per hourly frame
}

function pause() {
  isPlaying.value = false
  if (playTimer) {
    clearInterval(playTimer)
    playTimer = null
  }
}

function stepPrev() {
  pause()
  if (isMaximaActive.value) {
    isMaximaActive.value = false
    loadContourFrame(currentIndex.value)
    return
  }
  if (currentIndex.value > 0) {
    currentIndex.value--
    loadContourFrame(currentIndex.value)
  }
}

function stepNext() {
  pause()
  if (isMaximaActive.value) {
    isMaximaActive.value = false
    loadContourFrame(currentIndex.value)
    return
  }
  if (currentIndex.value < timesteps.value.length - 1) {
    currentIndex.value++
    loadContourFrame(currentIndex.value)
  }
}

function handleSliderChange(e: Event) {
  const val = parseInt((e.target as HTMLInputElement).value, 10)
  if (!isNaN(val)) {
    if (isMaximaActive.value) {
      isMaximaActive.value = false
    }
    currentIndex.value = val
    loadContourFrame(val)
  }
}

function toggleInundationLayer() {
  showInundation.value = !showInundation.value
  if (!map) return

  if (showInundation.value) {
    if (inundationLayer && !map.hasLayer(inundationLayer)) {
      inundationLayer.addTo(map)
      bringMarkersToTop()
      fitToFloodExtent()
    } else if (!inundationLayer) {
      if (isMaximaActive.value) {
        loadContourLayerData(maximaTimestepKey.value)
      } else if (timesteps.value.length > 0) {
        loadContourFrame(currentIndex.value)
      }
    }
  } else {
    if (inundationLayer && map.hasLayer(inundationLayer)) {
      map.removeLayer(inundationLayer)
    }
  }
}

function fitToFloodExtent() {
  if (!map || !inundationLayer) return
  const bounds = inundationLayer.getBounds()
  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(0.35), { maxZoom: 16, animate: true })
  }
}

function bringMarkersToTop() {
  if (!markers) return
  markers.eachLayer((layer: any) => {
    if (typeof layer.bringToFront === 'function') {
      layer.bringToFront()
    }
  })
}

// ─── Lifecycle & Initialization ──────────────────────────────────────────────

function initMap() {
  if (!mapEl.value) return
  map = L.map(mapEl.value, {
    center: [1.5560, 110.3465],
    zoom: 14,
    zoomControl: true,
    attributionControl: true,
  })

  // Create dedicated high z-index pane for node station markers
  const markerPane = map.createPane('telemetryMarkers')
  markerPane.style.zIndex = '650'

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map)

  markers = L.layerGroup().addTo(map)
  ;(window as any).__pickNode = (id: string) => emit('select-node', id)
}

function syncNodes() {
  if (!markers || !map) return
  markers.clearLayers()
  props.nodes.forEach((n) => {
    const m = L.marker([n.latitude, n.longitude], {
      icon: icon(n.status),
      pane: 'telemetryMarkers',
    })
      .bindPopup(nodePopup(n), { maxWidth: 280, className: '' })
    m.on('click', () => emit('select-node', n.id))
    markers!.addLayer(m)
  })

  // Only fit to nodes if contours haven't centered the view
  if (props.nodes.length && !hasFittedContours && (!inundationLayer || !map.hasLayer(inundationLayer))) {
    map.fitBounds(
      L.latLngBounds(props.nodes.map((n) => [n.latitude, n.longitude] as [number, number])).pad(0.4),
      { maxZoom: 15 }
    )
  }
}

async function initContours() {
  try {
    const [list, maximaRes] = await Promise.allSettled([
      fetchContourTimesteps(),
      checkHasMaxima(),
    ])

    if (maximaRes.status === 'fulfilled' && maximaRes.value?.available) {
      hasMaxima.value = true
      if (maximaRes.value.timestep) {
        maximaTimestepKey.value = maximaRes.value.timestep
      }
    }

    if (list.status === 'fulfilled' && Array.isArray(list.value) && list.value.length > 0) {
      timesteps.value = list.value
      currentIndex.value = 0
      await loadContourFrame(0)
    }
  } catch (err) {
    console.warn('Could not load contour timesteps:', err)
  }
}

onMounted(() => {
  initMap()
  if (props.nodes.length) syncNodes()
  initContours()
})

onUnmounted(() => {
  pause()
  map?.remove()
  delete (window as any).__pickNode
})

watch(() => props.nodes, syncNodes, { deep: true })
</script>

<template>
  <div class="map-wrap card">
    <!-- Top Header Bar -->
    <div class="map-bar">
      <div class="map-title-group">
        <span class="map-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" class="title-icon">
            <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
            <line x1="8" y1="2" x2="8" y2="18"/>
            <line x1="16" y1="6" x2="16" y2="22"/>
          </svg>
          2D Inundation & Monitoring Map
        </span>
        <button
          type="button"
          class="layer-toggle-btn"
          :class="{ 'layer-toggle-btn--active': showInundation }"
          @click="toggleInundationLayer"
          title="Toggle 2D Inundation Shapefile Contours"
        >
          <span class="toggle-dot"></span>
          2D Inundation Layer
        </button>

        <!-- Peak Simulation Maxima Envelope Toggle -->
        <button
          v-if="hasMaxima && showInundation"
          type="button"
          class="layer-toggle-btn layer-toggle-btn--maxima"
          :class="{ 'layer-toggle-btn--maxima-active': isMaximaActive }"
          @click="toggleMaximaMode"
          title="Toggle overall simulation peak flood inundation envelope (DTM Maxima)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="maxima-icon">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
          {{ isMaximaActive ? 'Showing Peak Maxima' : 'Show Maxima Envelope' }}
        </button>

        <button
          v-if="showInundation && inundationLayer"
          type="button"
          class="layer-toggle-btn"
          @click="fitToFloodExtent"
          title="Center Map on 2D Flood Inundation Extent"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px">
            <circle cx="12" cy="12" r="10"/>
            <line x1="22" y1="12" x2="18" y2="12"/>
            <line x1="6" y1="12" x2="2" y2="12"/>
            <line x1="12" y1="6" x2="12" y2="2"/>
            <line x1="12" y1="22" x2="12" y2="18"/>
          </svg>
          Zoom to Flood
        </button>
      </div>

      <!-- Legend Elements -->
      <div class="legend">
        <div class="legend-group">
          <span class="legend-label">Stations:</span>
          <span class="legend-i"><span class="dot dot--ok"></span>Normal</span>
          <span class="legend-i"><span class="dot dot--warn"></span>Warning</span>
          <span class="legend-i"><span class="dot dot--danger"></span>Alert</span>
        </div>
        <div v-if="showInundation && (timesteps.length > 0 || isMaximaActive)" class="legend-group legend-depth">
          <span class="legend-label">Depth:</span>
          <span class="legend-i"><span class="depth-swatch depth-swatch--shallow"></span>&lt;0.5m</span>
          <span class="legend-i"><span class="depth-swatch depth-swatch--mid"></span>0.5-1.2m</span>
          <span class="legend-i"><span class="depth-swatch depth-swatch--deep"></span>&gt;1.2m</span>
        </div>
      </div>
    </div>

    <!-- Leaflet Map Canvas -->
    <div ref="mapEl" class="map-canvas"></div>

    <!-- Interactive Time-Lapse Simulation Player -->
    <div v-if="timesteps.length > 0" class="sim-player">
      <div class="player-controls">
        <!-- Play / Pause Button -->
        <button
          type="button"
          class="btn-play"
          :class="{ 'btn-play--active': isPlaying }"
          @click="togglePlay"
          :title="isPlaying ? 'Pause Simulation' : 'Play Hourly Simulation'"
        >
          <svg v-if="!isPlaying" viewBox="0 0 24 24" fill="currentColor" class="play-icon">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="currentColor" class="play-icon">
            <rect x="6" y="4" width="4" height="16"/>
            <rect x="14" y="4" width="4" height="16"/>
          </svg>
        </button>

        <!-- Step Prev / Next -->
        <div class="step-btn-group">
          <button
            type="button"
            class="btn-step"
            :disabled="!isMaximaActive && currentIndex === 0"
            @click="stepPrev"
            title="Previous Hour"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="step-icon">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <button
            type="button"
            class="btn-step"
            :disabled="!isMaximaActive && currentIndex === timesteps.length - 1"
            @click="stepNext"
            title="Next Hour"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="step-icon">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
        </div>

        <!-- Frame Time Readout -->
        <div class="time-readout">
          <span class="time-pill" :class="{ 'time-pill--maxima': isMaximaActive }">
            <span class="radar-dot" :class="{ 'radar-dot--live': isPlaying, 'radar-dot--maxima': isMaximaActive }"></span>
            {{ isMaximaActive ? 'PEAK ENVELOPE' : `FRAME ${currentTimestep}` }}
          </span>
          <span class="clock-display" :class="{ 'clock-display--maxima': isMaximaActive }">
            {{ isMaximaActive ? 'SIMULATION MAXIMA EXTENT' : `${currentFormattedTime} HRS` }}
          </span>
        </div>
      </div>

      <!-- Maxima Information Banner -->
      <div v-if="isMaximaActive" class="maxima-banner">
        <span>★ Viewing overall peak inundation envelope (DTM Maxima). Scrub timeline or press Play to resume hourly sequence.</span>
      </div>

      <!-- Scrubber Timeline Slider -->
      <div class="slider-container">
        <input
          type="range"
          min="0"
          :max="timesteps.length - 1"
          :value="currentIndex"
          @input="handleSliderChange"
          class="time-slider"
          aria-label="Simulation Time Slider"
        />
        <div class="slider-ticks">
          <span
            v-for="(ts, idx) in timesteps"
            :key="ts"
            class="tick-label"
            :class="{ 'tick-label--active': !isMaximaActive && idx === currentIndex }"
          >
            {{ ts.length === 4 ? `${ts.slice(0, 2)}:${ts.slice(2)}` : ts }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.map-wrap {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Map Header Bar ── */
.map-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-surface);
  flex-wrap: wrap;
  gap: 10px;
}

.map-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.map-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: 0.02em;
}

.title-icon {
  width: 16px;
  height: 16px;
  color: var(--color-accent);
}

/* ── Layer Toggle Button ── */
.layer-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border);
  color: var(--color-text-dim);
  transition: all 0.15s ease;
}

.layer-toggle-btn:hover {
  border-color: var(--color-border-focus);
  color: var(--color-text);
}

.layer-toggle-btn--active {
  background: rgba(2, 132, 199, 0.15);
  border-color: rgba(56, 189, 248, 0.4);
  color: #38bdf8;
}

.layer-toggle-btn--maxima {
  border-color: rgba(245, 158, 11, 0.35);
  color: #d97706;
}

.layer-toggle-btn--maxima:hover {
  border-color: rgba(245, 158, 11, 0.7);
  color: #f59e0b;
}

.layer-toggle-btn--maxima-active {
  background: rgba(245, 158, 11, 0.18);
  border-color: #f59e0b;
  color: #fbbf24;
  font-weight: 700;
  box-shadow: 0 0 10px rgba(245, 158, 11, 0.25);
}

.maxima-icon {
  width: 12px;
  height: 12px;
}

.toggle-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

/* ── Legend ── */
.legend {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.legend-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-label {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-dim);
}

.legend-i {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}

.depth-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.depth-swatch--shallow { background: #38bdf8; opacity: 0.7; }
.depth-swatch--mid     { background: #0284c7; opacity: 0.8; }
.depth-swatch--deep    { background: #1d4ed8; opacity: 0.9; }

/* ── Map Canvas ── */
.map-canvas {
  width: 100%;
  height: 420px;
  background: #0d1117;
}

:deep(.leaflet-tile-pane) {
  filter: brightness(0.65) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.75);
}

/* ── Simulation Time-Lapse Player ── */
.sim-player {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 16px 12px 16px;
  background: var(--color-bg-surface);
  border-top: 1px solid var(--color-border-subtle);
}

.player-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-play {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--color-accent);
  color: #ffffff;
  cursor: pointer;
  transition: all 0.15s ease;
  box-shadow: 0 2px 8px rgba(74, 124, 255, 0.35);
  flex-shrink: 0;
}

.btn-play:hover {
  transform: scale(1.05);
  background: #3b6ae8;
}

.btn-play--active {
  background: #0284c7;
  box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.25);
}

.play-icon {
  width: 14px;
  height: 14px;
}

.step-btn-group {
  display: flex;
  gap: 4px;
}

.btn-step {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border);
  color: var(--color-text-dim);
  cursor: pointer;
  transition: all 0.12s ease;
}

.btn-step:hover:not(:disabled) {
  border-color: var(--color-border-focus);
  color: var(--color-text);
}

.btn-step:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.step-icon {
  width: 12px;
  height: 12px;
}

/* ── Time Readout ── */
.time-readout {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 4px;
}

.time-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.time-pill--maxima {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.4);
  color: #fbbf24;
}

.radar-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-dim);
}

.radar-dot--live {
  background: #38bdf8;
  box-shadow: 0 0 6px #38bdf8;
  animation: blink 1s infinite alternate;
}

.radar-dot--maxima {
  background: #fbbf24;
  box-shadow: 0 0 6px #fbbf24;
}

.clock-display {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 700;
  color: #38bdf8;
  letter-spacing: 0.05em;
}

.clock-display--maxima {
  color: #fbbf24;
}

.maxima-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: rgba(245, 158, 11, 0.10);
  border: 1px solid rgba(245, 158, 11, 0.25);
  color: #fbbf24;
  font-size: 0.72rem;
  font-weight: 500;
}

/* ── Slider Container ── */
.slider-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.time-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 5px;
  border-radius: 3px;
  background: var(--color-bg-raised);
  outline: none;
  cursor: pointer;
  transition: background 0.15s ease;
}

.time-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #38bdf8;
  border: 2px solid #ffffff;
  cursor: pointer;
  box-shadow: 0 0 8px rgba(56, 189, 248, 0.6);
  transition: transform 0.1s ease;
}

.time-slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}

.slider-ticks {
  display: flex;
  justify-content: space-between;
  padding: 0 4px;
}

.tick-label {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: var(--color-text-dim);
  transition: color 0.15s ease;
}

.tick-label--active {
  color: #38bdf8;
  font-weight: 700;
}
</style>
