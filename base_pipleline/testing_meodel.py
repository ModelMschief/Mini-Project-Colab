import joblib
from check import extract_pdf_lines, main_ex

# -----------------------------
# CONFIG
# -----------------------------

MODEL_PATH = "heading_classifier.joblib"
PDF_PATH = "modularity\\pdfs\\test3.pdf"   # change this to the PDF you want to test


# -----------------------------
# LOAD MODEL
# -----------------------------

artifact = joblib.load(MODEL_PATH)
model = artifact["model"]
label_map = artifact["label_map"]
inv_label_map = {v: k for k, v in label_map.items()}


# -----------------------------
# FEATURE EXTRACTION
# -----------------------------

def line_to_features(line, insights):
    fonts = set(line["style_stats"].keys())
    sizes = set(line["size_stats"].keys())

    return [
        line["word_count"],
        int(line["has_symbol"]),
        int(line["starts_with_number"]),
        int(line["ends_with_punctuation"]),
        int(insights.get("paragraph_font") in fonts),
        int(insights.get("heading_size") in sizes if insights.get("heading_size") else 0),
        round(line["layout"]["top"] / 800, 3),
    ]


# -----------------------------
# RUN TEST
# -----------------------------

print(f"\n[+] Testing model on: {PDF_PATH}\n")

lines = extract_pdf_lines(PDF_PATH)
insights = main_ex(PDF_PATH)

for line in lines:
    features = line_to_features(line, insights)
    pred = model.predict([features])[0]

    label = inv_label_map[pred]

    print(
        f"[Page {line['page_index']:>2} | Line {line['line_index']:>3}] "
        f"{label:<9} :: {line['text']}"
    )

print("\n[✓] Test complete")
