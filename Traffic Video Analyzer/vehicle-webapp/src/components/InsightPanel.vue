<template>
  <section v-if="items.length" class="insight-card">
    <div class="insight-header">
      <div>
        <p class="eyebrow">Guidance</p>
        <h3>Insights and Recommendations</h3>
      </div>
      <span class="source-chip">{{ sourceLabel }}</span>
    </div>

    <ul class="insight-list">
      <li v-for="(item, index) in items" :key="`insight-${index}`">
        {{ item }}
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  recommendations: { type: Array, default: () => [] },
  gptRecommendations: { type: [String, Array], default: null },
});

const items = computed(() => {
  if (Array.isArray(props.gptRecommendations) && props.gptRecommendations.length) {
    return props.gptRecommendations.map((item) => String(item).trim()).filter(Boolean);
  }

  if (typeof props.gptRecommendations === "string" && props.gptRecommendations.trim()) {
    return props.gptRecommendations
      .split(/\n+/)
      .map((item) => item.replace(/^[*\-•\d.\s]+/, "").trim())
      .filter(Boolean);
  }

  return (props.recommendations || []).map((item) => String(item).trim()).filter(Boolean);
});

const sourceLabel = computed(() => {
  if (props.gptRecommendations) {
    return "AI Narrative";
  }
  return "Rule-Based Summary";
});
</script>

<style scoped>
.insight-card {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 1.5rem;
  padding: 1.4rem;
  box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
}

.insight-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1rem;
}

.eyebrow {
  margin: 0 0 0.3rem;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #f59e0b;
}

.insight-header h3 {
  margin: 0;
  color: #0f172a;
}

.source-chip {
  padding: 0.45rem 0.8rem;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.14);
  color: #92400e;
  font-weight: 700;
  font-size: 0.82rem;
}

.insight-list {
  margin: 0;
  padding-left: 1.2rem;
  display: grid;
  gap: 0.65rem;
  color: #334155;
  line-height: 1.65;
}

@media (max-width: 720px) {
  .insight-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
