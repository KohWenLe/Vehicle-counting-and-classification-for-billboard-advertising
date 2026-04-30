from collections import defaultdict
from datetime import datetime


CUSTOM_CLASSES = [
    "Commercial Vehicles",
    "High-End Vehicles",
    "Low-End Vehicles",
    "Mid-Range Vehicles",
    "Motorcycle",
    "Unclassified",
]


def _parse_timestamp(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def analyze_results(time_series, class_counts):
    if not time_series:
        return {"peak": None, "recommendations": ["No vehicles detected."]}

    hourly_new = defaultdict(int)
    previous_total = None

    for point in time_series:
        timestamp = _parse_timestamp(point["timestamp"])
        total = sum(int(point.get(vehicle_class, 0)) for vehicle_class in CUSTOM_CLASSES)
        if previous_total is None:
            new_vehicles = total
        else:
            new_vehicles = max(0, total - previous_total)
        hourly_new[timestamp.hour] += int(new_vehicles)
        previous_total = total

    peak_hour, peak_count = max(hourly_new.items(), key=lambda item: (item[1], -item[0]))

    total_vehicles = sum(class_counts.get(vehicle_class, 0) for vehicle_class in CUSTOM_CLASSES if vehicle_class != "Unclassified")
    unclassified_count = class_counts.get("Unclassified", 0)

    classified_classes = [
        vehicle_class
        for vehicle_class in CUSTOM_CLASSES
        if vehicle_class != "Unclassified" and class_counts.get(vehicle_class, 0) > 0
    ]

    if classified_classes:
        class_max = max(classified_classes, key=lambda vehicle_class: class_counts[vehicle_class])
        class_min = min(classified_classes, key=lambda vehicle_class: class_counts[vehicle_class])
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

    recommendations = []

    if total_vehicles and unclassified_count > total_vehicles:
        recommendations.append("Warning: More than half of vehicles could not be classified. Data quality may be low. Check video clarity or retrain model.")

    if class_max:
        max_pct = (class_counts[class_max] / total_vehicles) * 100 if total_vehicles else 0.0
        recommendations.append(
            f"Most detected vehicles are '{class_max}' ({class_counts[class_max]} vehicles, {max_pct:.1f}% of classified). Recommended ads: {ad_map.get(class_max, 'General ads')}."
        )

    if class_min and class_min != class_max and total_vehicles and class_counts[class_min] / total_vehicles < 0.1:
        recommendations.append(
            f"Very few '{class_min}' vehicles detected ({class_counts[class_min]}). Ads targeting this group may be less effective."
        )

    if len(classified_classes) > 1:
        values = [class_counts[vehicle_class] for vehicle_class in classified_classes]
        max_value = max(values)
        min_value = min(values)
        if max_value and max_value - min_value < 0.15 * max_value:
            recommendations.append("Vehicle class distribution is fairly even. Consider mixed or general ads.")

    recommendations.append(
        f"Peak detected traffic is at {peak_hour}:00 ({peak_count} vehicles/hour). Show high-impact ads during this period for maximum reach."
    )

    return {
        "peak": {"hour": int(peak_hour), "count": int(peak_count)},
        "recommendations": recommendations,
    }
