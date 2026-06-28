# Traffic Video Analyzer Frontend

This is the Vue frontend for Traffic Video Analyzer. It submits analysis jobs, polls backend job status, displays recent jobs and history, opens job details, and shows the final vehicle analytics dashboard.

The frontend expects the Flask API to run on:

```text
http://localhost:5000
```

During development, `vue.config.js` proxies backend routes from the Vue dev server.

---

## Setup

From this folder:

```powershell
npm install
```

---

## Development Server

```powershell
npm run serve
```

Default URL:

```text
http://localhost:8080
```

If backend routes return `404` from port `8080`, restart the Vue dev server so it reloads `vue.config.js`.

---

## Required Backend Processes

Run these from the project root in separate terminals:

```powershell
python app.py
python worker.py
```

Without the worker, submitted jobs will stay queued.

---

## Proxied Backend Routes

The dev server proxies:

- `/analysis-jobs`
- `/analyze`
- `/output`
- `/history`
- `/health`
- `/metrics`
- `/diagnostics`
- `/test_gpt_analysis`

---

## Commands

Lint:

```powershell
npm.cmd run lint
```

Production build:

```powershell
npm.cmd run build
```

The production build may warn that the vendor bundle exceeds Vue CLI's default asset-size recommendation. That is expected with the current Vue and Chart.js dependencies.
