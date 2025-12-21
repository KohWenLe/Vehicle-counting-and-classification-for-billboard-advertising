# Vehicle Video Analyzer — FYP Submission Instructions

This tool analyzes traffic video or camera streams for billboard advertisers, providing vehicle counts, class breakdown, and actionable ad recommendations (using GPT or local logic). Analysis records are stored in a table for review.

---

## 1. Project Directories
Open command prompt and go to the project root (Traffic Video Analyzer)
```
cd <path/to/Traffic Video Analyzer>
```

## 2. Backend Setup

1. (Recommended/optional) Create a virtual environment:
   ```
   python -m venv venv
   # Activate (Windows): venv\Scripts\activate
   # Activate (Linux/Mac): source venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up environment variable for OpenAI (if using GPT):
   - add your OpenAI API key into .env file.
   - If not available, leave blank (local analysis will be used).

---

## 3. Frontend Setup

1. In the vehicle-webapp folder:
   ```
   cd vehicle-webapp
   npm install
   ```
2. Run the frontend:
   ```
   npm run serve
   ```
   - Opens at [http://localhost:8080](http://localhost:8080) by default.

---

## 4. Run the Backend

Open another command prompt, go to the Traffic Video Analyzer directory again, enter:

```
python app.py
```

- Backend API at [http://localhost:5000](http://localhost:5000)

---

## 5. Usage Steps

1. Open [http://localhost:8080](http://localhost:8080) in your browser.
2. Upload a video or enter a camera/IP stream URL.
3. (Optional) Enter video start date/time and analysis record name.
4. Click "Analyze Video" and wait for results.
5. View: vehicle counts, charts, annotated video, insights & recommendations, and analysis history.

---

## 6. Resetting the Database

To clear all previous analysis records:

- Stop the backend (Ctrl+C in terminal)
- Delete `analysis_history.db` (and any related journal/WAL files)
- Restart the backend (`python app.py`).

---

## 7. Important Notes

- Model files **must** be present or video analysis will fail.
- OpenAI GPT is optional; local recommendations are always available.
- All required dependencies are listed in requirements.txt and package.json.

---

## 8. Contact

For any issues or if model files are missing, contact the project author. 
email : jameskoh0513@gmail.com

---

**Thank you for reviewing this Final Year Project!**

