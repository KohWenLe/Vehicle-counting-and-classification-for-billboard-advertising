<template>
  <div class="app-shell">
    <main class="app-frame">
      <NotificationStack :notifications="notifications" @dismiss="dismissNotification" />

      <section class="hero-panel">
        <div class="hero-copy">
          <p class="eyebrow">Traffic Video Analytics</p>
          <h1>Turn roadside footage into billboard planning intelligence.</h1>
          <p class="hero-text">
            Upload traffic footage or connect a camera source, then monitor the analysis job, vehicle mix,
            traffic peaks, and recommendation output in one place.
          </p>
        </div>
        <div class="hero-stats">
          <div class="stat-card">
            <span class="stat-label">Analysis Source</span>
            <strong>{{ sourceType === "upload" ? "Uploaded Footage" : "Camera Stream" }}</strong>
          </div>
          <div class="stat-card">
            <span class="stat-label">Detected Vehicles</span>
            <strong>{{ totalVehicleCount }}</strong>
          </div>
          <div class="stat-card">
            <span class="stat-label">Peak Window</span>
            <strong>{{ peakSummary }}</strong>
          </div>
        </div>
      </section>

      <section class="workspace-grid">
        <div class="panel ingest-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Input</p>
              <h2>New Analysis</h2>
            </div>
            <span class="section-chip">{{ analysisButtonLabel }}</span>
          </div>

          <div class="form-grid">
            <label>
              Video Start Date
              <input v-model="startDate" type="date" />
            </label>

            <label>
              Start Time
              <input v-model="startTime" type="time" />
            </label>

            <label class="full-width">
              Analysis Name
              <input v-model.trim="outputFileName" type="text" placeholder="campaign_morning_peak" />
            </label>
          </div>

          <div class="source-selector">
            <label class="radio-tile" :class="{ 'radio-tile--active': sourceType === 'upload' }">
              <input v-model="sourceType" type="radio" value="upload" />
              <span>Upload Video</span>
            </label>
            <label class="radio-tile" :class="{ 'radio-tile--active': sourceType === 'camera_url' }">
              <input v-model="sourceType" type="radio" value="camera_url" />
              <span>Camera or IP URL</span>
            </label>
          </div>

          <label v-if="sourceType === 'upload'" class="file-drop">
            <input type="file" accept="video/*" @change="onFileChange" />
            <strong>{{ selectedVideoLabel }}</strong>
            <span>Select a video file to analyze traffic flow and vehicle mix.</span>
          </label>

          <label v-else class="full-width">
            Camera Stream Source
            <input
              v-model.trim="cameraUrl"
              type="text"
              placeholder="rtsp://..., direct http(s) stream, or webcam index like 0"
            />
          </label>
          <p v-if="sourceType === 'camera_url'" class="field-hint">
            Use a direct camera stream URL or device index. YouTube page URLs are not supported.
          </p>

          <label class="toggle-row">
            <input v-model="saveAnnotated" type="checkbox" />
            <span>Save annotated video output for review</span>
          </label>

          <div class="action-row">
            <button class="primary-btn" :disabled="!canAnalyze" @click="upload">
              {{ isUploading ? analysisButtonLabel : "Analyze Video" }}
            </button>
            <button v-if="isUploading" class="secondary-btn" @click="cancelAnalysis">Cancel</button>
          </div>
        </div>

        <div class="panel summary-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Overview</p>
              <h2>Campaign Snapshot</h2>
            </div>
          </div>

          <div v-if="resultEntries.length" class="metric-grid">
            <div v-for="([label, value], index) in topResultEntries" :key="`${label}-${index}`" class="metric-card">
              <span>{{ label }}</span>
              <strong>{{ value }}</strong>
            </div>
          </div>
          <div v-else class="empty-state">
            Run an analysis to populate vehicle mix, time-series traffic flow, and billboard recommendations.
          </div>

          <div class="summary-list">
            <div class="summary-item">
              <span>Analysis Name</span>
              <strong>{{ outputFileName || "Auto-generated on submit" }}</strong>
            </div>
            <div class="summary-item">
              <span>Start Context</span>
              <strong>{{ startContextSummary }}</strong>
            </div>
            <div class="summary-item">
              <span>Annotated Output</span>
              <strong>{{ saveAnnotated ? "Enabled" : "Disabled" }}</strong>
            </div>
          </div>
        </div>
      </section>

      <AnalysisStatus
        :busy="isUploading"
        :message="jobStatusMessage"
        :progress-percent="jobProgressPercent"
        :error="errorMsg"
      />

      <RecentJobsPanel
        :jobs="recentJobs"
        :total="jobsTotal"
        :limit="jobsLimit"
        :offset="jobsOffset"
        :is-loading="jobsLoading"
        :error="jobsError"
        :filters="jobFilters"
        :action-state="jobActionState"
        @refresh="refreshJobs"
        @apply-filters="applyJobFilters"
        @prev-page="goToPreviousJobsPage"
        @next-page="goToNextJobsPage"
        @retry-job="retryJob"
        @cancel-job="cancelRecentJob"
      />

      <HistoryPanel
        :visible="historyVisible"
        :entries="historyEntries"
        :is-loading="historyLoading"
        :error="historyError"
        :has-loaded="historyHasLoaded"
        :limit="historyLimit"
        :offset="historyOffset"
        :total="historyTotal"
        :filters="historyFilters"
        @toggle="toggleHistory"
        @refresh="refreshHistory"
        @apply-filters="applyHistoryFilters"
        @prev-page="goToPreviousHistoryPage"
        @next-page="goToNextHistoryPage"
      />

      <section v-if="resultEntries.length" class="results-grid">
        <div class="panel chart-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Results</p>
              <h2>Vehicle Class Distribution</h2>
            </div>
          </div>

          <table class="results-table">
            <thead>
              <tr>
                <th>Class</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="([label, value], index) in resultEntries" :key="`${label}-${index}`">
                <td>{{ label }}</td>
                <td>{{ value }}</td>
              </tr>
            </tbody>
          </table>

          <div class="results-cards">
            <article v-for="([label, value], index) in resultEntries" :key="`result-card-${label}-${index}`" class="result-card">
              <span>{{ label }}</span>
              <strong>{{ value }}</strong>
            </article>
          </div>

          <div class="chart-shell">
            <PieChart :counts="result" />
          </div>
        </div>

        <div v-if="timeSeries.length" class="panel chart-panel chart-panel--wide">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Flow</p>
              <h2>Traffic Flow Over Time</h2>
            </div>
          </div>

          <TimeSeriesChart :time-series="timeSeries" :main-class-list="mainClassList" />
        </div>

        <InsightPanel :recommendations="recommendations" :gpt-recommendations="gpt_recommendations" />

        <div v-if="annotatedUrl" class="panel media-panel">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Output</p>
              <h2>Annotated Video</h2>
            </div>
          </div>
          <video :key="annotatedUrl" width="100%" controls preload="metadata" class="result-video">
            <source :src="annotatedUrl" type="video/mp4" />
            Your browser does not support the video tag.
          </video>
          <p class="media-note">
            If playback does not start here, open the generated file directly:
            <a :href="annotatedUrl" target="_blank" rel="noopener">Open annotated video</a>
          </p>
        </div>
      </section>
    </main>
  </div>
</template>

<script>
import { defineAsyncComponent } from "vue";
import AnalysisStatus from "./components/AnalysisStatus.vue";
import HistoryPanel from "./components/HistoryPanel.vue";
import InsightPanel from "./components/InsightPanel.vue";
import NotificationStack from "./components/NotificationStack.vue";
import RecentJobsPanel from "./components/RecentJobsPanel.vue";

const ChartLoadingState = {
  template: `
    <div class="chart-loading-state">
      <div class="chart-loading-bar"></div>
      <p>Loading analytics visual...</p>
    </div>
  `,
};

const PieChart = defineAsyncComponent({
  loader: () => import("./components/PieChart.vue"),
  loadingComponent: ChartLoadingState,
  delay: 120,
});

const TimeSeriesChart = defineAsyncComponent({
  loader: () => import("./components/TimeSeriesChart.vue"),
  loadingComponent: ChartLoadingState,
  delay: 120,
});

export default {
  components: {
    PieChart,
    TimeSeriesChart,
    AnalysisStatus,
    HistoryPanel,
    InsightPanel,
    NotificationStack,
    RecentJobsPanel,
  },
  data() {
    return {
      startDate: "",
      startTime: "",
      sourceType: "upload",
      cameraUrl: "",
      video: null,
      uploadAbortController: null,
      pollTimer: null,
      activeJobId: null,
      jobStatus: null,
      jobProgressPercent: null,
      jobProgressMessage: null,
      result: null,
      peak: null,
      recommendations: [],
      timeSeries: [],
      isUploading: false,
      errorMsg: null,
      annotatedUrl: null,
      annotatedDownloadName: null,
      outputFileName: "",
      saveAnnotated: false,
      mainClassList: [
        "Commercial Vehicles",
        "High-End Vehicles",
        "Low-End Vehicles",
        "Mid-Range Vehicles",
        "Motorcycle",
        "Unclassified",
      ],
      historyEntries: [],
      historyVisible: false,
      historyLoading: false,
      historyError: null,
      historyLimit: 5,
      historyOffset: 0,
      historyTotal: 0,
      historyHasLoaded: false,
      historyRequestToken: 0,
      historyFilters: {
        analysisName: "",
        dateFrom: "",
        dateTo: "",
      },
      recentJobs: [],
      jobsLoading: false,
      jobsError: null,
      jobsLimit: 6,
      jobsOffset: 0,
      jobsTotal: 0,
      jobsRequestToken: 0,
      jobFilters: {
        status: "queued,running,canceling",
        sourceKind: "",
        analysisName: "",
      },
      jobActionState: {},
      gpt_recommendations: null,
      notifications: [],
      notificationCounter: 0,
    };
  },
  beforeUnmount() {
    this.stopPolling();
    if (this.uploadAbortController) {
      this.uploadAbortController.abort();
      this.uploadAbortController = null;
    }
  },
  mounted() {
    this.fetchRecentJobs();
  },
  computed: {
    analysisButtonLabel() {
      if (this.jobStatus === "submitting") return "Submitting";
      if (this.jobStatus === "queued") return "Queued";
      if (this.jobStatus === "running") return "Analyzing";
      if (this.jobStatus === "canceling") return "Canceling";
      return "Ready";
    },
    canAnalyze() {
      if (this.isUploading) {
        return false;
      }
      if (this.sourceType === "upload") {
        return !!this.video;
      }
      if (this.sourceType === "camera_url") {
        return !!this.cameraUrl.trim();
      }
      return false;
    },
    resultEntries() {
      return Object.entries(this.result || {});
    },
    topResultEntries() {
      return this.resultEntries.slice(0, 4);
    },
    totalVehicleCount() {
      return this.resultEntries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
    },
    peakSummary() {
      if (!this.peak) {
        return "Pending Analysis";
      }
      return `${this.peak.hour}:00 (${this.peak.count} vehicles)`;
    },
    startContextSummary() {
      if (!this.startDate && !this.startTime) {
        return "No start date or time provided";
      }
      return [this.startDate || "Date not set", this.startTime || "Time not set"].join(" at ");
    },
    selectedVideoLabel() {
      return this.video ? this.video.name : "Select a traffic video";
    },
    jobStatusMessage() {
      if (!this.isUploading || !this.jobStatus) return null;
      if (this.jobStatus === "submitting") return "Uploading footage and creating the analysis job.";
      if (this.jobStatus === "queued") {
        return this.jobProgressMessage || "The worker has queued your analysis and will start shortly.";
      }
      if (this.jobStatus === "running") {
        return this.jobProgressMessage || "The video is being analyzed. Longer footage can take a while.";
      }
      if (this.jobStatus === "canceling") {
        return this.jobProgressMessage || "Cancel requested. Waiting for the worker to stop.";
      }
      return null;
    },
  },
  methods: {
    pushNotification({ title, message, tone = "info", duration = 4000 }) {
      const id = this.notificationCounter + 1;
      this.notificationCounter = id;
      this.notifications = [...this.notifications, { id, title, message, tone }];

      if (duration > 0) {
        setTimeout(() => {
          this.dismissNotification(id);
        }, duration);
      }
    },
    dismissNotification(id) {
      this.notifications = this.notifications.filter((notification) => notification.id !== id);
    },
    setError(message, notificationTitle = "Request Failed") {
      this.errorMsg = message;
      this.pushNotification({
        title: notificationTitle,
        message,
        tone: "error",
        duration: 5500,
      });
    },
    normalizeError(error, fallbackMessage) {
      if (error?.name === "AbortError") {
        return "Analysis request canceled.";
      }
      if (error?.message) {
        return error.message;
      }
      return fallbackMessage;
    },
    validateCameraSource(value) {
      const trimmed = (value || "").trim();
      if (!trimmed) {
        return "Please enter a camera URL or device index.";
      }
      if (/^\d+$/.test(trimmed)) {
        return null;
      }

      let parsed;
      try {
        parsed = new URL(trimmed);
      } catch {
        return "Use a direct rtsp/http/https camera stream URL or a numeric device index.";
      }

      const protocol = parsed.protocol.replace(":", "").toLowerCase();
      if (!["rtsp", "rtsps", "http", "https"].includes(protocol)) {
        return "Use a direct rtsp/http/https camera stream URL or a numeric device index.";
      }

      const hostname = parsed.hostname.toLowerCase();
      const unsupportedHosts = new Set([
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
      ]);
      if (unsupportedHosts.has(hostname)) {
        return "YouTube page URLs are not supported. Use a direct camera stream URL instead.";
      }

      return null;
    },
    async parseJsonResponse(response) {
      const contentType = response.headers.get("content-type") || "";
      const isJson = contentType.includes("application/json");
      const payload = isJson ? await response.json() : { error: await response.text() };

      if (!response.ok) {
        const message = payload?.error || `Request failed (${response.status})`;
        const requestError = new Error(message);
        requestError.status = response.status;
        requestError.payload = payload;
        throw requestError;
      }

      return payload;
    },
    async getJson(url) {
      const response = await fetch(url);
      return this.parseJsonResponse(response);
    },
    async postForm(url, formData, signal) {
      const response = await fetch(url, {
        method: "POST",
        body: formData,
        signal,
      });
      return this.parseJsonResponse(response);
    },
    async postJson(url, body = null) {
      const headers = body ? { "Content-Type": "application/json" } : {};
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: body ? JSON.stringify(body) : null,
      });
      return this.parseJsonResponse(response);
    },
    setJobActionState(jobId, action = null) {
      this.jobActionState = {
        ...this.jobActionState,
        [jobId]: action,
      };
      if (!action) {
        delete this.jobActionState[jobId];
        this.jobActionState = { ...this.jobActionState };
      }
    },
    onFileChange(event) {
      this.video = event.target.files[0] || null;
      this.clearAnalysisState();
      this.errorMsg = null;
    },
    clearAnalysisState() {
      this.result = null;
      this.peak = null;
      this.recommendations = [];
      this.gpt_recommendations = null;
      this.timeSeries = [];
      this.annotatedUrl = null;
      this.annotatedDownloadName = null;
    },
    applyAnalysisResult(payload) {
      this.result = payload.counts || null;
      this.peak = payload.peak || null;
      this.recommendations = [].concat(payload.recommendations || []);
      this.gpt_recommendations = payload.gpt_recommendations || null;
      this.timeSeries = payload.time_series || [];
      this.annotatedDownloadName = payload.annotated_video || null;
      this.annotatedUrl = payload.annotated_video
        ? `/output/${encodeURIComponent(payload.annotated_video)}?v=${Date.now()}`
        : null;
      this.pushNotification({
        title: "Analysis Complete",
        message: "Vehicle counts, charts, and recommendations are ready to review.",
        tone: "success",
      });
      this.fetchRecentJobs({ preserveOffset: false });
      if (this.historyVisible) {
        this.fetchHistory({ resetOffset: true });
      }
    },
    stopPolling() {
      if (this.pollTimer) {
        clearTimeout(this.pollTimer);
        this.pollTimer = null;
      }
    },
    async pollJob(jobId) {
      try {
        const payload = await this.getJson(`/analysis-jobs/${jobId}`);
        this.jobStatus = payload.status;
        this.jobProgressPercent =
          typeof payload.progress_percent === "number" ? payload.progress_percent : null;
        this.jobProgressMessage = payload.progress_message || null;

        if (payload.status === "completed" && payload.result) {
          this.applyAnalysisResult(payload.result);
          this.isUploading = false;
          this.activeJobId = null;
          this.jobStatus = null;
          this.stopPolling();
          return;
        }

        if (payload.status === "failed") {
          this.setError(payload.error || "Analysis failed", "Analysis Failed");
          this.isUploading = false;
          this.activeJobId = null;
          this.jobProgressPercent = null;
          this.jobProgressMessage = null;
          this.jobStatus = null;
          this.stopPolling();
          this.fetchRecentJobs();
          return;
        }

        if (payload.status === "canceled") {
          this.errorMsg = "Analysis canceled.";
          this.pushNotification({
            title: "Analysis Canceled",
            message: "The worker has stopped this analysis job.",
            tone: "warning",
          });
          this.isUploading = false;
          this.activeJobId = null;
          this.jobProgressPercent = null;
          this.jobProgressMessage = null;
          this.jobStatus = null;
          this.stopPolling();
          this.fetchRecentJobs();
          return;
        }

        this.syncRecentJob(payload);
        this.pollTimer = setTimeout(() => this.pollJob(jobId), 1500);
      } catch (error) {
        this.setError(this.normalizeError(error, "Could not check analysis status"), "Status Check Failed");
        this.isUploading = false;
        this.activeJobId = null;
        this.jobProgressPercent = null;
        this.jobProgressMessage = null;
        this.jobStatus = null;
        this.stopPolling();
        this.fetchRecentJobs();
      }
    },
    syncRecentJob(jobPayload) {
      if (!jobPayload?.job_id || !this.recentJobs.length) {
        return;
      }
      const nextJobs = this.recentJobs.map((job) => (job.job_id === jobPayload.job_id ? { ...job, ...jobPayload } : job));
      this.recentJobs = nextJobs;
    },
    buildDefaultAnalysisName() {
      const now = new Date();
      const date = now.toISOString().slice(0, 10);
      const time = now.toTimeString().slice(0, 5).replace(":", "-");
      return `analysis_${date}_${time}`;
    },
    async upload() {
      this.stopPolling();
      if (this.uploadAbortController) {
        this.uploadAbortController.abort();
      }
      this.uploadAbortController = new AbortController();
      this.isUploading = true;
      this.jobStatus = "submitting";
      this.jobProgressPercent = null;
      this.jobProgressMessage = null;
      this.activeJobId = null;
      this.errorMsg = null;
      this.clearAnalysisState();

      const formData = new FormData();
      formData.append("start_date", this.startDate);
      formData.append("start_time", this.startTime);

      const analysisName = this.outputFileName || this.buildDefaultAnalysisName();
      this.outputFileName = analysisName;
      formData.append("analysis_name", analysisName);
      formData.append("save_annotated", this.saveAnnotated ? "true" : "false");

      if (this.sourceType === "upload") {
        if (!this.video) {
          this.isUploading = false;
          this.setError("Please choose a video file to analyze.", "Missing Video");
          return;
        }
        formData.append("video", this.video);
      } else if (this.sourceType === "camera_url") {
        const cameraSourceError = this.validateCameraSource(this.cameraUrl);
        if (cameraSourceError) {
          this.isUploading = false;
          this.setError(cameraSourceError, "Invalid Camera Source");
          return;
        }
        formData.append("camera_url", this.cameraUrl);
      }

      try {
        const payload = await this.postForm("/analysis-jobs", formData, this.uploadAbortController.signal);
        this.activeJobId = payload.job_id;
        this.jobStatus = payload.status;
        this.jobProgressPercent =
          typeof payload.progress_percent === "number" ? payload.progress_percent : null;
        this.jobProgressMessage = payload.progress_message || null;

        if (payload.result) {
          this.applyAnalysisResult(payload.result);
          this.isUploading = false;
          this.activeJobId = null;
          this.jobStatus = null;
        } else if (payload.job_id) {
          this.pushNotification({
            title: "Job Submitted",
            message: "Your analysis job is queued and will update automatically.",
            tone: "info",
          });
          this.fetchRecentJobs({ preserveOffset: false });
          this.pollJob(payload.job_id);
        }
      } catch (error) {
        this.setError(this.normalizeError(error, "Upload failed"), "Upload Failed");
        this.jobStatus = null;
        this.activeJobId = null;
        this.jobProgressPercent = null;
        this.jobProgressMessage = null;
        this.stopPolling();
        this.isUploading = false;
      } finally {
        this.uploadAbortController = null;
      }
    },
    buildJobsQuery() {
      const params = new URLSearchParams({
        limit: String(this.jobsLimit),
        offset: String(this.jobsOffset),
      });

      if (this.jobFilters.status) {
        params.set("status", this.jobFilters.status);
      }
      if (this.jobFilters.sourceKind) {
        params.set("source_kind", this.jobFilters.sourceKind);
      }
      if (this.jobFilters.analysisName) {
        params.set("analysis_name", this.jobFilters.analysisName);
      }

      return params.toString();
    },
    async fetchRecentJobs({ preserveOffset = true } = {}) {
      if (!preserveOffset) {
        this.jobsOffset = 0;
      }

      this.jobsLoading = true;
      this.jobsError = null;
      const requestToken = this.jobsRequestToken + 1;
      this.jobsRequestToken = requestToken;

      try {
        const payload = await this.getJson(`/analysis-jobs?${this.buildJobsQuery()}`);
        if (this.jobsRequestToken !== requestToken) {
          return;
        }

        this.recentJobs = payload.jobs || [];
        this.jobsTotal = typeof payload.total === "number" ? payload.total : 0;
        this.jobsOffset = typeof payload.offset === "number" ? payload.offset : this.jobsOffset;
        this.jobsLimit = typeof payload.limit === "number" ? payload.limit : this.jobsLimit;
      } catch (error) {
        if (this.jobsRequestToken !== requestToken) {
          return;
        }
        this.jobsError = this.normalizeError(error, "Could not load recent jobs");
        this.pushNotification({
          title: "Jobs Unavailable",
          message: this.jobsError,
          tone: "error",
          duration: 5500,
        });
      } finally {
        if (this.jobsRequestToken === requestToken) {
          this.jobsLoading = false;
        }
      }
    },
    async refreshJobs() {
      await this.fetchRecentJobs();
      if (!this.jobsError) {
        this.pushNotification({
          title: "Jobs Refreshed",
          message: "Recent analysis jobs were reloaded from the backend queue.",
          tone: "info",
        });
      }
    },
    async applyJobFilters(filters) {
      this.jobFilters = {
        status: filters.status || "",
        sourceKind: filters.sourceKind || "",
        analysisName: filters.analysisName || "",
      };
      await this.fetchRecentJobs({ preserveOffset: false });
      if (!this.jobsError) {
        this.pushNotification({
          title: "Job Filters Applied",
          message: "Recent jobs now reflect the selected queue filters.",
          tone: "success",
        });
      }
    },
    async goToPreviousJobsPage() {
      if (this.jobsOffset === 0) {
        return;
      }
      this.jobsOffset = Math.max(0, this.jobsOffset - this.jobsLimit);
      await this.fetchRecentJobs();
    },
    async goToNextJobsPage() {
      if (this.jobsOffset + this.jobsLimit >= this.jobsTotal) {
        return;
      }
      this.jobsOffset += this.jobsLimit;
      await this.fetchRecentJobs();
    },
    buildHistoryQuery() {
      const params = new URLSearchParams({
        limit: String(this.historyLimit),
        offset: String(this.historyOffset),
      });

      if (this.historyFilters.analysisName) {
        params.set("analysis_name", this.historyFilters.analysisName);
      }
      if (this.historyFilters.dateFrom) {
        params.set("date_from", this.historyFilters.dateFrom);
      }
      if (this.historyFilters.dateTo) {
        params.set("date_to", this.historyFilters.dateTo);
      }

      return params.toString();
    },
    normalizeHistoryPayload(payload) {
      if (Array.isArray(payload)) {
        return {
          records: payload,
          total: payload.length,
          limit: payload.length || this.historyLimit,
          offset: 0,
        };
      }

      return {
        records: payload.records || [],
        total: typeof payload.total === "number" ? payload.total : payload.count || 0,
        limit: typeof payload.limit === "number" ? payload.limit : this.historyLimit,
        offset: typeof payload.offset === "number" ? payload.offset : this.historyOffset,
      };
    },
    async fetchHistory({ resetOffset = false } = {}) {
      if (resetOffset) {
        this.historyOffset = 0;
      }

      this.historyLoading = true;
      this.historyError = null;
      const requestToken = this.historyRequestToken + 1;
      this.historyRequestToken = requestToken;

      try {
        const payload = await this.getJson(`/history?${this.buildHistoryQuery()}`);
        if (this.historyRequestToken !== requestToken) {
          return;
        }

        const normalized = this.normalizeHistoryPayload(payload);
        this.historyEntries = normalized.records;
        this.historyTotal = normalized.total;
        this.historyLimit = normalized.limit || this.historyLimit;
        this.historyOffset = normalized.offset;
        this.historyHasLoaded = true;
      } catch (error) {
        if (this.historyRequestToken !== requestToken) {
          return;
        }
        this.historyError = this.normalizeError(error, "Could not load analysis history");
        this.pushNotification({
          title: "History Unavailable",
          message: this.historyError,
          tone: "error",
          duration: 5500,
        });
      } finally {
        if (this.historyRequestToken === requestToken) {
          this.historyLoading = false;
        }
      }
    },
    async toggleHistory() {
      this.historyVisible = !this.historyVisible;
      if (this.historyVisible && !this.historyHasLoaded) {
        await this.fetchHistory({ resetOffset: true });
      }
    },
    async refreshHistory() {
      await this.fetchHistory();
      if (!this.historyError) {
        this.pushNotification({
          title: "History Refreshed",
          message: "Recent analysis records were reloaded from the backend.",
          tone: "info",
        });
      }
    },
    async applyHistoryFilters(filters) {
      this.historyFilters = {
        analysisName: filters.analysisName || "",
        dateFrom: filters.dateFrom || "",
        dateTo: filters.dateTo || "",
      };
      await this.fetchHistory({ resetOffset: true });
      if (!this.historyError) {
        this.pushNotification({
          title: "Filters Applied",
          message: "History results now reflect the selected date and name filters.",
          tone: "success",
        });
      }
    },
    async goToPreviousHistoryPage() {
      if (this.historyOffset === 0) {
        return;
      }
      this.historyOffset = Math.max(0, this.historyOffset - this.historyLimit);
      await this.fetchHistory();
    },
    async goToNextHistoryPage() {
      if (this.historyOffset + this.historyLimit >= this.historyTotal) {
        return;
      }
      this.historyOffset += this.historyLimit;
      await this.fetchHistory();
    },
    async retryJob(jobId) {
      this.setJobActionState(jobId, "retrying");
      try {
        const payload = await this.postJson(`/analysis-jobs/${jobId}/retry`);
        this.syncRecentJob(payload);
        await this.fetchRecentJobs();
        this.pushNotification({
          title: "Job Retried",
          message: "The analysis job was re-queued for another run.",
          tone: "success",
        });
      } catch (error) {
        this.setError(this.normalizeError(error, "Could not retry job"), "Retry Failed");
      } finally {
        this.setJobActionState(jobId, null);
      }
    },
    async cancelRecentJob(jobId) {
      this.setJobActionState(jobId, "canceling");
      try {
        const payload = await this.postJson(`/analysis-jobs/${jobId}/cancel`);
        this.syncRecentJob(payload);
        await this.fetchRecentJobs();
        this.pushNotification({
          title: "Job Cancel Requested",
          message: "The selected analysis job has received a cancel request.",
          tone: "warning",
        });

        if (this.activeJobId === jobId) {
          this.jobStatus = payload.status;
          this.jobProgressPercent =
            typeof payload.progress_percent === "number" ? payload.progress_percent : null;
          this.jobProgressMessage = payload.progress_message || null;
          if (payload.status === "canceled") {
            this.errorMsg = "Analysis canceled.";
            this.activeJobId = null;
            this.jobStatus = null;
            this.jobProgressPercent = null;
            this.jobProgressMessage = null;
            this.isUploading = false;
          }
        }
      } catch (error) {
        this.setError(this.normalizeError(error, "Could not cancel job"), "Cancel Failed");
      } finally {
        this.setJobActionState(jobId, null);
      }
    },
    async cancelAnalysis() {
      this.stopPolling();
      if (this.uploadAbortController) {
        this.uploadAbortController.abort();
        this.uploadAbortController = null;
      }

      if (this.activeJobId) {
        try {
          const payload = await this.postJson(`/analysis-jobs/${this.activeJobId}/cancel`);
          this.jobStatus = payload.status;
          this.jobProgressPercent =
            typeof payload.progress_percent === "number" ? payload.progress_percent : null;
          this.jobProgressMessage = payload.progress_message || null;

          if (payload.status === "canceled") {
            this.errorMsg = "Analysis canceled.";
            this.pushNotification({
              title: "Analysis Canceled",
              message: "The job was canceled before completion.",
              tone: "warning",
            });
            this.activeJobId = null;
            this.jobStatus = null;
            this.jobProgressPercent = null;
            this.jobProgressMessage = null;
            this.isUploading = false;
          } else {
            this.fetchRecentJobs();
            this.pollJob(this.activeJobId);
          }
          this.fetchRecentJobs();
          return;
        } catch (error) {
          this.setError(this.normalizeError(error, "Could not cancel analysis"), "Cancel Failed");
        }
      } else {
        this.errorMsg = "Analysis request canceled.";
        this.pushNotification({
          title: "Request Canceled",
          message: "The upload request was stopped before a job finished submitting.",
          tone: "warning",
        });
      }

      this.jobStatus = null;
      this.activeJobId = null;
      this.jobProgressPercent = null;
      this.jobProgressMessage = null;
      this.isUploading = false;
    },
  },
};
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap");

:root {
  color-scheme: light;
}

.app-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.18), transparent 28%),
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.18), transparent 26%),
    linear-gradient(180deg, #f8fbff 0%, #eef4f7 100%);
  padding: 2rem 1rem 3rem;
  font-family: "Manrope", sans-serif;
  color: #0f172a;
}

.app-frame {
  width: min(1180px, 100%);
  margin: 0 auto;
  display: grid;
  gap: 1.5rem;
}

.hero-panel,
.panel {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 1.5rem;
  box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
}

.hero-panel {
  padding: 1.75rem;
  display: grid;
  gap: 1.5rem;
}

.hero-copy h1,
.section-heading h2 {
  margin: 0;
}

.hero-copy h1 {
  font-size: clamp(2rem, 3.6vw, 3.25rem);
  line-height: 1.05;
  max-width: 12ch;
}

.hero-text {
  margin: 0.9rem 0 0;
  max-width: 48rem;
  color: #475569;
  line-height: 1.65;
}

.eyebrow {
  margin: 0 0 0.45rem;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0ea5e9;
}

.hero-stats,
.metric-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}

.stat-card,
.metric-card {
  border-radius: 1.1rem;
  padding: 1rem 1.1rem;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(241, 245, 249, 0.92));
  border: 1px solid rgba(226, 232, 240, 0.95);
}

.stat-label,
.metric-card span,
.summary-item span {
  display: block;
  color: #64748b;
  font-size: 0.9rem;
  margin-bottom: 0.35rem;
}

.stat-card strong,
.metric-card strong,
.summary-item strong {
  font-size: 1.05rem;
}

.workspace-grid,
.results-grid {
  display: grid;
  gap: 1.5rem;
}

.workspace-grid {
  grid-template-columns: minmax(0, 1.35fr) minmax(300px, 0.95fr);
}

.results-grid {
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
}

.form-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.full-width {
  grid-column: 1 / -1;
}

label {
  display: grid;
  gap: 0.45rem;
  font-weight: 600;
  color: #334155;
}

input[type="date"],
input[type="time"],
input[type="text"] {
  min-height: 2.8rem;
  padding: 0.75rem 0.95rem;
  border-radius: 0.95rem;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: #f8fafc;
  color: #0f172a;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

input[type="date"]:focus,
input[type="time"]:focus,
input[type="text"]:focus {
  outline: none;
  border-color: rgba(14, 165, 233, 0.7);
  box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.12);
}

.source-selector {
  display: grid;
  gap: 0.9rem;
  margin: 1.15rem 0;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.radio-tile {
  position: relative;
  border-radius: 1rem;
  border: 1px solid rgba(148, 163, 184, 0.35);
  padding: 1rem 1.1rem;
  background: #f8fafc;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.radio-tile input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.radio-tile span {
  font-weight: 700;
  color: #0f172a;
}

.radio-tile--active {
  background: rgba(14, 165, 233, 0.08);
  border-color: rgba(14, 165, 233, 0.55);
  transform: translateY(-1px);
}

.file-drop {
  margin: 0;
  min-height: 8.5rem;
  border-radius: 1.2rem;
  border: 1.5px dashed rgba(14, 165, 233, 0.45);
  background: linear-gradient(180deg, rgba(240, 249, 255, 0.9), rgba(248, 250, 252, 0.95));
  align-items: center;
  justify-items: center;
  text-align: center;
  padding: 1.35rem;
  cursor: pointer;
}

.file-drop input[type="file"] {
  display: none;
}

.file-drop strong {
  font-size: 1.05rem;
}

.file-drop span {
  color: #64748b;
  font-weight: 500;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
}

.field-hint {
  margin: -0.35rem 0 0;
  color: #64748b;
  font-size: 0.92rem;
  line-height: 1.5;
}

.toggle-row input {
  width: 1rem;
  height: 1rem;
}

.action-row {
  display: flex;
  gap: 0.85rem;
  flex-wrap: wrap;
  margin-top: 1.4rem;
}

.primary-btn,
.secondary-btn {
  min-height: 2.8rem;
  border-radius: 999px;
  padding: 0.78rem 1.25rem;
  border: none;
  cursor: pointer;
  font-weight: 800;
  transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
}

.primary-btn {
  background: linear-gradient(90deg, #0ea5e9 0%, #0284c7 100%);
  color: white;
  box-shadow: 0 14px 24px rgba(14, 165, 233, 0.24);
}

.secondary-btn {
  background: rgba(239, 68, 68, 0.12);
  color: #991b1b;
}

.primary-btn:hover,
.secondary-btn:hover {
  transform: translateY(-1px);
}

.primary-btn:disabled,
.secondary-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  transform: none;
}

.empty-state {
  border-radius: 1rem;
  padding: 1.2rem;
  background: #f8fafc;
  color: #475569;
  line-height: 1.6;
}

.summary-list {
  margin-top: 1.25rem;
  display: grid;
  gap: 0.9rem;
}

.summary-item {
  border-radius: 1rem;
  padding: 0.95rem 1rem;
  background: rgba(248, 250, 252, 0.88);
  border: 1px solid rgba(226, 232, 240, 0.95);
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1.25rem;
}

.results-cards {
  display: none;
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

.result-card {
  border-radius: 1rem;
  padding: 0.9rem 1rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  background: rgba(248, 250, 252, 0.92);
}

.result-card span {
  display: block;
  color: #64748b;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}

.result-card strong {
  color: #0f172a;
  font-size: 1.05rem;
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

.chart-panel--wide {
  grid-column: 1 / -1;
}

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

.media-note a {
  color: #0284c7;
  font-weight: 700;
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
  .workspace-grid,
  .results-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .app-shell {
    padding: 1rem 0.75rem 2rem;
  }

  .hero-panel,
  .panel {
    padding: 1.15rem;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .section-heading {
    flex-direction: column;
  }

  .hero-copy h1 {
    max-width: none;
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
