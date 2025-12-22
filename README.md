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

### System Flowchart and Video Processing Pipeline

<img width="490" height="265" alt="System Flowchart" src="https://github.com/user-attachments/assets/7043a86c-9358-42b6-a84d-717f44e13c76" />

---

## System showcase (UI)

- Counting and Classification Process

<img width="1440" height="1069" alt="vehicle tracking" src="https://github.com/user-attachments/assets/12e705be-9ac4-41df-91a2-2e3f78e006f6" />


- Video Upload

<img width="418" height="217" alt="video-upload-feature" src="https://github.com/user-attachments/assets/856b8134-25ea-4006-91eb-6f0fd07a5a48" />


- Analysis Generated

<img width="1131" height="1131" alt="pie-chart" src="https://github.com/user-attachments/assets/fd47505a-00ed-498a-aa95-38fb99f5e98f" />
<img width="1131" height="565" alt="time-series-chart" src="https://github.com/user-attachments/assets/c7a0e6e2-cca7-4abd-8858-1052d809b191" />
<img width="1087" height="137" alt="recommendations generated" src="https://github.com/user-attachments/assets/3778f02a-79ba-4986-871a-d5d771f35949" />

---

## ⚙️ Prerequisites

* Python **3.8+**
* Node.js **16+**
* npm

---

## To start off 
Open command prompt and go to the project root (Traffic Video Analyzer)
```
cd <path/to/Traffic Video Analyzer>
```

(Recommended/optional) Create a virtual environment:
```
python -m venv venv
# Activate (Windows): venv\Scripts\activate
# Activate (Linux/Mac): source venv/bin/activate
```

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

Open another command prompt, go to the Traffic Video Analyzer directory again, enter:
```bash
cd vehicle-webapp
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

---

## Research & Model Development Notebooks

The project root includes a folder that contains several Jupyter Notebook (`.ipynb`) files used **during the research and model development phase** of this project. These notebooks are **not required to run the final system**, but are included for academic transparency and evaluation.

### Included Notebooks

- **scrapeImages.ipynb**  
  Used to collect and preprocess vehicle images from online sources for dataset creation.

- **YOLO classification and crop.ipynb**  
  Used to experiment with YOLO-based vehicle detection and cropping detected vehicles for downstream classification.

- **MobileNetV3 training original.ipynb**  
  Used to train the MobileNetV3 model for vehicle class classification (High-End, Mid-Range, Low-End, Commercial, Motorcycle).

- **Vehicle counting and classification.ipynb**  
  Early prototype notebook for testing vehicle counting, tracking logic, and class aggregation before integrating into the production pipeline.

### Important Notes

- These notebooks were used **offline** during experimentation and model training.
- They are **not executed by the Flask application**.
- Running the system **does NOT require Jupyter Notebook**.

They are provided for:
- Academic review
- Reproducibility of model training
- Demonstration of research methodology

---

## 📬 Contact
For questions, missing assets, or clarification, please contact the project author.
jameskoh0513@gmail.com

---
