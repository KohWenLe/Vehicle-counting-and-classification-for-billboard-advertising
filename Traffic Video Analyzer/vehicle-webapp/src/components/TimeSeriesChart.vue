<template>
    <Line v-if="chartData" :data="chartData" :options="options" />
</template>
<script setup>
import { Line } from 'vue-chartjs'
import { computed } from 'vue'
  
const props = defineProps({ timeSeries: Array, mainClassList: Array })
  
const chartData = computed(() => {
    const labels = props.timeSeries.map(entry => entry.timestamp);
    const datasets = props.mainClassList.map(cls => ({
      label: cls,
      data: props.timeSeries.map(entry => entry[cls] || 0),
      borderWidth: 2
    }));
    return { labels, datasets }
});
const options = {
  responsive: true,
  plugins: {
    legend: { display: true, position: 'bottom' },
    zoom: {
        pan: { enabled: true, mode: 'x' },
        zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }
    }
  },
  scales: {
    x: {
      title: { display: true, text: 'Time' },
      ticks: {
        autoSkip: true,
        maxTicksLimit: 8, // show at most 8 x-axis labels
        callback: function(val) {
          // Format timestamp label to HH:MM (from "YYYY-MM-DD HH:MM:SS")
          const label = this.getLabelForValue(val);
          if (!label) return '';
          const parts = label.split(' ');
          return parts[1] ? parts[1].slice(0, 5) : label;
        },
        maxRotation: 45,
        minRotation: 30
      }
    },
    y: {
      title: { display: true, text: 'Vehicle Count' }
    }
  }
};

</script>
  