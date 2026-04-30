<template>
  <section class="jobs-panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Queue</p>
        <h3>Recent Analysis Jobs</h3>
        <p class="panel-copy">
          Track recent submissions, retry failed runs, and cancel queued or running jobs without leaving the dashboard.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost-btn" :disabled="isLoading" @click="$emit('refresh')">
          Refresh Jobs
        </button>
      </div>
    </div>

    <form class="job-filters" @submit.prevent="submitFilters">
      <label>
        Status
        <select v-model="localStatus">
          <option value="">All statuses</option>
          <option value="queued,running,canceling">Active</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="canceling">Canceling</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="canceled">Canceled</option>
        </select>
      </label>

      <label>
        Source
        <select v-model="localSourceKind">
          <option value="">All sources</option>
          <option value="upload">Upload</option>
          <option value="camera_url">Camera URL</option>
        </select>
      </label>

      <label>
        Analysis Name
        <input v-model.trim="localAnalysisName" type="text" placeholder="Filter by name" />
      </label>

      <div class="filter-actions">
        <button type="submit" class="primary-btn">Apply</button>
        <button type="button" class="ghost-btn" @click="resetFilters">Clear</button>
      </div>
    </form>

    <div v-if="error" class="state-card state-card--error">{{ error }}</div>
    <div v-else-if="isLoading" class="state-card">Loading recent jobs...</div>
    <div v-else-if="!jobs.length" class="state-card">No jobs match the current filters.</div>

    <template v-else>
      <div class="jobs-meta">
        <span>Showing {{ jobs.length }} of {{ total }} jobs</span>
        <span>Page {{ currentPage }} of {{ totalPages }}</span>
      </div>

      <div class="jobs-list">
        <article v-for="job in jobs" :key="job.job_id" class="job-card">
          <div class="job-header">
            <div>
              <h4>{{ job.analysis_name || "Untitled Analysis" }}</h4>
              <p>{{ formatDate(job.created_at) }}</p>
            </div>
            <span class="status-chip" :class="statusToneClass(job.status)">
              {{ statusLabel(job.status) }}
            </span>
          </div>

          <div class="job-details">
            <div class="detail-item">
              <span>Source</span>
              <strong>{{ formatSource(job.source_kind) }}</strong>
            </div>
            <div class="detail-item">
              <span>Progress</span>
              <strong>{{ formatProgress(job.progress_percent, job.progress_message) }}</strong>
            </div>
            <div class="detail-item">
              <span>Updated</span>
              <strong>{{ formatDate(job.updated_at) }}</strong>
            </div>
          </div>

          <p v-if="job.error" class="job-error">{{ job.error }}</p>

          <div class="job-actions">
            <button
              type="button"
              class="secondary-btn"
              :disabled="!canCancel(job) || !!actionState[job.job_id]"
              @click="$emit('cancel-job', job.job_id)"
            >
              {{ actionState[job.job_id] === "canceling" ? "Canceling..." : "Cancel" }}
            </button>
            <button
              type="button"
              class="primary-btn"
              :disabled="!canRetry(job) || !!actionState[job.job_id]"
              @click="$emit('retry-job', job.job_id)"
            >
              {{ actionState[job.job_id] === "retrying" ? "Retrying..." : "Retry" }}
            </button>
          </div>
        </article>
      </div>

      <div class="pagination-controls">
        <button type="button" class="ghost-btn" :disabled="currentPage <= 1 || isLoading" @click="$emit('prev-page')">
          Previous
        </button>
        <button
          type="button"
          class="ghost-btn"
          :disabled="currentPage >= totalPages || isLoading"
          @click="$emit('next-page')"
        >
          Next
        </button>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  jobs: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  limit: { type: Number, default: 6 },
  offset: { type: Number, default: 0 },
  isLoading: { type: Boolean, default: false },
  error: { type: String, default: null },
  filters: {
    type: Object,
    default: () => ({
      status: "",
      sourceKind: "",
      analysisName: "",
    }),
  },
  actionState: { type: Object, default: () => ({}) },
});

const emit = defineEmits([
  "refresh",
  "apply-filters",
  "prev-page",
  "next-page",
  "retry-job",
  "cancel-job",
]);

const localStatus = ref(props.filters.status || "");
const localSourceKind = ref(props.filters.sourceKind || "");
const localAnalysisName = ref(props.filters.analysisName || "");

watch(
  () => props.filters,
  (nextFilters) => {
    localStatus.value = nextFilters.status || "";
    localSourceKind.value = nextFilters.sourceKind || "";
    localAnalysisName.value = nextFilters.analysisName || "";
  },
  { deep: true }
);

const currentPage = computed(() => Math.floor(props.offset / props.limit) + 1);
const totalPages = computed(() => Math.max(1, Math.ceil((props.total || 0) / props.limit)));

function submitFilters() {
  emit("apply-filters", {
    status: localStatus.value,
    sourceKind: localSourceKind.value,
    analysisName: localAnalysisName.value,
  });
}

function resetFilters() {
  localStatus.value = "";
  localSourceKind.value = "";
  localAnalysisName.value = "";
  submitFilters();
}

function canRetry(job) {
  return ["failed", "canceled"].includes(job.status) && job.source_kind === "camera_url";
}

function canCancel(job) {
  return ["queued", "running", "canceling"].includes(job.status);
}

function formatSource(sourceKind) {
  if (sourceKind === "camera_url") {
    return "Camera URL";
  }
  if (sourceKind === "upload") {
    return "Upload";
  }
  return "Unknown";
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
    return `${percent}%${message ? ` • ${message}` : ""}`;
  }
  return message || "Waiting for update";
}

function statusLabel(status) {
  return (status || "unknown").replace(/_/g, " ");
}

function statusToneClass(status) {
  return `status-chip--${status || "unknown"}`;
}
</script>

<style scoped>
.jobs-panel {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 1.5rem;
  padding: 1.5rem;
  box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 1.25rem;
  align-items: flex-start;
}

.eyebrow {
  margin: 0 0 0.3rem;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0ea5e9;
}

.panel-header h3 {
  margin: 0;
  color: #0f172a;
  font-size: 1.35rem;
}

.panel-copy {
  margin: 0.45rem 0 0;
  color: #475569;
  line-height: 1.5;
  max-width: 44rem;
}

.job-filters {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  align-items: end;
  margin-top: 1.5rem;
}

.job-filters label {
  display: grid;
  gap: 0.45rem;
  font-weight: 600;
  color: #334155;
}

.job-filters input,
.job-filters select {
  min-height: 2.7rem;
  padding: 0.75rem 0.9rem;
  border-radius: 0.9rem;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: #f8fafc;
  color: #0f172a;
}

.filter-actions,
.header-actions,
.pagination-controls,
.job-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.jobs-meta {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  color: #475569;
  font-size: 0.95rem;
  margin-top: 1rem;
}

.jobs-list {
  display: grid;
  gap: 1rem;
  margin-top: 1rem;
}

.job-card {
  border-radius: 1.15rem;
  padding: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92), rgba(255, 255, 255, 0.95));
}

.job-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.job-header h4 {
  margin: 0;
  color: #0f172a;
}

.job-header p {
  margin: 0.25rem 0 0;
  color: #64748b;
  font-size: 0.92rem;
}

.status-chip {
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 800;
  text-transform: capitalize;
  white-space: nowrap;
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

.job-details {
  display: grid;
  gap: 0.8rem;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  margin-top: 1rem;
}

.detail-item span {
  display: block;
  color: #64748b;
  font-size: 0.88rem;
  margin-bottom: 0.2rem;
}

.detail-item strong {
  color: #0f172a;
  line-height: 1.45;
}

.job-error {
  margin: 0.9rem 0 0;
  color: #991b1b;
  background: rgba(220, 38, 38, 0.08);
  padding: 0.8rem 0.9rem;
  border-radius: 0.9rem;
}

.job-actions {
  margin-top: 1rem;
}

.state-card {
  border-radius: 1rem;
  padding: 1rem 1.1rem;
  background: #f8fafc;
  color: #475569;
  margin-top: 1rem;
}

.state-card--error {
  background: rgba(220, 38, 38, 0.08);
  color: #7f1d1d;
}

.primary-btn,
.secondary-btn,
.ghost-btn {
  min-height: 2.7rem;
  border-radius: 999px;
  padding: 0.72rem 1.15rem;
  font-weight: 700;
  cursor: pointer;
  border: 1px solid transparent;
  transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.primary-btn {
  background: #0ea5e9;
  color: white;
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

.primary-btn:hover,
.secondary-btn:hover,
.ghost-btn:hover {
  transform: translateY(-1px);
}

.primary-btn:disabled,
.secondary-btn:disabled,
.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

@media (max-width: 720px) {
  .jobs-panel {
    padding: 1.15rem;
  }

  .panel-header,
  .job-header {
    flex-direction: column;
  }
}
</style>
