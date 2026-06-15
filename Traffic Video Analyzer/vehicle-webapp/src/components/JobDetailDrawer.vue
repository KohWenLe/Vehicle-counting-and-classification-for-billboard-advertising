<template>
  <teleport to="body">
    <div v-if="visible" class="drawer-shell" role="dialog" aria-modal="true" aria-labelledby="job-detail-title">
      <button type="button" class="drawer-backdrop" aria-label="Close job details" @click="$emit('close')"></button>

      <aside class="drawer-panel">
        <header class="drawer-header">
          <div>
            <p class="eyebrow">Job Detail</p>
            <h3 id="job-detail-title">{{ jobTitle }}</h3>
            <p class="header-subtitle">{{ formatDate(job?.created_at) }}</p>
          </div>
          <button type="button" class="icon-btn" aria-label="Close job details" @click="$emit('close')">X</button>
        </header>

        <div v-if="isLoading" class="state-card">Loading job details...</div>
        <div v-else-if="error" class="state-card state-card--error">{{ error }}</div>
        <div v-else-if="!job" class="state-card">Select a job to inspect its processing record.</div>

        <template v-else>
          <section class="detail-section">
            <div class="status-row">
              <span class="status-chip" :class="statusToneClass(job.status)">{{ statusLabel(job.status) }}</span>
              <span>{{ formatSource(job.source_kind) }}</span>
            </div>

            <div class="progress-track" aria-hidden="true">
              <div class="progress-fill" :style="{ width: `${normalizedProgress}%` }"></div>
            </div>
            <p class="progress-copy">{{ formatProgress(job.progress_percent, job.progress_message) }}</p>
          </section>

          <section class="detail-section">
            <h4>Timeline</h4>
            <dl class="detail-grid">
              <div>
                <dt>Created</dt>
                <dd>{{ formatDate(job.created_at) }}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{{ formatDate(job.started_at) }}</dd>
              </div>
              <div>
                <dt>Completed</dt>
                <dd>{{ formatDate(job.completed_at) }}</dd>
              </div>
              <div>
                <dt>Worker</dt>
                <dd>{{ job.worker_id || "Not assigned" }}</dd>
              </div>
            </dl>
          </section>

          <section v-if="job.error" class="detail-section detail-section--error">
            <h4>Error</h4>
            <p>{{ job.error }}</p>
          </section>

          <section v-if="resultEntries.length" class="detail-section">
            <div class="section-title-row">
              <h4>Vehicle Mix</h4>
              <strong>{{ totalVehicles }} total</strong>
            </div>
            <div class="counts-grid">
              <div v-for="([label, value], index) in resultEntries" :key="`${label}-${index}`" class="count-item">
                <span>{{ label }}</span>
                <strong>{{ value }}</strong>
              </div>
            </div>
          </section>

          <section v-if="job.result?.peak" class="detail-section">
            <h4>Peak Window</h4>
            <p>{{ job.result.peak.hour }}:00 with {{ job.result.peak.count }} vehicles.</p>
          </section>

          <section v-if="recommendations.length" class="detail-section">
            <h4>Recommendations</h4>
            <ul class="compact-list">
              <li v-for="(recommendation, index) in recommendations" :key="`recommendation-${index}`">
                {{ recommendation }}
              </li>
            </ul>
          </section>

          <section v-if="annotatedUrl" class="detail-section">
            <h4>Annotated Output</h4>
            <video :key="annotatedUrl" class="drawer-video" controls preload="metadata">
              <source :src="annotatedUrl" type="video/mp4" />
              Your browser does not support the video tag.
            </video>
            <a class="video-link" :href="annotatedUrl" target="_blank" rel="noopener">Open video in a new tab</a>
          </section>

          <footer class="drawer-actions">
            <button
              type="button"
              class="primary-btn"
              :disabled="!canOpenResults"
              @click="$emit('open-results', job)"
            >
              Open Results
            </button>
            <button
              type="button"
              class="secondary-btn"
              :disabled="!canCancel || !!actionState[job.job_id]"
              @click="$emit('cancel-job', job.job_id)"
            >
              {{ actionState[job.job_id] === "canceling" ? "Canceling..." : "Cancel Job" }}
            </button>
            <button
              type="button"
              class="ghost-btn"
              :disabled="!canRetry || !!actionState[job.job_id]"
              @click="$emit('retry-job', job.job_id)"
            >
              {{ actionState[job.job_id] === "retrying" ? "Retrying..." : "Retry" }}
            </button>
            <button type="button" class="ghost-btn" :disabled="isLoading" @click="$emit('refresh')">
              Refresh
            </button>
          </footer>
        </template>
      </aside>
    </div>
  </teleport>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  job: { type: Object, default: null },
  isLoading: { type: Boolean, default: false },
  error: { type: String, default: null },
  actionState: { type: Object, default: () => ({}) },
});

defineEmits(["close", "refresh", "open-results", "retry-job", "cancel-job"]);

const jobTitle = computed(() => props.job?.analysis_name || "Untitled Analysis");
const resultEntries = computed(() => Object.entries(props.job?.result?.counts || {}));
const totalVehicles = computed(() => resultEntries.value.reduce((sum, [, value]) => sum + Number(value || 0), 0));
const normalizedProgress = computed(() => {
  if (typeof props.job?.progress_percent !== "number") {
    return props.job?.status === "completed" ? 100 : 0;
  }
  return Math.min(100, Math.max(0, props.job.progress_percent));
});
const recommendations = computed(() => {
  const saved = props.job?.result?.recommendations || [];
  return Array.isArray(saved) ? saved : [saved].filter(Boolean);
});
const annotatedUrl = computed(() => {
  const name = props.job?.result?.annotated_video;
  return name ? `/output/${encodeURIComponent(name)}?job=${encodeURIComponent(props.job.job_id)}` : null;
});
const canOpenResults = computed(() => props.job?.status === "completed" && !!props.job?.result);
const canRetry = computed(() => ["failed", "canceled"].includes(props.job?.status) && props.job?.source_kind === "camera_url");
const canCancel = computed(() => ["queued", "running", "canceling"].includes(props.job?.status));

function formatSource(sourceKind) {
  if (sourceKind === "camera_url") {
    return "Camera URL";
  }
  if (sourceKind === "upload") {
    return "Upload";
  }
  return "Unknown source";
}

function formatDate(value) {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function formatProgress(percent, message) {
  if (typeof percent === "number") {
    return `${percent}%${message ? ` - ${message}` : ""}`;
  }
  return message || "Waiting for worker update";
}

function statusLabel(status) {
  return (status || "unknown").replace(/_/g, " ");
}

function statusToneClass(status) {
  return `status-chip--${status || "unknown"}`;
}
</script>

<style scoped>
.drawer-shell {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  justify-items: end;
}

.drawer-backdrop {
  position: absolute;
  inset: 0;
  border: 0;
  background: rgba(15, 23, 42, 0.42);
  cursor: pointer;
}

.drawer-panel {
  position: relative;
  z-index: 1;
  width: min(560px, 100%);
  height: 100%;
  overflow-y: auto;
  background: #ffffff;
  color: #0f172a;
  padding: 1.25rem;
  box-shadow: -18px 0 48px rgba(15, 23, 42, 0.18);
}

.drawer-header,
.section-title-row,
.status-row,
.drawer-actions {
  display: flex;
  gap: 1rem;
}

.drawer-header,
.section-title-row,
.status-row {
  justify-content: space-between;
  align-items: flex-start;
}

.drawer-header {
  padding-bottom: 1rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.95);
}

.eyebrow {
  margin: 0 0 0.3rem;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0ea5e9;
}

.drawer-header h3,
.detail-section h4 {
  margin: 0;
}

.drawer-header h3 {
  font-size: 1.45rem;
}

.header-subtitle {
  margin: 0.35rem 0 0;
  color: #64748b;
}

.icon-btn {
  width: 2.4rem;
  height: 2.4rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  background: #f8fafc;
  color: #0f172a;
  font-weight: 800;
  cursor: pointer;
}

.detail-section,
.state-card {
  margin-top: 1rem;
  border-radius: 0.75rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  background: #f8fafc;
  padding: 1rem;
}

.detail-section--error,
.state-card--error {
  background: rgba(220, 38, 38, 0.08);
  border-color: rgba(220, 38, 38, 0.16);
  color: #7f1d1d;
}

.status-row {
  align-items: center;
  color: #475569;
  font-weight: 700;
}

.status-chip {
  padding: 0.38rem 0.7rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 800;
  text-transform: capitalize;
}

.status-chip--queued,
.status-chip--running,
.status-chip--canceling {
  background: rgba(14, 165, 233, 0.12);
  color: #075985;
}

.status-chip--completed {
  background: rgba(16, 185, 129, 0.14);
  color: #166534;
}

.status-chip--failed {
  background: rgba(220, 38, 38, 0.12);
  color: #991b1b;
}

.status-chip--canceled {
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
}

.progress-track {
  height: 0.65rem;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
  margin-top: 0.85rem;
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0ea5e9, #10b981);
}

.progress-copy {
  margin: 0.65rem 0 0;
  color: #475569;
}

.detail-grid,
.counts-grid {
  display: grid;
  gap: 0.85rem;
}

.detail-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0.9rem 0 0;
}

.detail-grid dt,
.count-item span {
  color: #64748b;
  font-size: 0.88rem;
}

.detail-grid dd {
  margin: 0.25rem 0 0;
  color: #0f172a;
  font-weight: 700;
}

.counts-grid {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin-top: 0.9rem;
}

.count-item {
  border-radius: 0.65rem;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.95);
  padding: 0.8rem;
}

.count-item span,
.count-item strong {
  display: block;
}

.count-item strong {
  margin-top: 0.25rem;
  font-size: 1.1rem;
}

.compact-list {
  margin: 0.8rem 0 0;
  padding-left: 1.1rem;
  display: grid;
  gap: 0.4rem;
  color: #334155;
}

.drawer-video {
  width: 100%;
  margin-top: 0.85rem;
  border-radius: 0.65rem;
  background: #020617;
}

.video-link {
  display: inline-block;
  margin-top: 0.65rem;
  color: #0284c7;
  font-weight: 800;
}

.drawer-actions {
  flex-wrap: wrap;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(226, 232, 240, 0.95);
}

.primary-btn,
.secondary-btn,
.ghost-btn {
  min-height: 2.55rem;
  border-radius: 999px;
  padding: 0.65rem 1rem;
  font-weight: 800;
  cursor: pointer;
  border: 1px solid transparent;
}

.primary-btn {
  background: #0ea5e9;
  color: #ffffff;
}

.secondary-btn {
  background: rgba(239, 68, 68, 0.12);
  color: #991b1b;
}

.ghost-btn {
  background: transparent;
  border-color: rgba(14, 165, 233, 0.28);
  color: #0f3d4c;
}

.primary-btn:disabled,
.secondary-btn:disabled,
.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .drawer-panel {
    width: 100%;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
