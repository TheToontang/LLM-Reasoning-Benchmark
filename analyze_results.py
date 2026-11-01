
import csv
from pathlib import Path

# 1. Locate the results file
BASE_DIR = Path(__file__).resolve().parent
RESULTS_PATH = BASE_DIR / "results" / "experiment_results.csv"

# 2. Read the experiment results
with open(RESULTS_PATH, "r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)
    results = list(reader)

# 3. Count total and correct responses
total = len(results)
correct = sum(
    1 for row in results
    if row["Evaluation"] == "Correct"
    and row["Status"] == "success"
)

# 4. Calculate accuracy
accuracy = (correct / total * 100) if total else 0

# 5. Display the summary
print("=== Benchmark Result Analysis ===")
print(f"Total Questions: {total}")
print(f"Correct Answers: {correct}")
print(f"Accuracy: {accuracy:.2f}%")

# 6. Accuracy by category
print("\n=== Accuracy by Category ===")

categories = ["logical", "deductive", "constraint"]

for category in categories:
    category_rows = [
        row for row in results
        if row["Category"] == category
    ]

    category_correct = sum(
        1 for row in category_rows
        if row["Evaluation"] == "Correct"
        and row["Status"] == "success"
    )

    category_total = len(category_rows)
    category_accuracy = (
        category_correct / category_total * 100
        if category_total else 0
    )

    print(
        f"{category}: {category_correct}/{category_total} "
        f"({category_accuracy:.2f}%)"
    )


# 7. Accuracy by variant
print("\n=== Accuracy by Variant ===")

variants = ["original", "paraphrased", "typo"]

for variant in variants:
    variant_rows = [
        row for row in results
        if row["Variant"] == variant
    ]

    variant_correct = sum(
        1 for row in variant_rows
        if row["Evaluation"] == "Correct"
        and row["Status"] == "success"
    )

    variant_total = len(variant_rows)
    variant_accuracy = (
        variant_correct / variant_total * 100
        if variant_total else 0
    )

    print(
        f"{variant}: {variant_correct}/{variant_total} "
        f"({variant_accuracy:.2f}%)"
    )

# 8. Latency analysis
print("\n=== Latency Analysis ===")

# Only include successful responses
valid_rows = [
    row for row in results
    if row["Status"] == "success"
    and row["Latency_Seconds"] != ""
]

latencies = [
    float(row["Latency_Seconds"])
    for row in valid_rows
]

if latencies:
    average_latency = sum(latencies) / len(latencies)

    print(f"Average Latency: {average_latency:.3f} seconds")
    print(f"Minimum Latency: {min(latencies):.3f} seconds")
    print(f"Maximum Latency: {max(latencies):.3f} seconds")


# 9. Average latency by category
print("\n=== Average Latency by Category ===")

for category in categories:
    category_latencies = [
        float(row["Latency_Seconds"])
        for row in valid_rows
        if row["Category"] == category
    ]

    if category_latencies:
        average = sum(category_latencies) / len(category_latencies)
        print(f"{category}: {average:.3f} seconds")


# 10. Average latency by variant
print("\n=== Average Latency by Variant ===")

for variant in variants:
    variant_latencies = [
        float(row["Latency_Seconds"])
        for row in valid_rows
        if row["Variant"] == variant
    ]

    if variant_latencies:
        average = sum(variant_latencies) / len(variant_latencies)
        print(f"{variant}: {average:.3f} seconds")


# 11. Find the slowest questions
print("\n=== Top 5 Slowest Responses ===")

slowest_rows = sorted(
    valid_rows,
    key=lambda row: float(row["Latency_Seconds"]),
    reverse=True
)[:5]

for row in slowest_rows:
    print(
        f"{row['Question_ID']} ({row['Variant']}): "
        f"{float(row['Latency_Seconds']):.3f} seconds"
    )

# 12. Generate latency chart
import matplotlib.pyplot as plt

chart_categories = []
chart_latencies = []

for category in categories:
    values = [
        float(row["Latency_Seconds"])
        for row in valid_rows
        if row["Category"] == category
    ]

    if values:
        chart_categories.append(category.capitalize())
        chart_latencies.append(sum(values) / len(values))

# Create a folder for charts
CHARTS_DIR = BASE_DIR / "results" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

plt.figure(figsize=(8, 5))

bars = plt.bar(chart_categories, chart_latencies)

plt.title("Average API Latency by Reasoning Category")
plt.xlabel("Reasoning Category")
plt.ylabel("Average Latency (seconds)")

# Display the value above each bar
for bar, value in zip(bars, chart_latencies):
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.05,
        f"{value:.3f}s",
        ha="center"
    )

plt.ylim(0, max(chart_latencies) * 1.2)
plt.tight_layout()

# Save chart
chart_path = CHARTS_DIR / "latency_by_category.png"
plt.savefig(chart_path, dpi=300)
plt.close()

print(f"\nChart saved to: {chart_path}")

# 13. Generate latency chart by variant
variant_names = []
variant_averages = []

for variant in variants:
    values = [
        float(row["Latency_Seconds"])
        for row in valid_rows
        if row["Variant"] == variant
    ]

    if values:
        variant_names.append(variant.capitalize())
        variant_averages.append(sum(values) / len(values))

plt.figure(figsize=(8, 5))

bars = plt.bar(variant_names, variant_averages)

plt.title("Average API Latency by Question Variant")
plt.xlabel("Question Variant")
plt.ylabel("Average Latency (seconds)")

for bar, value in zip(bars, variant_averages):
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.05,
        f"{value:.3f}s",
        ha="center"
    )

plt.ylim(0, max(variant_averages) * 1.2)
plt.tight_layout()

chart_path = CHARTS_DIR / "latency_by_variant.png"
plt.savefig(chart_path, dpi=300)
plt.close()

print(f"Chart saved to: {chart_path}")
