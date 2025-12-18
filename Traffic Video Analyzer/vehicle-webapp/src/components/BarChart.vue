<template>
    <Bar v-if="chartData" :data="chartData" :options="options" />
</template>

<script setup>
import { Bar } from 'vue-chartjs'
import { computed } from 'vue';

const props = defineProps({
    counts: Object // { "High-End": 15, ... }
})

const chartData = computed(() => ({
  labels: Object.keys(props.counts || {}),
  datasets: [{
    label: 'Vehicle Count',
    data: Object.values(props.counts || {}),
    backgroundColor: ['#6366f1', '#f59e42', '#10b981', '#ef4444', '#fbbf24', '#a3e635']
  }]
}))

const options = {
    responsive: true,
    plugins: {
    legend: { display: false }
    }
}
</script>
  