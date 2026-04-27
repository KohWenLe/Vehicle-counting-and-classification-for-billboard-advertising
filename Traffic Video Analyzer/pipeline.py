import cv2
import numpy as np
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v3 import preprocess_input as keras_preprocess
from tensorflow.keras.preprocessing.image import img_to_array

def load_classifier_with_architecture(classifier_path):
    """Load classifier by rebuilding architecture then loading weights"""
    from tensorflow.keras.applications import MobileNetV3Small
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import GlobalAveragePooling2D, Dense, Dropout
    from tensorflow.keras.regularizers import l2
    
    # Rebuild the exact architecture from your training
    base_model = MobileNetV3Small(
        input_shape=(224, 224, 3),
        include_top=False,
        weights=None  # Don't load ImageNet weights
    )
    
    model = Sequential([
        base_model,
        GlobalAveragePooling2D(),
        Dense(256, activation='relu', kernel_regularizer=l2(0.001)),
        Dropout(0.4),
        Dense(5, activation='softmax')  # 5 classes
    ])
    
    # Load only the weights
    model.load_weights(classifier_path)
    
    return model

def process_video(
    video_path,
    start_dt=None,
    resize_dim=(640, 480),
    denoise=False,
    roi_points=None,
    model_path="yolo11n.pt",
    classifier_path="mobilenetv3_original.keras",
    detection_interval=1,
    confidence_threshold=0.4,
    min_w=10,
    min_h=10,
    classification_threshold=0.4,
    custom_classes=None,
    save_annotated=None
):
    """
    Run vehicle detection, tracking, classification, and ROI counting on a video file.

    Returns: dict with counts per class (including 'Unclassified'), and optionally the path to annotated video.
    """
    # Default class names and classifier classes if not supplied
    yolo_class_names = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
    if custom_classes is None:
        custom_classes = [
            "Commercial Vehicles",
            "High-End Vehicles",
            "Low-End Vehicles",
            "Mid-Range Vehicles",
            "Motorcycle"
        ]

    # Load models
    yolo_model = YOLO(model_path)
    # Add detailed error handling
    try:
        print(f"Loading classifier from: {classifier_path}")
        print(f"TensorFlow version: {tf.__version__}")
        
        # Try loading weights only approach
        classifier_model = load_classifier_with_architecture(classifier_path)
        
    except Exception as e:
        print(f"Failed to load classifier: {e}")
        print("Attempting alternative loading method...")
        
        # Fallback: load with safe_mode=False
        classifier_model = tf.keras.models.load_model(
            classifier_path,
            compile=False,
            safe_mode=False
        )

    import datetime
    if start_dt is None:
        start_dt = datetime.datetime.now()

    # Video setup
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = resize_dim
    if roi_points is None:
        # Default: middle half of frame as ROI for counting
        y0 = int(h/4)      # e.g. 480/4= 120
        y1 = int(h*3/4)   # e.g. 480*3/4= 360
        x0 = int(w/4)     # e.g. 640/4= 160
        x1 = int(w*3/4)   # e.g. 640*3/4= 480
        roi_points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # Rectangle
    roi_polygon = np.array(roi_points, dtype=np.int32)    # OpenCV polygon

    # Annotated video output (optional)
    if save_annotated:
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        out_writer = cv2.VideoWriter(save_annotated+".avi", fourcc, fps, (w, h))
    else:
        out_writer = None

    # Tracking and counting setup
    deepsort = DeepSort(max_age=15, n_init=2, nms_max_overlap=1.0, max_cosine_distance=0.2, nn_budget=25, embedder="mobilenet", embedder_gpu=True)
    track_classes = {}
    track_memory = {}
    class_counts = {name: 0 for name in custom_classes}
    class_counts["Unclassified"] = 0

    time_series = []  # Will store one entry per frame (or per N seconds)
    frame_idx = 0

    import time

    max_retries = 10   # Max consecutive failed reads before exit
    retry_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            retry_count += 1
            print(f"Failed to grab frame, retry {retry_count}/{max_retries}")
            time.sleep(1)  # Brief wait before retry
            if retry_count >= max_retries:
                print("Stream appears to be down. Ending processing.")
                break
            continue
        retry_count = 0  # Reset on successful frame
        frame_idx += 1
        # frame_time_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        # real_timestamp = start_dt + datetime.timedelta(seconds=frame_time_sec)
        if fps > 1 and not (
            isinstance(video_path, str) and 
            (video_path.startswith("http") or video_path.startswith("rtsp"))
        ):
            frame_time_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        else:
            frame_time_sec = frame_idx / fps

        try:
            real_timestamp = start_dt + datetime.timedelta(seconds=frame_time_sec)
        except OverflowError:
            real_timestamp = datetime.datetime.now()

        # When saving to time_series:
        time_series.append({
            "timestamp": real_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            **class_counts.copy()
        })
        frame_resized = cv2.resize(frame, resize_dim)
        if denoise:
            frame_resized = cv2.fastNlMeansDenoisingColored(frame_resized, None, 10, 10, 7, 21)

        # Detection & Tracking
        if frame_idx % detection_interval == 0:
            yolo_results = yolo_model(frame_resized, verbose=False)
            detections_for_tracker = []
            for result in yolo_results:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    if conf < confidence_threshold: continue
                    if cls_id in yolo_class_names:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        detections_for_tracker.append(([x1, y1, x2, y2, conf], cls_id))
            bbs = []
            for box_data, cls_id in detections_for_tracker:
                x1, y1, x2, y2, conf = box_data
                w_box, h_box = x2 - x1, y2 - y1
                bbs.append([[x1, y1, w_box, h_box], conf, cls_id])
            tracks = deepsort.update_tracks(bbs, frame=frame_resized)
        else:
            tracks = deepsort.update_tracks([], frame=frame_resized)

        # ROI Counting & On-demand classification
        for track in tracks:
            if not track.is_confirmed():
                continue
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            track_id = track.track_id
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            mem = track_memory.get(track_id, {"inside_roi": False, "counted": False})
            was_inside = mem["inside_roi"]
            counted = mem["counted"]
            now_inside = cv2.pointPolygonTest(roi_polygon, (cx, cy), False) >= 0

            if not was_inside and now_inside and not counted:
                # Only classify at counting time
                crop = frame_resized[y1:y2, x1:x2]
                if crop.shape[0] >= min_h and crop.shape[1] >= min_w:
                    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    small = cv2.resize(rgb, (224, 224))
                    arr = img_to_array(small)
                    arr = keras_preprocess(arr)
                    arr = np.expand_dims(arr, axis=0)
                    probs = classifier_model.predict(arr)
                    lab = np.argmax(probs)
                    conf = np.max(probs)
                    if conf >= classification_threshold:
                        cls_label = custom_classes[lab]
                    else:
                        cls_label = "Unclassified"
                else:
                    cls_label = "Unclassified"
                track_classes[track_id] = cls_label
                class_counts[cls_label] += 1
                counted = True
            else:
                cls_label = track_classes.get(track_id, "Unclassified")
            track_memory[track_id] = {"inside_roi": now_inside, "counted": counted}


            color = (0, 255, 0)
            cv2.rectangle(frame_resized, (x1, y1), (x2, y2), color, 2)
            label_text = f"ID:{track_id} {cls_label}"
            cv2.putText(frame_resized, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.polylines(frame_resized, [roi_polygon], isClosed=True, color=(0, 255, 255), thickness=2)
        count_text = " | ".join([f"{k}: {v}" for k, v in class_counts.items()])
        cv2.putText(frame_resized, count_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 2)
        cv2.imshow('Processing', frame_resized)
        key = cv2.waitKey(30) & 0xFF  # Wait longer for reliable keypress
        if key == ord('q'):
            print("[INFO] 'q' pressed, exiting loop.")
            break
        if out_writer:
            out_writer.write(frame_resized)

    cap.release()
    cv2.destroyAllWindows()
    if out_writer:
        out_writer.release()
    # Return counts and time-series data
    result = {
        "counts": class_counts,
        "time_series": time_series,
    }

    return result
