<template>
  <section v-if="notifications.length" class="toast-stack" aria-live="polite" aria-label="Notifications">
    <article
      v-for="notification in notifications"
      :key="notification.id"
      class="toast-card"
      :class="`toast-card--${notification.tone}`"
    >
      <div class="toast-copy">
        <strong>{{ notification.title }}</strong>
        <p>{{ notification.message }}</p>
      </div>
      <button
        type="button"
        class="dismiss-btn"
        :aria-label="`Dismiss ${notification.title}`"
        @click="$emit('dismiss', notification.id)"
      >
        ×
      </button>
    </article>
  </section>
</template>

<script setup>
defineProps({
  notifications: {
    type: Array,
    default: () => [],
  },
});

defineEmits(["dismiss"]);
</script>

<style scoped>
.toast-stack {
  position: sticky;
  top: 1rem;
  z-index: 30;
  display: grid;
  gap: 0.8rem;
}

.toast-card {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  padding: 1rem 1.05rem;
  border-radius: 1rem;
  border: 1px solid transparent;
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(12px);
}

.toast-card--info {
  background: rgba(14, 165, 233, 0.12);
  border-color: rgba(14, 165, 233, 0.22);
  color: #0f3d4c;
}

.toast-card--success {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.22);
  color: #14532d;
}

.toast-card--warning {
  background: rgba(245, 158, 11, 0.14);
  border-color: rgba(245, 158, 11, 0.24);
  color: #92400e;
}

.toast-card--error {
  background: rgba(220, 38, 38, 0.12);
  border-color: rgba(220, 38, 38, 0.24);
  color: #7f1d1d;
}

.toast-copy strong {
  display: block;
  margin-bottom: 0.2rem;
}

.toast-copy p {
  margin: 0;
  line-height: 1.5;
}

.dismiss-btn {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
</style>
