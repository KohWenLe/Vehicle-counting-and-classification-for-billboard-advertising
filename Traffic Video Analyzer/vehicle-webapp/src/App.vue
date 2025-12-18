<template>
  <div class="app-container">
    <div class="card">
      <h2 class="title">🚗 Vehicle Video Analyzer</h2>

      <button class="history-btn" @click="toggleHistory">
        {{ historyVisible ? "Hide" : "Show" }} Analysis History
      </button>

      <div v-if="historyVisible && history.length" class="history-section">
        <h3>Analysis History</h3>
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
            <tr v-for="item in paginatedHistory" :key="item.id">
              <td>{{ item.analysis_name || 'N/A' }}</td>
              <td>{{ formatDate(item.timestamp) }}</td>
              <td>
                <ul>
                  <li v-for="(v, k) in item.counts" :key="k">{{ k }}: {{ v }}</li>
                </ul>
              </td>
              <td>{{ item.peak_hour }} ({{ item.peak_count }} vehicles)</td>
              <td>
                <ul>
                  <li v-for="rec in item.recommendations" :key="rec">{{ rec }}</li>
                </ul>
              </td>
            </tr>
          </tbody>
        </table>
        <!-- Pagination controls -->
        <div v-if="totalPages > 1" class="pagination-controls">
          <button @click="currentPage = Math.max(1, currentPage - 1)" :disabled="currentPage === 1">Prev</button>
          <span style="margin: 0 8px;">Page {{ currentPage }} / {{ totalPages }}</span>
          <button @click="currentPage = Math.min(totalPages, currentPage + 1)" :disabled="currentPage === totalPages">Next</button>
        </div>
      </div>


      <label>
        Video Start Date (optional):
        <input type="date" v-model="startDate">
      </label>

      <label>
        Start Time (HH:MM) (optional):
        <input type="time" v-model="startTime">
      </label>

      <label>
        Save analysis record as:
        <input type="text" v-model="outputFileName" placeholder="(Optional) analysis name" />
      </label>

      <div>
        <label>
          <input type="radio" value="upload" v-model="sourceType" /> Upload Video
        </label>
        <label>
          <input type="radio" value="camera_url" v-model="sourceType" /> Use Camera/IP URL
        </label>
      </div>
      <!-- If Upload is chosen -->
      <label v-if="sourceType === 'upload'" class="file-label">
        <input v-if="sourceType === 'upload'" type="file" @change="onFileChange" accept="video/*" />
        <span v-if="sourceType === 'upload'">Select video file…</span>
      </label>
      <!-- If Camera URL is chosen -->
      <input v-if="sourceType === 'camera_url'" type="text" v-model="cameraUrl" placeholder="rtsp://..., http://..., or webcam index (0)" />

      <!-- test -->
      <!-- <button @click="loadTestData" class="test-btn">Load Test Chart Data</button> -->

      <button class="analyze-btn" @click="upload" :disabled="!canAnalyze">
        {{ isUploading ? 'Analyzing...' : 'Analyze Video' }}
      </button>
      <button v-if="isUploading" @click="cancelAnalysis" class="cancel-btn">Cancel</button>

      <div class="spinner" v-if="isUploading"></div>
      <div v-if="errorMsg" class="error">{{ errorMsg }}</div>

      <div v-if="result" class="results-card">
        <h3>Analysis Results</h3>
        <table class="results-table">
          <thead>
            <tr>
              <th>Class</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(val, key) in result" :key="key">
              <td>{{ key }}</td>
              <td>{{ val }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pie chart for class distribution -->
      <div v-if="result">
        <h3>Vehicle Class Distribution</h3>
        <!-- <BarChart :counts="result" /> -->
        <PieChart :counts="result" />
      </div>

      <!-- Time series line chart -->
      <div v-if="timeSeries && timeSeries.length">
        <h3>Time-Series (Vehicle Count over Time)</h3>
        <TimeSeriesChart :timeSeries="timeSeries" :mainClassList="mainClassList" />
      </div>

      <div v-if="peak">
        <h4>Peak Hour</h4>
        <div>
          Peak hour: {{ peak.hour }}:00 ({{ peak.count }} vehicles)
        </div>
      </div>

      <!-- <button @click="loadGptTest" class="test-btn">Test GPT Analysis Only</button> -->
      <div v-if="insightToShow" class="insight-card">
        <h3 class="insight-title">Insights and Recommendations</h3>
        <div class="insight-content" v-html="formatInsightText(insightToShow)"></div>
      </div>

      <video v-if="annotatedUrl" width="100%" controls class="result-video">
        <source :src="annotatedUrl" type="video/mp4" />
        Your browser does not support the video tag.
      </video>
    </div>
  </div>
</template>

<script>
import axios from "axios";
// import BarChart from './components/BarChart.vue'
import PieChart from './components/PieChart.vue'
import TimeSeriesChart from './components/TimeSeriesChart.vue'

export default {
  data() {
    return {
      startDate: "",
      startTime: "",
      sourceType: 'upload',
      cameraUrl: "",
      video: null,
      cancelSource: null,
      result: null,
      peak: null,
      recommendations: [],
      timeSeries: [],
      isUploading: false,
      errorMsg: null,
      annotatedUrl: null,
      outputFileName: "",
      mainClassList: [
        "Commercial Vehicles",
        "High-End Vehicles",
        "Low-End Vehicles",
        "Mid-Range Vehicles",
        "Motorcycle",
        "Unclassified"
      ],
      history: [],
      historyVisible: false,     // To toggle display
      currentPage: 1,           // For pagination
      recordsPerPage: 5,        // Items per page
      gpt_recommendations: null,
    };
  },
  components: { PieChart,  TimeSeriesChart }, //BarChart
  methods: {
    loadTestData() {
      this.result = {
        "Commercial Vehicles": 10,
        "High-End Vehicles": 12,
        "Low-End Vehicles": 8,
        "Mid-Range Vehicles": 15,
        "Motorcycle": 5,
        "Unclassified": 3
      };
      this.timeSeries = [
        {"timestamp": "2024-06-12 09:00:00", "Commercial Vehicles": 2, "High-End Vehicles": 3, "Low-End Vehicles": 1, "Mid-Range Vehicles": 4, "Motorcycle": 1, "Unclassified": 0},
        {"timestamp": "2024-06-12 10:00:00", "Commercial Vehicles": 3, "High-End Vehicles": 2, "Low-End Vehicles": 3, "Mid-Range Vehicles": 5, "Motorcycle": 2, "Unclassified": 1},
        {"timestamp": "2024-06-12 11:00:00", "Commercial Vehicles": 5, "High-End Vehicles": 7, "Low-End Vehicles": 4, "Mid-Range Vehicles": 6, "Motorcycle": 2, "Unclassified": 2}
      ];
      this.peak = {hour: 11, count: 24};
      this.recommendations = [
        "Most detected vehicles are 'Mid-Range Vehicles' (15 vehicles, 28.3% of classified). Recommended ads: Popular brands, family cars, household electronics, family insurance.",
        "Very few 'Motorcycle' vehicles detected (5). Ads targeting this group may be less effective.",
        "Peak detected traffic is at 11:00 (24 vehicles/hour). Show high-impact ads during this period for maximum reach."
      ];
      console.log("Loaded test data:", this.result, this.timeSeries);
    },
    onFileChange(e) {
      this.video = e.target.files[0]; 
      this.result = null;
      this.annotatedUrl = null;
      this.errorMsg = null;
    },
    async upload() {
      console.log("Upload called. sourceType:", this.sourceType, "video:", this.video, "cameraUrl:", this.cameraUrl);
      this.cancelSource = axios.CancelToken.source();
      this.isUploading = true;
      this.errorMsg = null;
      this.result = null;
      let formData = new FormData();
      // Always send date/time for consistent API
      formData.append("start_date", this.startDate);
      formData.append("start_time", this.startTime);
      
      if (!this.outputFileName) {
        // Generate a simple default name
        const now = new Date();
        const date = now.toISOString().slice(0,10);
        const time = now.toTimeString().slice(0,5).replace(':','-');
        this.outputFileName = `analysis_${date}_${time}`;
      }

      if (this.sourceType === "upload") {
        if (!this.video) {
          this.isUploading = false;
          this.errorMsg = "Please provide a video file or record with webcam.";
          return;
        }
        formData.append("video", this.video);
      } else if (this.sourceType === "camera_url") {
        if (!this.cameraUrl.trim()) {
          this.isUploading = false;
          this.errorMsg = "Please enter a camera URL or index.";
          return;
        }
        formData.append("camera_url", this.cameraUrl);
      }

      try {
        let res = await axios.post("/analyze", formData, { cancelToken: this.cancelSource.token });
        // Store each field
        this.result = res.data.counts || null;
        this.peak = res.data.peak || null;
        this.recommendations = [].concat(res.data.recommendations || []);
        this.gpt_recommendations = res.data.gpt_recommendations || null;
        this.timeSeries = res.data.time_series || [];
        // Annotated video support
        if (res.data.annotated_video) {
          this.annotatedUrl = "/output/" + res.data.annotated_video.split("/").pop();
        }
      } catch (err) {
        if (axios.isCancel(err)) {
          this.errorMsg = "Analysis canceled by user.";
        } else {
        this.errorMsg = err.response?.data?.error || err.message || "Upload failed";
        }
      }
      this.isUploading = false;
      this.cancelSource = null;
    },
    async toggleHistory() {
      // Only fetch if not yet loaded
      if (!this.history.length) {
        try {
          const res = await fetch('/history');
          if (!res.ok) throw new Error('Failed to fetch history');
          this.history = await res.json();
        } catch (err) {
          alert('Could not load history: ' + err.message);
          return;
        }
      }
      this.historyVisible = !this.historyVisible;
      // Reset to first page every time it is shown (optional)
      if (this.historyVisible) {
        this.currentPage = 1;
      }
    },
    formatDate(dt) {
      if (!dt) return '';
      const date = new Date(dt);
      return date.toLocaleString();
    },
    cancelAnalysis() {
      if (this.cancelSource) {
        this.cancelSource.cancel("User canceled the analysis.");
      }
      this.isUploading = false;
    },
    async loadGptTest() { 
      try {
        const res = await fetch('/test_gpt_analysis');
        const data = await res.json();
        this.gpt_recommendations = data.gpt_recommendations;
      } catch (err) {
        this.gpt_recommendations = "Error loading GPT analysis: " + err.message;
      }
    },
    formatInsightText(text) {
      // Same formatting for both GPT and local analysis
      let html = text
        .replace(/• /g, '<br><b>• </b>')         // Bold bullet points
        .replace(/\d+\./g, match => `<br>&nbsp;&nbsp;${match}`); // Numbered items
      html = html.replace(/\n\n/g, '<br><br>');
      html = html.replace(/\n/g, '<br>');        // Single newlines as <br>
      return html;
    },
  },
  computed: {
    canAnalyze() {
      if (this.isUploading) return false;
      if (this.sourceType === 'upload') {
        return !!this.video;
      }
      if (this.sourceType === 'camera_url') {
        return !!this.cameraUrl;
      }
      return false;
    },
    insightToShow() {
      // Prefer GPT if available, else use recommendations from analysis.py
      if (this.gpt_recommendations) {
        return this.gpt_recommendations;
      } else if (this.recommendations && this.recommendations.length) {
        // Join array into text for formatting
        return this.recommendations.join('\n');
      }
      return null;
    },
    paginatedHistory() {
      const start = (this.currentPage - 1) * this.recordsPerPage;
      return this.history.slice(start, start + this.recordsPerPage);
    },
    totalPages() {
      return Math.ceil(this.history.length / this.recordsPerPage);
    }
  }
};
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');

.app-container {
  min-height: 100vh;
  background: #f7fafc;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-family: 'Inter', sans-serif;
  padding: 40px 0;
}

/* Card Layout */
.card {
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 8px 32px 0 rgba(31, 41, 55, 0.09);
  padding: 32px 30px 30px 30px;
  max-width: 60%;
  width: 100%;
  margin: 28px auto;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

/* Title */
.title {
  text-align: center;
  font-size: 2rem;
  margin-bottom: 22px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.03em;
}

/* Input labels and fields */
label {
  font-weight: 500;
  display: block;
  margin-bottom: 10px;
  color: #374151;
  letter-spacing: 0.3px;
}
input[type="date"],
input[type="time"],
input[type="text"] {
  margin-left: 8px;
  padding: 8px 10px;
  font-size: 1em;
  border: 1.5px solid #d1d5db;
  border-radius: 7px;
  background: #f9fafb;
  margin-bottom: 16px;
  transition: border 0.2s;
}
input[type="date"]:focus,
input[type="time"]:focus,
input[type="text"]:focus {
  border-color: #6366f1;
  outline: none;
}

/* File input */
.file-label {
  background: #f1f5f9;
  border-radius: 7px;
  padding: 18px 12px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 2px dashed #a0aec0;
  font-size: 1rem;
  color: #334155;
  transition: border-color 0.2s;
}
.file-label:hover {
  border-color: #6366f1;
}
.file-label input[type="file"] {
  display: none;
}

/* Buttons */
.analyze-btn, .test-btn, .history-btn, .cancel-btn {
  background: linear-gradient(90deg, #6366f1 0%, #60a5fa 100%);
  color: white;
  font-weight: 600;
  padding: 11px 20px;
  margin: 12px 7px 16px 0;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  letter-spacing: 0.2px;
  font-size: 1em;
  transition: background 0.18s, box-shadow 0.18s;
  box-shadow: 0 2px 6px rgba(99,102,241,0.08);
}
.analyze-btn[disabled] {
  background: #cbd5e1;
  cursor: not-allowed;
}
.cancel-btn {
  background: #ef4444;
  background-image: none;
}
.history-btn {
  background: #0ea5e9;
  background-image: none;
}
.test-btn {
  background: #10b981;
  background-image: none;
}

/* Spinner */
.spinner {
  border: 4px solid #f1f5f9;
  border-top: 4px solid #6366f1;
  border-radius: 50%;
  width: 32px;
  height: 32px;
  margin: 0 auto 18px auto;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error message */
.error {
  color: #ef4444;
  margin-bottom: 16px;
  text-align: center;
  background: #fff0f0;
  border: 1.2px solid #ef4444;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 1.04em;
}

/* Results card */
.results-card {
  background: #f8fafc;
  border-radius: 10px;
  padding: 18px 10px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(30,41,59,0.05);
}

.results-table, .history-table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 auto;
  font-size: 0.99em;
}
.results-table th, .results-table td,
.history-table th, .history-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
}
.results-table th,
.history-table th {
  font-weight: 700;
  background: #e0e7ef;
  letter-spacing: 0.15px;
}
.results-table tr:last-child td,
.history-table tr:last-child td {
  border-bottom: none;
}

.history-section {
  margin: 30px 0 28px 0;
  background: #f9fafb;
  border-radius: 16px;
  box-shadow: 0 2px 8px rgba(30,41,59,0.04);
  padding: 19px 10px 19px 10px;
}

/* Video preview */
.result-video {
  border-radius: 10px;
  margin-top: 12px;
  box-shadow: 0 2px 8px rgba(30,41,59,0.04);
}

.pagination-controls {
  text-align: center;
  margin-top: 10px;
}

.pagination-controls button {
  background: #6366f1;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 6px 15px;
  margin: 0 4px;
  font-size: 1em;
  cursor: pointer;
}

.pagination-controls button[disabled] {
  background: #d1d5db;
  color: #9ca3af;
  cursor: not-allowed;
}

.insight-card {
  background: #f8fafc;
  border-radius: 13px;
  padding: 22px 18px 18px 18px;
  margin: 28px 0 16px 0;
  box-shadow: 0 2px 12px rgba(99,102,241,0.07);
  max-width: 700px;
  width: 100%;
  display: block;
}

.insight-title {
  font-size: 1.35rem;
  font-weight: 600;
  color: #3b4252;
  margin-bottom: 10px;
  letter-spacing: 0.04em;
}

.insight-content {
  font-size: 1.06em;
  color: #22223b;
  line-height: 1.7;
}

.insight-content b {
  color: #6366f1;
}

.insight-content ul, .insight-content ol {
  margin-left: 25px;
  margin-bottom: 0.7em;
}

.insight-content br {
  margin-bottom: 4px;
}

/* Responsive for mobile */
@media (max-width: 900px) {
  .card {
    max-width: 99vw;
    padding: 18px 6vw 22px 6vw;
  }
  .insight-card {
    max-width: 99vw;
    padding: 18px 6vw 22px 6vw;
  }
  .history-section, .results-card {
    padding: 10px 3vw;
  }
}
@media (max-width: 600px) {
  .card { max-width: 100%; padding: 12px 2vw; }
  .results-table, .history-table { font-size: 0.98em; }
}

</style>

