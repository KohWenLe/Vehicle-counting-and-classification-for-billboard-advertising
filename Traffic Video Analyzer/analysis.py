import pandas as pd

def analyze_results(time_series, class_counts):
    custom_classes = [
        "Commercial Vehicles",
        "High-End Vehicles",
        "Low-End Vehicles",
        "Mid-Range Vehicles",
        "Motorcycle",
        "Unclassified"
    ]

    df = pd.DataFrame(time_series)
    if df.empty:
        return {"peak": None, "recommendations": ["No vehicles detected."]}

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df['total'] = df[custom_classes].sum(axis=1)
    df['new_vehicles'] = df['total'].diff().fillna(df['total'])  # First row is the total itself
    hourly_new = df.groupby('hour')['new_vehicles'].sum()
    peak_hour = int(hourly_new.idxmax())
    peak_count = int(hourly_new.max())
    total_vehicles = sum(class_counts.get(c, 0) for c in custom_classes if c != "Unclassified")
    unclassified_count = class_counts.get("Unclassified", 0)

    # Get main and rare classes
    classified_classes = [k for k in custom_classes if k != "Unclassified" and class_counts.get(k, 0) > 0]
    if classified_classes:
        class_max = max(classified_classes, key=lambda k: class_counts[k])
        class_min = min(classified_classes, key=lambda k: class_counts[k])
    else:
        class_max = None
        class_min = None

    ad_map = {
        "High-End Vehicles": "Luxury car brands, high-end electronics, real estate, premium watches.",
        "Mid-Range Vehicles": "Popular brands, family cars, household electronics, family insurance.",
        "Low-End Vehicles": "Budget-friendly products, affordable food, basic smartphones, prepaid services.",
        "Commercial Vehicles": "Fleet management, logistics, fuel cards, business insurance, tire services.",
        "Motorcycle": "Motorbike accessories, fast food, beverages, helmets, delivery rider promotions.",
    }

    recs = []

    # 1. Data quality warning
    if unclassified_count > total_vehicles:
        recs.append("Warning: More than half of vehicles could not be classified. Data quality may be low. Check video clarity or retrain model.")

    # 2. Dominant class recommendation
    if class_max:
        max_pct = (class_counts[class_max] / (total_vehicles + 1e-9)) * 100  # Avoid zero division
        recs.append(
            f"Most detected vehicles are '{class_max}' ({class_counts[class_max]} vehicles, {max_pct:.1f}% of classified). Recommended ads: {ad_map.get(class_max, 'General ads')}."
        )

    # 3. Niche/rare class insight
    if class_min and class_min != class_max and class_counts[class_min] / (total_vehicles + 1e-9) < 0.1:
        recs.append(
            f"Very few '{class_min}' vehicles detected ({class_counts[class_min]}). Ads targeting this group may be less effective."
        )

    # 4. Even distribution insight
    if len(classified_classes) > 1:
        values = [class_counts[k] for k in classified_classes]
        maxval = max(values)
        minval = min(values)
        if maxval - minval < 0.15 * maxval:
            recs.append("Vehicle class distribution is fairly even. Consider mixed or general ads.")

    # 5. Peak hour recommendation
    recs.append(f"Peak detected traffic is at {peak_hour}:00 ({peak_count} vehicles/hour). Show high-impact ads during this period for maximum reach.")

    return {
        "peak": {"hour": peak_hour, "count": peak_count},
        "recommendations": recs
    }
