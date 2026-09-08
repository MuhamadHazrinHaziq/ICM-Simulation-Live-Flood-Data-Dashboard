<script setup lang="ts">
import { computed } from 'vue'
import { fetchActiveAlerts, usePolling, type AlertListData, type AlertData } from '@/composables/useApi'

const { data: alertData, loading } = usePolling<AlertListData>(fetchActiveAlerts, 30000)

const alerts = computed(() => alertData.value?.alerts || [])
const totalActive = computed(() => alertData.value?.total_active || 0)

function formatTime(isoStr: string | null): string {
  if (!isoStr) return '—'
  const d = new Date(isoStr)
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getPriorityType(priority: string | null): 'danger' | 'warn' | 'muted' {
  const p = (priority || '').toLowerCase()
  if (p === 'critical' || p === 'alert' || p === 'severe') return 'danger'
  if (p === 'warning' || p === 'moderate' || p === 'watch') return 'warn'
  return 'muted'
}
</script>

<template>
  <div class="alert-panel card">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="panel-icon">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        <span class="panel-title">Active Alert Stream</span>
      </div>
      <div class="header-status">
        <span v-if="totalActive > 0" class="tag tag--danger">
          <span class="dot dot--danger"></span>
          {{ totalActive }} Active
        </span>
        <span v-else class="tag tag--ok">
          <span class="dot dot--ok"></span>
          Normal Status
        </span>
      </div>
    </div>

    <div class="panel-body">
      <!-- Loading Skeleton -->
      <div v-if="loading" class="skeleton-list">
        <div v-for="i in 3" :key="i" class="alert-skeleton"></div>
      </div>

      <!-- Empty State: Operational Normal -->
      <div v-else-if="alerts.length === 0" class="all-clear-state">
        <div class="shield-icon-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="shield-icon">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <polyline points="9 12 11 14 15 10"/>
          </svg>
        </div>
        <div class="all-clear-title">Zero Active Alert Thresholds</div>
        <p class="all-clear-desc">
          Telemetry & simulation models for all monitored drains are operating within nominal thresholds.
        </p>
      </div>

      <!-- Alert List -->
      <div v-else class="alert-items">
        <div
          v-for="alert in alerts"
          :key="alert.alert_definition_id"
          class="alert-entry"
          :class="`alert-entry--${getPriorityType(alert.priority)}`"
        >
          <div class="entry-top">
            <span class="tag" :class="`tag--${getPriorityType(alert.priority)}`">
              {{ alert.priority || 'ADVISORY' }}
            </span>
            <span v-if="alert.category" class="entry-category">{{ alert.category }}</span>
            <span class="entry-id">{{ alert.alert_definition_id }}</span>
          </div>

          <div class="entry-details">
            <div class="target-row">
              <span class="field-label">Target:</span>
              <span class="target-id">{{ alert.target_id || 'System-wide' }}</span>
              <span v-if="alert.target_type" class="target-type">({{ alert.target_type }})</span>
            </div>

            <div class="time-window">
              <div class="time-block">
                <span class="time-label">Onset</span>
                <span class="time-val">{{ formatTime(alert.onset_time) }}</span>
              </div>
              <span class="time-divider">&rarr;</span>
              <div class="time-block">
                <span class="time-label">End</span>
                <span class="time-val">{{ formatTime(alert.end_time) }}</span>
              </div>
            </div>

            <div v-if="alert.peak_value !== null" class="peak-block">
              <span class="field-label">Forecast Peak:</span>
              <span class="peak-val">
                {{ alert.peak_value.toFixed(3) }}
                <span class="peak-unit">{{ alert.peak_value_units || 'm' }}</span>
              </span>
              <span v-if="alert.peak_time" class="peak-timestamp">
                at {{ formatTime(alert.peak_time) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alert-panel {
  display: flex;
  flex-direction: column;
  height: 485px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-surface);
}

.panel-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-icon {
  width: 16px;
  height: 16px;
  color: var(--color-text-secondary);
}

.panel-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
}

/* ── All Clear Empty State ── */
.all-clear-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 24px 16px;
}

.shield-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--color-ok-dim);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 14px;
}

.shield-icon {
  width: 22px;
  height: 22px;
  color: var(--color-ok);
}

.all-clear-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 6px;
}

.all-clear-desc {
  font-size: 0.78rem;
  color: var(--color-text-dim);
  max-width: 280px;
  line-height: 1.5;
}

/* ── Alert Items ── */
.alert-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.alert-entry {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-entry--danger { border-left-color: var(--color-danger); }
.alert-entry--warn { border-left-color: var(--color-warn); }
.alert-entry--muted { border-left-color: var(--color-accent); }

.entry-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.entry-category {
  font-size: 0.72rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.entry-id {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--color-text-dim);
}

.entry-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.78rem;
}

.target-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.field-label {
  color: var(--color-text-dim);
  font-size: 0.72rem;
}

.target-id {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--color-text);
}

.target-type {
  font-size: 0.7rem;
  color: var(--color-text-dim);
}

.time-window {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
}

.time-block {
  display: flex;
  flex-direction: column;
}

.time-label {
  font-size: 0.62rem;
  text-transform: uppercase;
  color: var(--color-text-dim);
  letter-spacing: 0.05em;
}

.time-val {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--color-text-secondary);
}

.time-divider {
  color: var(--color-text-dim);
  font-size: 0.8rem;
}

.peak-block {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px dashed var(--color-border-subtle);
}

.peak-val {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--color-danger);
}

.peak-unit {
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--color-text-dim);
}

.peak-timestamp {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-dim);
}

.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-skeleton {
  height: 90px;
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
}
</style>
