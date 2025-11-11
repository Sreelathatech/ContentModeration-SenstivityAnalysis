"""
report_generation.py

Compute per-row moderation signals:
- toxicity_score (max across toxicity columns)
- toxicity_matches (list of {origin_col, value, score}) for columns that exceed threshold
- pii_score (0/1) and pii_matches (list of {origin_col, value}) using regex extraction (email, phone, emp_id, etc.)
- nsfw_score (max across nsfw columns)
- nsfw_matches (list of candidate image URLs found in image columns) -- flagged URLs are finalized in grouping

This module avoids grouping and does not produce final `content`.
It's intended to be called after detection modules (PII/Toxicity/NSFW) have run.
"""

import re
import ast
import pandas as pd
from tqdm import tqdm

tqdm.pandas()

# ===============================================================
# Default thresholds
# ===============================================================
TOXICITY_THRESHOLD = 0.6
NSFW_THRESHOLD = 0.7

# ===============================================================
# Regex patterns for PII detection
# ===============================================================
_EMAIL_RE = re.compile(r"[a-zA-Z0-9.\-_+]+@[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-.]+")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{10}|\d{3}[-.\s]\d{3}[-.\s]\d{4})\b")
_EMP_ID_RE = re.compile(r"\b(?:EMP|Emp|emp)[-_]?\d{3,6}\b")  # Matches EMP12345, emp-00123, etc.

# Add any new PII regexes here
_PII_REGEXES = {
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
    "emp_id": _EMP_ID_RE,
}

# ===============================================================
# Utility functions
# ===============================================================
def _safe_float(v):
    try:
        if pd.isna(v):
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _collect_image_columns(df):
    return [c for c in df.columns if "image" in c.lower() or "image_url" in c.lower()]


def _collect_toxicity_columns(df):
    return [c for c in df.columns if "toxicity" in c.lower()]


def _collect_nsfw_columns(df):
    return [c for c in df.columns if "nsfw" in c.lower()]


def _extract_values_by_regex(text):
    """Return list of matches across all PII regexes for a single text value."""
    found = []
    if not isinstance(text, str) or not text.strip():
        return found
    for name, rx in _PII_REGEXES.items():
        for m in rx.findall(text):
            found.append(m)
    return list(dict.fromkeys(found))  # dedupe preserving order

# ===============================================================
# Main generator
# ===============================================================
def generate_reporting_columns(df: pd.DataFrame, text_columns=None, image_columns=None):
    """
    Enrich df with intermediate columns useful for grouping stage.
    - text_columns: list of text columns to scan for toxicity/PII origin details
    - image_columns: list of image columns to inspect for URLs
    """
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # Auto-detect likely text columns
    if text_columns is None:
        candidates = ["title", "description", "tags", "name", "about"]
        text_columns = [c for c in candidates if c in df.columns]

    # Auto-detect image columns
    if image_columns is None:
        image_columns = _collect_image_columns(df)

    # -----------------------------------------------------------
    # TOXICITY
    # -----------------------------------------------------------
    tox_cols = _collect_toxicity_columns(df)
    if tox_cols:
        df[tox_cols] = df[tox_cols].applymap(_safe_float)
        df["toxicity_score"] = df[tox_cols].max(axis=1)
    else:
        df["toxicity_score"] = 0.0

    # Map text column to possible toxicity score column (e.g. title_toxicity)
    text_to_toxcol = {}
    for tcol in text_columns:
        matching = [c for c in tox_cols if c.startswith(tcol + "_")]
        text_to_toxcol[tcol] = matching[0] if matching else None

    def _row_toxicity_matches(row):
        matches = []
        for tcol, toxcol in text_to_toxcol.items():
            if toxcol and toxcol in row:
                score = _safe_float(row.get(toxcol, 0.0))
                if score > TOXICITY_THRESHOLD:
                    val = row.get(tcol, "")
                    matches.append({"origin_col": tcol, "value": val, "score": round(score, 3)})
        return matches

    df["toxicity_matches"] = df.progress_apply(_row_toxicity_matches, axis=1)

    # -----------------------------------------------------------
    # PII (regex + Presidio)
    # -----------------------------------------------------------
    if "pii_entities" in df.columns:
        if "pii_score" not in df.columns:
            df["pii_score"] = df["pii_entities"].apply(lambda x: 1 if x and len(x) > 0 else 0)
    else:
        df["pii_score"] = 0

    def _row_pii_matches(row):
        matches = []
        for tcol in text_columns:
            txt = row.get(tcol, "")
            found = _extract_values_by_regex(str(txt))
            for v in found:
                matches.append({"origin_col": tcol, "value": v})
        pres = row.get("pii_entities")
        if pres and isinstance(pres, (list, tuple)) and len(pres) > 0:
            matches.append({"origin_col": "pii_entities", "value": pres})
        return matches

    df["pii_matches"] = df.progress_apply(_row_pii_matches, axis=1)

    # -----------------------------------------------------------
    # NSFW
    # -----------------------------------------------------------
    nsfw_cols = _collect_nsfw_columns(df)
    if nsfw_cols:
        df[nsfw_cols] = df[nsfw_cols].applymap(_safe_float)
        df["nsfw_score"] = df[nsfw_cols].max(axis=1)
        df["nsfw_flag"] = df["nsfw_score"].apply(lambda x: 1 if x > 0.7 else 0)

    else:
        df["nsfw_score"] = df.get("nsfw_score", 0.0).map(_safe_float) if "nsfw_score" in df.columns else 0.0

    # Build image URL list
    def _row_image_list(row):
        urls = []
        for col in image_columns:
            v = row.get(col)
            if pd.isna(v) or v is None:
                continue
            if isinstance(v, str):
                v_str = v.strip()
                if v_str.startswith("[") and v_str.endswith("]"):
                    try:
                        arr = ast.literal_eval(v_str)
                        urls.extend([u for u in arr if isinstance(u, str)])
                    except Exception:
                        urls.append(v_str)
                else:
                    if v_str.startswith("http"):
                        urls.append(v_str)
                    elif "," in v_str:
                        for part in [p.strip() for p in v_str.split(",")]:
                            if part.startswith("http"):
                                urls.append(part)
            elif isinstance(v, (list, tuple, set)):
                for item in v:
                    if isinstance(item, str) and item.startswith("http"):
                        urls.append(item)
        return list(dict.fromkeys(urls))

    df["all_image_urls"] = df.progress_apply(_row_image_list, axis=1)
    df["nsfw_candidates"] = df["all_image_urls"]

    return df
