# pip install flask
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS 
import os
import uuid
import traceback
import datetime
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///analysis_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class AnalysisResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=True)  
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    counts = db.Column(db.Text)  # Store as JSON string
    peak_hour = db.Column(db.Integer)
    peak_count = db.Column(db.Integer)
    recommendations = db.Column(db.Text)  # Store as JSON string
    analysis_name = db.Column(db.String(256))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat(),
            'counts': json.loads(self.counts),
            'peak_hour': self.peak_hour,
            'peak_count': self.peak_count,
            'recommendations': json.loads(self.recommendations),
            'analysis_name': self.analysis_name,
        }
    
with app.app_context():
    db.create_all()


UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

from pipeline import process_video  # import process_video function
from analysis import analyze_results # import analyze_results function

@app.route('/analyze', methods=['POST'])
def analyze():
    temp_path = None
    video_path = None
    result = None
    analysis = None
    gpt_recommendations = None
    try:
        # 1. Handle video upload or camera URL/index
        if 'video' in request.files:
            file = request.files['video']
            if file.filename == '':
                return jsonify({'error': 'Empty filename'}), 400
            temp_name = f"{uuid.uuid4().hex}_{file.filename}"
            temp_path = os.path.join(UPLOAD_FOLDER, temp_name)
            file.save(temp_path)
            video_path = temp_path
            
        elif 'camera_url' in request.form:
            video_path = request.form.get('camera_url')
            if not video_path:
                return jsonify({'error': 'No camera URL provided'}), 400
            # Allow numeric "0" as string for webcam index
            if video_path.isdigit():
                video_path = int(video_path)
        else:
            return jsonify({'error': 'No video file or camera URL provided'}), 400    

        # 2. Parse start_date/start_time
        start_date = request.form.get('start_date')
        start_time = request.form.get('start_time')
        if start_date and start_time: # # Combine and parse to datetime
            start_dt = datetime.datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M") # 'YYYY-MM-DD', 'HH:MM'
        else:
            start_dt = datetime.datetime.now() # Use current time as fallback

        save_annotated = request.form.get('save_annotated', None)
        # 3. Run pipeline on video_path (can be file path, URL, or int index)
        result = process_video(video_path, start_dt=start_dt, save_annotated=save_annotated) # result contains: counts, time_series
        
        # 4. Try GPT analysis first
        try:
            gpt_recommendations = analyze_with_gpt(result['counts'], result['time_series'])
        except Exception as gpt_error:
            print(f"GPT API error: {gpt_error}")
            gpt_recommendations = None  # Explicit for clarity

        # 5. If GPT not available, use local analysis.py
        if not gpt_recommendations:
            analysis = analyze_results(result['time_series'], result['counts'])

    except Exception as e:
        print("=== ERROR CAUGHT IN FLASK /analyze ===")
        traceback.print_exc()  # This prints the full traceback to your Flask terminal
        return jsonify({'error': str(e)}), 500
    finally:
        # Only delete temp file if we saved one
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    # 6. save as record in db
    record = AnalysisResult(
        user_id=None,
        counts=json.dumps(result["counts"]),
        peak_hour=analysis["peak"]["hour"] if analysis else None,
        peak_count=analysis["peak"]["count"] if analysis else None,
        recommendations=json.dumps(
            analysis["recommendations"] if analysis else [gpt_recommendations]
        ),
        analysis_name=save_annotated
    )
    db.session.add(record)
    db.session.commit()
    # 7. Return results as JSON
    response = {
        "counts": result["counts"],
        "time_series": result["time_series"],
    }
    if gpt_recommendations:
        response["gpt_recommendations"] = gpt_recommendations
    if analysis:
        response["peak"] = analysis["peak"]
        response["recommendations"] = analysis["recommendations"]
    return jsonify(response)

@app.route('/output/<filename>')
def output_file(filename):
    return send_from_directory('output', filename)

@app.route('/test_analysis', methods=['POST'])
def test_analysis():
    # Get sample data from request body (as JSON)
    data = request.get_json()
    # Example expected keys: 'counts', 'time_series'
    counts = data.get('counts', {})
    time_series = data.get('time_series', [])
    # Call your analysis function 
    from analysis import analyze_results
    analysis = analyze_results(time_series, counts)
    return jsonify(analysis)

@app.route('/history', methods=['GET'])
def get_history():
    results = AnalysisResult.query.order_by(AnalysisResult.timestamp.desc()).limit(50).all()
    return jsonify([r.to_dict() for r in results])

def analyze_with_gpt(counts, time_series):
    import openai
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "sk-sample")
    client = openai.OpenAI(api_key=api_key)

    prompt = (
        "You are a billboard advertising strategist. "
        "Given this vehicle traffic data, note that all counts and time series are CUMULATIVE totals up to each timestamp, not interval-based flows. "
        f"Total counts per class: {counts}. "
        f"Hourly time series (only show if relevant): {time_series[:3]} ...\n"
        "Instructions:\n"
        "- Briefly identify the peak hour and dominant class, in one sentence each.\n"
        "- List exactly 5 targeted advertisement recommendations (product/service categories) for the most common audience, based on vehicle classes detected.\n"
        "- After the ad recommendations, add a short, practical elaboration (~2-3 sentences) explaining why these ad types are optimal for this audience and timing.\n"
        "- Do NOT repeat the raw counts or detailed data in your answer.\n"
        "- Format as short bullet points and clear paragraphs.\n"
        "- Total answer MUST NOT exceed 200 words.\n"
        "Example output:\n"
        "• Peak hour: 11:00 AM is the busiest time, ideal for ad exposure.\n"
        "• Dominant class: Mid-Range Vehicles dominate, suggesting a mainstream consumer base.\n"
        "• Recommended ads:\n"
        "   1. Family cars or home electronics\n"
        "   2. Insurance or financial services\n"
        "   3. Food delivery platforms\n"
        "   4. Travel and tourism\n"
        "   5. Health and wellness\n"
        "These recommendations match the preferences and lifestyles of the primary commuters detected. Advertising during the peak hour maximizes exposure to this audience, increasing potential engagement and return on investment."
    )
    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14",
        messages=[
            {"role": "system", "content": "You are a concise and expert billboard ad advisor."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        temperature=0.5
    )
    return response.choices[0].message.content

@app.route('/test_gpt_analysis', methods=['GET'])
def test_gpt_analysis():
    # Sample/mock data 
    counts = {
        "Commercial Vehicles": 12,
        "High-End Vehicles": 18,
        "Low-End Vehicles": 5,
        "Mid-Range Vehicles": 15,
        "Motorcycle": 3,
        "Unclassified": 20
    }
    time_series = [
        {"timestamp": "2024-07-07 09:00:00", "Commercial Vehicles": 3, "High-End Vehicles": 4, "Low-End Vehicles": 0, "Mid-Range Vehicles": 4, "Motorcycle": 1, "Unclassified": 0},
        {"timestamp": "2024-07-07 10:00:00", "Commercial Vehicles": 4, "High-End Vehicles": 6, "Low-End Vehicles": 2, "Mid-Range Vehicles": 5, "Motorcycle": 1, "Unclassified": 10},
        {"timestamp": "2024-07-07 11:00:00", "Commercial Vehicles": 5, "High-End Vehicles": 8, "Low-End Vehicles": 3, "Mid-Range Vehicles": 6, "Motorcycle": 1, "Unclassified": 20}
    ]
    gpt_recommendations = analyze_with_gpt(counts, time_series)
    return jsonify({"gpt_recommendations": gpt_recommendations})


if __name__ == '__main__':
    app.run(debug=False, threaded=True)
