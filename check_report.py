import json
with open("run4_report.json", encoding="utf-8") as f:
    data = json.load(f)
from collections import Counter
diseases = Counter(r["disease"] for r in data["regions"])
print(diseases)
print("Total flagged:", data["total_flagged"], "of", data["total_regions_evaluated"])
