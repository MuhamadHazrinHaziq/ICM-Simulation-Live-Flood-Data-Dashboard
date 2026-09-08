<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { NodeData } from '@/composables/useApi'

const props = defineProps<{ nodes: NodeData[] }>()
const emit = defineEmits<{ (e: 'select-node', nodeId: string): void }>()

const mapEl = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let markers: L.LayerGroup | null = null

const COLORS: Record<string, string> = { normal: '#34c471', warning: '#e6a020', alert: '#e04848' }

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

function popup(n: NodeData): string {
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

function init() {
  if (!mapEl.value) return
  map = L.map(mapEl.value, { center: [1.5535, 110.3485], zoom: 14, zoomControl: true, attributionControl: true })
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map)
  markers = L.layerGroup().addTo(map)
  ;(window as any).__pickNode = (id: string) => emit('select-node', id)
}

function sync() {
  if (!markers || !map) return
  markers.clearLayers()
  props.nodes.forEach(n => {
    const m = L.marker([n.latitude, n.longitude], { icon: icon(n.status) })
      .bindPopup(popup(n), { maxWidth: 280, className: '' })
    m.on('click', () => emit('select-node', n.id))
    markers!.addLayer(m)
  })
  if (props.nodes.length) {
    map.fitBounds(L.latLngBounds(props.nodes.map(n => [n.latitude, n.longitude] as [number, number])).pad(0.4), { maxZoom: 15 })
  }
}

onMounted(() => { init(); if (props.nodes.length) sync() })
onUnmounted(() => { map?.remove(); delete (window as any).__pickNode })
watch(() => props.nodes, sync, { deep: true })
</script>

<template>
  <div class="map-wrap card">
    <div class="map-bar">
      <span class="map-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" style="width:16px;height:16px"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>
        Monitoring Map
      </span>
      <div class="legend">
        <span class="legend-i"><span class="dot dot--ok"></span>Normal</span>
        <span class="legend-i"><span class="dot dot--warn"></span>Warning</span>
        <span class="legend-i"><span class="dot dot--danger"></span>Alert</span>
      </div>
    </div>
    <div ref="mapEl" class="map-canvas"></div>
  </div>
</template>

<style scoped>
.map-wrap { display: flex; flex-direction: column; overflow: hidden; }

.map-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.map-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-text);
}

.legend { display: flex; gap: 14px; }
.legend-i { display: flex; align-items: center; gap: 5px; font-size: 0.7rem; color: var(--color-text-secondary); }

.map-canvas {
  width: 100%;
  height: 430px;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

:deep(.leaflet-tile-pane) {
  filter: brightness(0.65) invert(1) contrast(3) hue-rotate(200deg) saturate(0.3) brightness(0.75);
}
</style>
