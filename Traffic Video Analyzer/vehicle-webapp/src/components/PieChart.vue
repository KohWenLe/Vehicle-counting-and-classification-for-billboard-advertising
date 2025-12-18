<template>
    <Pie v-if="chartData" :data="chartData" :options="options" />
  </template>
  
  <script setup>
  import { Pie } from 'vue-chartjs'
  import { computed } from 'vue'
  
  const props = defineProps({
    counts: Object // e.g. { "High-End Vehicles": 15, ... }
  })
  
  const chartData = computed(() => ({
    labels: Object.keys(props.counts || {}),
    datasets: [{
      label: 'Vehicle Distribution',
      data: Object.values(props.counts || {}),
      backgroundColor: [
        '#6366f1', '#f59e42', '#10b981', '#ef4444', '#fbbf24', '#a3e635'
      ]
    }]
  }))
  
  const options = {
    responsive: true,
    plugins: {
      legend: { position: 'bottom' }
    }
  }
  </script>
  