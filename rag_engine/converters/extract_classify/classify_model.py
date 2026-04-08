import joblib
import os
import json
from .insights import main_ex
from .extractor import extract_document_lines


# DYNAMIC CONFIGURATION LOADER
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "..", "..", "..", "config.json")

try:
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    # Default fallback if config is missing
    config = {
        "active_model": "heading_classifierv2.joblib", 
        "heading_threshold": 0.70
    }

MODEL_FILENAME = config.get("active_model", "heading_classifierv2.joblib")
# Assumes model files are in the root directory
MODEL_PATH = os.path.join(BASE_DIR, "..", "..", "..", MODEL_FILENAME)
THRESHOLD = config.get("heading_threshold", 0.70)


# LOAD MODEL & METADATA
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Could not find model '{MODEL_FILENAME}' at {MODEL_PATH}.")

artifact = joblib.load(MODEL_PATH)
model = artifact["model"]

# Safe label mapping fallback
if "label_map" in artifact:
    label_map = artifact["label_map"]
else:
    label_map = {"PARAGRAPH": 0, "HEADING": 1}
inv_label_map = {v: k for k, v in label_map.items()}

# If the model has internal feature ordering, we use it. 
# Older models won't have this, which triggers our hybrid logic below.
FEATURE_ORDER = artifact.get("feature_order", [])

# HYBRID FEATURE ALIGNMENT
def line_to_features(line, insights):
    fonts = set(line.get("style_stats", {}).keys())
    sizes = set(line.get("size_stats", {}).keys())
    
    # Pre-calculate the 20-feature superset
    is_bold = int(any("bold" in str(f).lower() or "heavy" in str(f).lower() or "black" in str(f).lower() for f in fonts))

    features_dict = {
        "word_count": line.get("word_count", 0),
        "char_length": line.get("char_length", 0),
        "is_upper": line.get("is_upper", 0),
        "is_title": line.get("is_title", 0),
        "upper_ratio": line.get("upper_ratio", 0.0),
        "is_bold": is_bold,
        "has_symbol": int(line.get("has_symbol", False)),
        "starts_with_number": int(line.get("starts_with_number", False)),
        "ends_with_punctuation": int(line.get("ends_with_punctuation", False)),
        "is_paragraph_font": int(insights.get("paragraph_font") in fonts),
        "is_heading_font": int(any(f in insights.get("heading_font", []) for f in fonts)),
        "is_paragraph_size": int(insights.get("paragraph_size") in sizes),
        "is_heading_size": int(insights.get("heading_size") in sizes if insights.get("heading_size") else 0),
        "normalized_top": round(line.get("layout", {}).get("top", 0) / 800, 3),
        "is_tiny": line.get("is_tiny", 0),
        "is_numeric_only": line.get("is_numeric_only", 0),
        "alpha_ratio": round(line.get("alpha_ratio", 0), 3),
        "digit_ratio": round(line.get("digit_ratio", 0), 3),
        "symbol_ratio": round(line.get("symbol_ratio", 0), 3),
        "has_math_symbol": line.get("has_math_symbol", 0)
    }
    
    # PATH 1: Trust internal metadata if it exists
    if FEATURE_ORDER:
        return [features_dict.get(f, 0) for f in FEATURE_ORDER]
    
    # PATH 2: V2 NEW MODEL FALLBACK (20 Features)
    if "v2" in MODEL_FILENAME.lower() or MODEL_FILENAME == "heading_classifierv2.joblib":
        return [
            features_dict["word_count"], features_dict["char_length"], features_dict["is_upper"],
            features_dict["is_title"], features_dict["upper_ratio"], features_dict["is_bold"],
            features_dict["has_symbol"], features_dict["starts_with_number"], features_dict["ends_with_punctuation"],
            features_dict["is_paragraph_font"], features_dict["is_heading_font"], features_dict["is_paragraph_size"],
            features_dict["is_heading_size"], features_dict["normalized_top"], features_dict["is_tiny"],
            features_dict["is_numeric_only"], features_dict["alpha_ratio"], features_dict["digit_ratio"],
            features_dict["symbol_ratio"], features_dict["has_math_symbol"]
        ]
    
    # PATH 3: V1 OLD MODEL FALLBACK (The original 13 features exactly as provided)
    return [
        features_dict["word_count"],
        features_dict["has_symbol"],
        features_dict["starts_with_number"],
        features_dict["ends_with_punctuation"],
        features_dict["is_paragraph_font"],
        features_dict["is_heading_size"],
        features_dict["normalized_top"],
        features_dict["is_tiny"],
        features_dict["is_numeric_only"],
        features_dict["alpha_ratio"],
        features_dict["digit_ratio"],
        features_dict["symbol_ratio"],
        features_dict["has_math_symbol"]
    ]


# MAIN CLASSIFICATION API
def classify_pdf(pdf_path):
    """
    Called by structuring_json.py.
    Returns a list of dicts with 'page_index', 'line_index', 'label', and 'text'.
    """
    lines = extract_document_lines(pdf_path)
    insights = main_ex(lines)

    if not lines:
        return []

    # BATCH OPTIMIZATION: Process all features into a matrix first
    f_matrix = [line_to_features(line, insights) for line in lines]

    structured_output = []

    # Prefer probability for precision control, fallback to direct prediction for older models
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(f_matrix)
        
        for i, line in enumerate(lines):
            # Index 1 corresponds to HEADING
            heading_prob = probs[i][1] 
            label = "HEADING" if heading_prob >= THRESHOLD else "PARAGRAPH"
            
            structured_output.append({
                "page_index": line.get("page_index", 0),
                "line_index": line.get("line_index", 0),
                "label": label,
                "text": line.get("text", "")
            })
    else:
        # Standard fallback for basic predict()
        preds = model.predict(f_matrix)
        for i, line in enumerate(lines):
            label = inv_label_map.get(preds[i], "PARAGRAPH")
            
            structured_output.append({
                "page_index": line.get("page_index", 0),
                "line_index": line.get("line_index", 0),
                "label": label,
                "text": line.get("text", "")
            })

    return structured_output

# Example usage in case to test the classify_pdf function directly without running the whole server
#remove the triple quotes to run this test
'''
if __name__ == "__main__":
    # Test block
    PDF_TEST = "test5.pdf"
    results = classify_pdf(PDF_TEST)
    for item in results: # Print first 10 for verification
        print(f"[{item['label']:^10}] :: {item['text'][:50]}")'''
