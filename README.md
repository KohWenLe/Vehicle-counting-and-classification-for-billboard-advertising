# 🚗 Vehicle Video Analyzer for Billboard Advertising

A real-time vehicle detection, tracking, and classification system designed to support **data-driven billboard advertising decisions**.
The system analyzes traffic videos or live camera streams, extracts vehicle insights, and generates **actionable advertising recommendations** using either **GPT (LLM-based analysis)** or a **local rule-based analysis fallback**.

---

## 📌 Project Overview

Outdoor advertisers rely on accurate traffic data to optimize ad placement and timing.
This project provides:

* Vehicle counting by class
* Time-series traffic analysis
* Peak-hour detection
* Advertising insights and recommendations
* Optional GPT-powered analysis
* Historical analysis record storage

---

## 🧠 Key Features

* **Vehicle Detection & Tracking**

  * YOLO for detection
  * DeepSORT for multi-object tracking

* **Vehicle Classification**

  * Custom MobileNetV3 classifier
  * Classes:

    * High-End Vehicles
    * Mid-Range Vehicles
    * Low-End Vehicles
    * Commercial Vehicles
    * Motorcycles
    * Unclassified

* **Traffic Analytics**

  * Cumulative counts
  * Hourly traffic flow estimation
  * Peak-hour detection

* **Advertising Insights**

  * GPT-based analysis (if API key available)
  * Automatic fallback to local analysis logic
  * Structured, readable recommendations

* **Web Interface**

  * Upload video or use camera/IP stream
  * Interactive charts (Pie + Time-Series)
  * Annotated video output
  * Paginated analysis history

---

## 🏗️ System Architecture

```
Frontend (Vue.js)
    ↓
Backend (Flask API)
    ↓
Video Pipeline (YOLO + DeepSORT + MobileNetV3)
    ↓
Analytics Engine (Local or GPT-based)
    ↓
SQLite Database (Analysis History)
```

---

## 📂 Project Structure

```
project-root/
├── app.py                     # Flask backend
├── pipeline.py                # Video processing pipeline
├── analysis.py                # Local analysis logic
├── requirements.txt
├── .env.sample               # Environment variable template
├── yolo11n.pt                 # YOLO model (not included)
├── mobilenetv3_original.keras # Classifier model (not included)
├── analysis_history.db        # Auto-generated database
├── frontend/
│   ├── App.vue
│   ├── main.js
│   └── ...
```

---

## ⚙️ Prerequisites

* Python **3.8+**
* Node.js **16+**
* npm

---

## 🔧 Backend Setup (Flask)

### 1️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 2️⃣ (Optional) GPT Configuration

Create a `.env` file:

```env
OPENAI_API_KEY=your_api_key_here
```

> If the key is missing, the system automatically uses local analysis.

### 3️⃣ Run Backend

```bash
python app.py
```

Backend runs at:

```
http://localhost:5000
```

---

## 🎨 Frontend Setup (Vue.js)

```bash
cd frontend
npm install
npm run serve
```

Frontend runs at:

```
http://localhost:8080
```

---

## ▶️ How to Use

1. Open `http://localhost:8080`
2. Choose:

   * Upload a video **OR**
   * Enter a camera/IP stream URL
3. (Optional) Set start date/time and analysis name
4. Click **Analyze Video**
5. View:

   * Vehicle counts
   * Distribution charts
   * Time-series traffic flow
   * Peak hour
   * Insights & recommendations
6. Browse past analyses in **Analysis History**

---

## 📊 Insights & Recommendations Logic

### Priority Order:

1. **GPT Analysis (LLM)**
2. **Local Analysis Fallback**

### Local Analysis Includes:

* Dominant vehicle class
* Rare class detection
* Data quality warnings
* Peak-hour advertising suggestions

---

## 🗄️ Resetting the Database

To clear analysis history:

```bash
# Stop backend
Ctrl + C

# Delete database file
rm analysis_history.db

# Restart backend
python app.py
```

---

## 🎓 Academic Context

* **Domain:** Computer Vision, AI, Data Analytics
* **Application:** Traffic Analysis for Billboard Advertising 
* **Tech Stack:**
  Python · Flask · Vue.js · YOLO · DeepSORT · TensorFlow · GPT

---

## 📬 Contact

For questions, missing assets, or clarification, please contact the project author.
jameskoh0513@gmail.com
---
