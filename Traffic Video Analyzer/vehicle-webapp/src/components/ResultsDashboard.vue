<template>
  <section v-if="resultEntries.length" class="results-dashboard">
    <div class="results-band">
      <div>
        <p class="eyebrow">Results</p>
        <h2>Media Planning Snapshot</h2>
      </div>
      <div class="kpi-grid">
        <article class="kpi-card">
          <span>Total Vehicles</span>
          <strong>{{ totalVehicles }}</strong>
        </article>
        <article class="kpi-card">
          <span>Dominant Segment</span>
          <strong>{{ dominantClass }}</strong>
        </article>
        <article class="kpi-card">
          <span>Peak Window</span>
          <strong>{{ peakLabel }}</strong>
        </article>
        <article class="kpi-card" :class="qualityToneClass">
          <span>Review Status</span>
          <strong>{{ qualityLabel }}</strong>
        </article>
      </div>
    </div>

    <div class="results-layout">
      <div class="panel chart-panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Audience Mix</p>
            <h3>Vehicle Class Distribution</h3>
          </div>
          <span class="section-chip">{{ audienceSummary }}</span>
        </div>

        <table class="results-table">
          <thead>
            <tr>
              <th>Class</th>
              <th>Count</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="([label, value], index) in resultEntries" :key="`${label}-${index}`">
              <td>{{ label }}</td>
              <td>{{ value }}</td>
              <td>{{ formatShare(value) }}</td>
            </tr>
          </tbody>
        </table>

        <div class="results-cards">
          <article v-for="([label, value], index) in resultEntries" :key="`result-card-${label}-${index}`" class="result-card">
            <span>{{ label }}</span>
            <strong>{{ value }}</strong>
            <small>{{ formatShare(value) }}</small>
          </article>
        </div>

        <div class="chart-shell">
          <PieChart :counts="counts" />
        </div>
      </div>

      <div v-if="timeSeries.length" class="panel chart-panel chart-panel--wide">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Flow</p>
            <h3>Traffic Flow Over Time</h3>
          </div>
        </div>

        <TimeSeriesChart :time-series="timeSeries" :main-class-list="mainClassList" />
      </div>

      <InsightPanel :recommendations="recommendations" :gpt-recommendations="gptRecommendations" />

      <div class="panel media-panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Output</p>
            <h3>Annotated Video</h3>
          </div>
          <span class="section-chip" :class="videoToneClass">{{ videoStatusLabel }}</span>
        </div>

        <template v-if="annotatedUrl">
          <video
            :key="annotatedUrl"
            width="100%"
            controls
            preload="metadata"
            class="result-video"
            @loadedmetadata="videoState = 'ready'"
            @error="videoState = 'error'"
          >
            <source :src="annotatedUrl" type="video/mp4" />
            Your browser does not support the video tag.
          </video>
          <p v-if="videoState === 'error'" class="media-note media-note--error">
            Browser playback failed. The generated file may be missing, still unavailable, or encoded with an unsupported codec.
          </p>
          <p class="media-note">
            <a :href="annotatedUrl" target="_blank" rel="noopener">Open annotated video</a>
          </p>
        </template>

        <div v-else class="media-empty">
          Annotated output was not saved for this analysis.
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, ref, watch } from "vue";
import InsightPanel from "./InsightPanel.vue";

const ChartLoadingState = {
  template: `
    <div class="chart-loading-state">
      <div class="chart-loading-bar"></div>
      <p>Loading analytics visual...</p>
    </div>
  `,
};

const PieChart = defineAsyncComponent({
  loader: () => import("./PieChart.vue"),
  loadingComponent: ChartLoadingState,
  delay: 120,
});

const TimeSeriesChart = defineAsyncComponent({
  loader: () => import("./TimeSeriesChart.vue"),
  loadingComponent: ChartLoadingState,
  delay: 120,
});

const props = defineProps({
  counts: { type: Object, default: null },
  peak: { type: Object, default: null },
  recommendations: { type: Array, default: () => [] },
  gptRecommendations: { type: String, default: null },
  timeSeries: { type: Array, default: () => [] },
  mainClassList: { type: Array, default: () => [] },
  annotatedUrl: { type: String, default: null },
});

const videoState = ref("idle");

watch(
  () => props.annotatedUrl,
  (nextUrl) => {
    videoState.value = nextUrl ? "loading" : "missing";
  },
  { immediate: true }
);

const resultEntries = computed(() => Object.entries(props.counts || {}));
const totalVehicles = computed(() => resultEntries.value.reduce((sum, [, value]) => sum + Number(value || 0), 0));
const dominantEntry = computed(() => {
  return resultEntries.value.reduce((best, entry) => {
    if (!best || Number(entry[1] || 0) > Number(best[1] || 0)) {
      return entry;
    }
    return best;
  }, null);
});
const dominantClass = computed(() => dominantEntry.value?.[0] || "Not available");
const peakLabel = computed(() => {
  if (!props.peak) {
    return "Not available";
  }
  return `${props.peak.hour}:00 (${props.peak.count})`;
});
const unclassifiedShare = computed(() => {
  if (!totalVehicles.value) {
    return 0;
  }
  return Number(props.counts?.Unclassified || 0) / totalVehicles.value;
});
const qualityLabel = computed(() => {
  if (unclassifiedShare.value >= 0.25) {
    return "Needs review";
  }
  if (unclassifiedShare.value >= 0.1) {
    return "Moderate";
  }
  return "Strong";
});
const qualityToneClass = computed(() => {
  if (unclassifiedShare.value >= 0.25) {
    return "kpi-card--warning";
  }
  if (unclassifiedShare.value >= 0.1) {
    return "kpi-card--watch";
  }
  return "kpi-card--good";
});
const audienceSummary = computed(() => {
  if (!dominantEntry.value || !totalVehicles.value) {
    return "No audience signal";
  }
  return `${formatShare(dominantEntry.value[1])} ${dominantEntry.value[0]}`;
});
const videoStatusLabel = computed(() => {
  if (!props.annotatedUrl) {
    return "Not saved";
  }
  if (videoState.value === "error") {
    return "Playback issue";
  }
  if (videoState.value === "ready") {
    return "Ready";
  }
  return "Loading";
});
const videoToneClass = computed(() => {
  if (!props.annotatedUrl) {
    return "section-chip--muted";
  }
  if (videoState.value === "error") {
    return "section-chip--warning";
  }
  if (videoState.value === "ready") {
    return "section-chip--good";
  }
  return "";
});

function formatShare(value) {
  if (!totalVehicles.value) {
    return "0%";
  }
  return `${Math.round((Number(value || 0) / totalVehicles.value) * 100)}%`;
}
</script>

<style scoped>
.results-dashboard {
  display: grid;
  gap: 1.5rem;
}

.results-band,
.panel {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 1.5rem;
  box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
}

.results-band {
  padding: 1.5rem;
  display: grid;
  gap: 1.25rem;
}

.results-band h2,
.section-heading h3 {
  margin: 0;
}

.eyebrow {
  margin: 0 0 0.45rem;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0ea5e9;
}

.kpi-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}

.kpi-card,
.result-card,
.media-empty {
  border-radius: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  background: #f8fafc;
}

.kpi-card {
  padding: 1rem;
}

.kpi-card span,
.result-card span {
  display: block;
  color: #64748b;
  font-size: 0.9rem;
  margin-bottom: 0.3rem;
}

.kpi-card strong,
.result-card strong {
  color: #0f172a;
  font-size: 1.08rem;
}

.kpi-card--good {
  border-color: rgba(16, 185, 129, 0.32);
  background: rgba(16, 185, 129, 0.08);
}

.kpi-card--watch {
  border-color: rgba(245, 158, 11, 0.32);
  background: rgba(245, 158, 11, 0.1);
}

.kpi-card--warning {
  border-color: rgba(220, 38, 38, 0.28);
  background: rgba(220, 38, 38, 0.08);
}

.results-layout {
  display: grid;
  gap: 1.5rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}

.panel {
  padding: 1.5rem;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 1.25rem;
}

.section-chip {
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
  background: rgba(14, 165, 233, 0.12);
  color: #075985;
  font-weight: 800;
  font-size: 0.82rem;
  white-space: nowrap;
}

.section-chip--good {
  background: rgba(16, 185, 129, 0.14);
  color: #166534;
}

.section-chip--warning {
  background: rgba(220, 38, 38, 0.12);
  color: #991b1b;
}

.section-chip--muted {
  background: #e2e8f0;
  color: #475569;
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1.25rem;
}

.results-table th,
.results-table td {
  padding: 0.8rem 0.65rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.95);
  text-align: left;
}

.results-table th {
  background: rgba(14, 165, 233, 0.08);
}

.results-cards {
  display: none;
}

.result-card {
  padding: 0.9rem 1rem;
}

.result-card small {
  display: block;
  margin-top: 0.25rem;
  color: #64748b;
}

.chart-shell {
  min-height: 260px;
}

:deep(.chart-loading-state) {
  min-height: 260px;
  display: grid;
  place-items: center;
  gap: 0.8rem;
  color: #475569;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), rgba(241, 245, 249, 0.82));
  border-radius: 1rem;
}

:deep(.chart-loading-bar) {
  width: min(280px, 78%);
  height: 0.8rem;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.18), rgba(245, 158, 11, 0.32), rgba(14, 165, 233, 0.18));
  background-size: 200% 100%;
  animation: shimmer 1.2s linear infinite;
}

.chart-panel--wide,
.media-panel {
  grid-column: 1 / -1;
}

.result-video {
  width: 100%;
  border-radius: 1rem;
  overflow: hidden;
  background: #020617;
}

.media-note {
  margin: 0.85rem 0 0;
  color: #475569;
  line-height: 1.5;
}

.media-note--error {
  color: #991b1b;
}

.media-note a {
  color: #0284c7;
  font-weight: 700;
}

.media-empty {
  padding: 1rem;
  color: #475569;
}

@keyframes shimmer {
  from {
    background-position: 0% 0;
  }
  to {
    background-position: 200% 0;
  }
}

@media (max-width: 980px) {
  .results-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .results-band,
  .panel {
    padding: 1.15rem;
  }

  .section-heading {
    flex-direction: column;
  }

  .results-table {
    display: none;
  }

  .results-cards {
    display: grid;
    gap: 0.8rem;
    margin-bottom: 1.1rem;
  }
}
</style>
