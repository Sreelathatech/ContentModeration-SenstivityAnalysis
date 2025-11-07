# ====================== PII DETECTION MODULE ======================
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from tqdm import tqdm
import re

# -------------------- Initialize Presidio Analyzer --------------------
analyzer = AnalyzerEngine()

# --- REMOVE noisy built-in recognizers ---
from presidio_analyzer import RecognizerRegistry

for recognizer_name in ["URLRecognizer", "US_BANK_NUMBER", "US_DRIVER_LICENSE"]:
    try:
        # Find matching recognizer by class name or entity type
        recognizer_to_remove = None
        for r in analyzer.registry.recognizers:
            if r.name == recognizer_name or (
                r.supported_entities and recognizer_name in r.supported_entities
            ):
                recognizer_to_remove = r
                break

        if recognizer_to_remove:
            analyzer.registry.remove_recognizer(recognizer_to_remove)
            print(f"✅ Removed built-in recognizer: {recognizer_name}")
        else:
            print(f"⚠️ Recognizer not found: {recognizer_name}")
    except Exception as e:
        print(f"⚠️ Could not remove recognizer {recognizer_name}: {e}")

# --- ADD a stricter custom URL recognizer ---
custom_url_pattern = Pattern(
    name="custom_url_pattern",
    regex=r"\b(?:https?://|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?\b",
    score=0.85,
)

custom_url_recognizer = PatternRecognizer(
    supported_entity="URL",
    patterns=[custom_url_pattern],
    context=["website", "link", "page", "web"],
)

analyzer.registry.add_recognizer(custom_url_recognizer)
print("✅ Registered custom URL recognizer")

# --- ADD custom recognizer for Employee ID (e.g., EMP12345) ---
emp_id_pattern = Pattern(name="EMP_ID", regex=r"\bEMP\d{3,6}\b", score=0.9)
emp_id_recognizer = PatternRecognizer(supported_entity="EMP_ID", patterns=[emp_id_pattern])
analyzer.registry.add_recognizer(emp_id_recognizer)
print("✅ Registered custom Employee ID recognizer")

# -------------------- Helper: Detect PII --------------------
def detect_pii_presidio(text):
    """Detect PII entities using Microsoft Presidio + custom regex."""
    if not isinstance(text, str) or not text.strip():
        return []
    results = analyzer.analyze(text=text, language="en")
    pii_types = list({r.entity_type for r in results})
    # Filter out common noisy entities
    pii_types = [p for p in pii_types if p not in ["DATE_TIME", "NRP", "LOCATION", "PERSON","UK_NHS","US_DRIVER_LICENSE", "US_BANK_NUMBER"]]
    return pii_types


# -------------------- Helper: Compute binary score --------------------
def compute_pii_score(pii_entities):
    """1 if any PII entity detected, else 0"""
    return int(bool(pii_entities))


# -------------------- Core detection for a single DataFrame --------------------
def run_pii_detection(df, text_columns):
    """
    Apply Presidio PII detection on multiple columns in a DataFrame.
    Adds `pii_entities` (aggregated) and `pii_detailed` (per-column mapping).
    """
    tqdm.pandas(desc="🔎 Running Presidio PII detection")

    def extract_entities_per_row(row):
        detailed = []
        all_entities = []
        for col in text_columns:
            val = row.get(col)
            if isinstance(val, str) and val.strip():
                ents = detect_pii_presidio(val)
                if ents:
                    detailed.append({"origin_col": col, "entities": ents})
                    all_entities.extend(ents)
        return {
            "pii_detailed": detailed,
            "pii_entities": list({e for e in all_entities}),
        }

    extracted = df.progress_apply(extract_entities_per_row, axis=1)
    df["pii_entities"] = extracted.apply(lambda x: x["pii_entities"])
    df["pii_detailed"] = extracted.apply(lambda x: x["pii_detailed"])
    df["pii_score"] = df["pii_entities"].apply(compute_pii_score)
    return df


# -------------------- Run detection for both DFs --------------------
def run_for_all(serviceDf, providerDf):
    print("🔍 Running PII detection on Services...")
    serviceDf = run_pii_detection(serviceDf, ["title", "description"])

    print("🔍 Running PII detection on Providers...")
    providerDf = run_pii_detection(providerDf, ["name", "about"])

    return serviceDf, providerDf
