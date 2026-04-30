<template>
  <section v-if="busy || message || error" class="status-stack">
    <div v-if="busy" class="status-card status-card--busy">
      <div class="spinner" aria-hidden="true"></div>
      <div class="status-copy">
        <strong>Analysis Running</strong>
        <p>{{ message || "Preparing your traffic analytics job." }}</p>
      </div>
    </div>

    <div v-else-if="message" class="status-card status-card--info">
      <div class="status-copy">
        <strong>Job Update</strong>
        <p>{{ message }}</p>
      </div>
    </div>

    <div v-if="showProgress" class="progress-shell">
      <div class="progress-bar" :style="{ width: `${progressPercent}%` }"></div>
    </div>
    <div v-if="showProgress" class="progress-label">{{ progressPercent }}% complete</div>

    <div v-if="error" class="status-card status-card--error">
      <div class="status-copy">
        <strong>Something Needs Attention</strong>
        <p>{{ error }}</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  busy: { type: Boolean, default: false },
  message: { type: String, default: null },
  progressPercent: { type: Number, default: null },
  error: { type: String, default: null },
});

const showProgress = computed(() => typeof props.progressPercent === "number");
</script>

<style scoped>
.status-stack {
  display: grid;
  gap: 0.75rem;
}

.status-card {
  border-radius: 1rem;
  padding: 1rem 1.1rem;
  display: flex;
  align-items: center;
  gap: 0.9rem;
  border: 1px solid transparent;
}

.status-card--busy,
.status-card--info {
  background: rgba(14, 165, 233, 0.08);
  border-color: rgba(14, 165, 233, 0.18);
  color: #0f3d4c;
}

.status-card--error {
  background: rgba(220, 38, 38, 0.08);
  border-color: rgba(220, 38, 38, 0.18);
  color: #7f1d1d;
}

.status-copy strong {
  display: block;
  margin-bottom: 0.15rem;
}

.status-copy p {
  margin: 0;
  line-height: 1.5;
}

.spinner {
  width: 1.1rem;
  height: 1.1rem;
  border: 3px solid rgba(12, 74, 110, 0.15);
  border-top-color: #0ea5e9;
  border-radius: 999px;
  animation: spin 0.9s linear infinite;
  flex-shrink: 0;
}

.progress-shell {
  width: 100%;
  height: 0.8rem;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(14, 165, 233, 0.12);
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #f59e0b 0%, #0ea5e9 100%);
  transition: width 0.25s ease;
}

.progress-label {
  color: #475569;
  font-size: 0.92rem;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
