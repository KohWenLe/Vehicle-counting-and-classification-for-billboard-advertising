import { createApp } from 'vue'
import App from './App.vue'
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);
import zoomPlugin from 'chartjs-plugin-zoom'
Chart.register(zoomPlugin)

createApp(App).mount('#app')
