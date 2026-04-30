<template>
  <section class="history-panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Archive</p>
        <h3>Analysis History</h3>
        <p class="panel-copy">
          Review earlier traffic studies without loading the full history table into the browser.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost-btn" @click="$emit('toggle')">
          {{ visible ? "Hide History" : "Show History" }}
        </button>
        <button
          v-if="visible"
          type="button"
          class="secondary-btn"
          :disabled="isLoading"
          @click="$emit('refresh')"
        >
          Refresh
        </button>
      </div>
    </div>

    <div v-if="visible" class="history-content">
      <form class="history-filters" @submit.prevent="submitFilters">
        <label>
          Analysis Name
          <input v-model.trim="localAnalysisName" type="text" placeholder="Search by study name" />
        </label>
        <label>
          Date From
          <input v-model="localDateFrom" type="date" />
        </label>
        <label>
          Date To
          <input v-model="localDateTo" type="date" />
        </label>
        <div class="filter-actions">
          <button type="submit" class="primary-btn">Apply Filters</button>
          <button type="button" class="ghost-btn" @click="resetFilters">Clear</button>
        </div>
      </form>

      <div v-if="error" class="state-card state-card--error">{{ error }}</div>
      <div v-else-if="isLoading" class="state-card">Loading recent analyses...</div>
      <div v-else-if="!entries.length" class="state-card">
        {{ hasLoaded ? "No analyses match the current filters." : "Open history to load recent analyses." }}
      </div>

      <template v-else>
        <div class="history-meta">
          <span>Showing {{ entries.length }} of {{ total }} analyses</span>
          <span>Page {{ currentPage }} of {{ totalPages }}</span>
        </div>

        <div class="table-shell table-shell--desktop">
          <table class="history-table">
            <thead>
              <tr>
                <th>Analysis Name</th>
                <th>Date/Time</th>
                <th>Counts</th>
                <th>Peak Hour</th>
                <th>Recommendations</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in entries" :key="item.id">
                <td>{{ item.analysis_name || "Untitled Analysis" }}</td>
                <td>{{ formatDate(item.timestamp) }}</td>
                <td>
                  <ul class="compact-list">
                    <li v-for="([label, count], index) in Object.entries(item.counts || {})" :key="`${item.id}-count-${index}`">
                      {{ label }}: {{ count }}
                    </li>
                  </ul>
                </td>
                <td>{{ item.peak_hour }} ({{ item.peak_count }} vehicles)</td>
                <td>
                  <ul class="compact-list">
                    <li v-for="(recommendation, index) in normalizeRecommendations(item.recommendations)" :key="`${item.id}-rec-${index}`">
                      {{ recommendation }}
                    </li>
                  </ul>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="history-cards">
          <article v-for="item in entries" :key="`mobile-${item.id}`" class="history-card">
            <div class="history-card__header">
              <h4>{{ item.analysis_name || "Untitled Analysis" }}</h4>
              <p>{{ formatDate(item.timestamp) }}</p>
            </div>

            <div class="history-card__section">
              <span>Vehicle Counts</span>
              <ul class="compact-list">
                <li v-for="([label, count], index) in Object.entries(item.counts || {})" :key="`mobile-${item.id}-count-${index}`">
                  {{ label }}: {{ count }}
                </li>
              </ul>
            </div>

            <div class="history-card__section">
              <span>Peak Hour</span>
              <strong>{{ item.peak_hour }} ({{ item.peak_count }} vehicles)</strong>
            </div>

            <div class="history-card__section">
              <span>Recommendations</span>
              <ul class="compact-list">
                <li
                  v-for="(recommendation, index) in normalizeRecommendations(item.recommendations)"
                  :key="`mobile-${item.id}-rec-${index}`"
                >
                  {{ recommendation }}
                </li>
              </ul>
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
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  entries: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  error: { type: String, default: null },
  hasLoaded: { type: Boolean, default: false },
  limit: { type: Number, default: 5 },
  offset: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  filters: {
    type: Object,
    default: () => ({
      analysisName: "",
      dateFrom: "",
      dateTo: "",
    }),
  },
});

const emit = defineEmits(["toggle", "refresh", "apply-filters", "prev-page", "next-page"]);

const localAnalysisName = ref(props.filters.analysisName || "");
const localDateFrom = ref(props.filters.dateFrom || "");
const localDateTo = ref(props.filters.dateTo || "");

watch(
  () => props.filters,
  (nextFilters) => {
    localAnalysisName.value = nextFilters.analysisName || "";
    localDateFrom.value = nextFilters.dateFrom || "";
    localDateTo.value = nextFilters.dateTo || "";
  },
  { deep: true }
);

const currentPage = computed(() => Math.floor(props.offset / props.limit) + 1);
const totalPages = computed(() => Math.max(1, Math.ceil((props.total || 0) / props.limit)));

function submitFilters() {
  emit("apply-filters", {
    analysisName: localAnalysisName.value,
    dateFrom: localDateFrom.value,
    dateTo: localDateTo.value,
  });
}

function resetFilters() {
  localAnalysisName.value = "";
  localDateFrom.value = "";
  localDateTo.value = "";
  submitFilters();
}

function formatDate(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function normalizeRecommendations(recommendations) {
  if (Array.isArray(recommendations)) {
    return recommendations;
  }
  if (typeof recommendations === "string" && recommendations.trim()) {
    return [recommendations.trim()];
  }
  return ["No recommendation summary saved."];
}
</script>

<style scoped>
.history-panel {
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

.header-actions,
.filter-actions,
.pagination-controls {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.history-content {
  margin-top: 1.5rem;
  display: grid;
  gap: 1rem;
}

.history-filters {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  align-items: end;
}

.history-filters label {
  display: grid;
  gap: 0.45rem;
  font-weight: 600;
  color: #334155;
}

.history-filters input {
  min-height: 2.7rem;
  padding: 0.75rem 0.9rem;
  border-radius: 0.9rem;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: #f8fafc;
  color: #0f172a;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  color: #475569;
  font-size: 0.95rem;
}

.table-shell {
  overflow-x: auto;
}

.history-cards {
  display: none;
}

.history-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}

.history-table th,
.history-table td {
  padding: 0.85rem 0.8rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.95);
  text-align: left;
  vertical-align: top;
}

.history-table th {
  color: #0f172a;
  background: rgba(14, 165, 233, 0.08);
}

.compact-list {
  margin: 0;
  padding-left: 1rem;
  display: grid;
  gap: 0.25rem;
}

.history-card {
  border-radius: 1rem;
  padding: 1rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92), rgba(255, 255, 255, 0.95));
  display: grid;
  gap: 0.9rem;
}

.history-card__header h4 {
  margin: 0;
  color: #0f172a;
}

.history-card__header p {
  margin: 0.3rem 0 0;
  color: #64748b;
  font-size: 0.92rem;
}

.history-card__section span {
  display: block;
  margin-bottom: 0.35rem;
  font-size: 0.88rem;
  color: #64748b;
}

.history-card__section strong {
  color: #0f172a;
}

.state-card {
  border-radius: 1rem;
  padding: 1rem 1.1rem;
  background: #f8fafc;
  color: #475569;
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
  background: #f59e0b;
  color: #111827;
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
  .panel-header {
    flex-direction: column;
  }

  .history-panel {
    padding: 1.15rem;
  }

  .table-shell--desktop {
    display: none;
  }

  .history-cards {
    display: grid;
    gap: 0.9rem;
  }
}
</style>
