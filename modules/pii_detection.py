# ====================== FIXED PII DETECTION MODULE ======================
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from tqdm import tqdm
import re

# -------------------- Initialize Presidio Analyzer --------------------
analyzer = AnalyzerEngine()

# --- REMOVE noisy built-in recognizers ---
from presidio_analyzer import RecognizerRegistry

# Remove noisy or irrelevant recognizers
REMOVE_RECOGNIZERS = [
    "URLRecognizer", "URL", "US_BANK_NUMBER", "US_DRIVER_LICENSE",
    "NRP", "LOCATION", "PERSON", "DATE_TIME"
]

for recognizer_name in REMOVE_RECOGNIZERS:
    try:
        recognizer_to_remove = None
        for r in analyzer.registry.recognizers:
            if r.name == recognizer_name or \
               (r.supported_entities and recognizer_name in r.supported_entities):
                recognizer_to_remove = r
                break

        if recognizer_to_remove:
            analyzer.registry.remove_recognizer(recognizer_to_remove)
    except:
        pass

# --- ADD custom URL recognizer (optional but controlled) ---
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

# --- Custom Employee ID recognizer ---
emp_id_pattern = Pattern(name="EMP_ID", regex=r"\bEMP\d{3,6}\b", score=0.9)
emp_id_recognizer = PatternRecognizer(supported_entity="EMP_ID", patterns=[emp_id_pattern])
analyzer.registry.add_recognizer(emp_id_recognizer)

# -------------------- Helper: Detect PII --------------------
def detect_pii_presidio(text):
    """Detect PII entities using Presidio and custom recognizers."""
    if not isinstance(text, str) or not text.strip():
        return []

    results = analyzer.analyze(text=text, language="en")

    # Cleaned, safe PII types only
    pii_types = list({r.entity_type for r in results})

    # STRICT FILTER — Remove all metadata and non-PII
    FILTER_OUT = {
        "URL",          # Important → URL ≠ PII
        "DATE_TIME",
        "LOCATION",
        "PERSON",
        "NRP",
        "US_DRIVER_LICENSE",
        "US_BANK_NUMBER",
        "PHONE_NUMBER"  # optional
    }

    pii_types = [p for p in pii_types if p not in FILTER_OUT]

    return pii_types


# -------------------- Core detection --------------------
def run_pii_detection(df, text_columns):
    """
    Applies strict PII detection and stores:
    - pii_entities (clean list of PII types)
    - pii_detailed (list of {origin_col, entities})
    """
    tqdm.pandas(desc="🔎 Running strict PII detection")

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
    df["pii_score"] = df["pii_entities"].apply(lambda ents: 1 if ents else 0)

    return df


# -------------------- Wrapper --------------------
def run_for_all(serviceDf, providerDf):
    serviceDf = run_pii_detection(serviceDf, ["title", "description"])
    providerDf = run_pii_detection(providerDf, ["name", "about"])
    return serviceDf, providerDf
