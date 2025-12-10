# ====================== FIXED & STABLE REPORT GENERATION ======================
import re
import ast
import pandas as pd
from tqdm import tqdm

tqdm.pandas()

TOXICITY_THRESHOLD = 0.6
NSFW_THRESHOLD = 0.7

_EMAIL_RE = re.compile(r"[a-zA-Z0-9.\-_+]+@[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-.]+")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{10}|\d{3}[-.\s]\d{3}[-.\s]\d{4})\b")
_EMP_ID_RE = re.compile(r"\b(?:EMP|Emp|emp)[-_]?\d{3,6}\b")

_PII_REGEXES = {
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
    "emp_id": _EMP_ID_RE,
}


def _safe_float(v):
    try:
        if pd.isna(v):
            return 0.0
        return float(v)
    except:
        return 0.0


# ============================================================================
# MAIN ENTRY: generate_reporting_columns
# ============================================================================
def generate_reporting_columns(df: pd.DataFrame, text_columns=None, image_columns=None):

    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # Auto-detect text columns
    if text_columns is None:
        candidates = ["title", "description", "tags", "name", "about"]
        text_columns = [c for c in candidates if c in df.columns]

    # ----------------------------------------------------------------------
    # TOXICITY
    # ----------------------------------------------------------------------
    tox_cols = [c for c in df.columns if "toxicity" in c.lower()]
    if tox_cols:
        df[tox_cols] = df[tox_cols].applymap(_safe_float)
        df["toxicity_score"] = df[tox_cols].max(axis=1)
    else:
        df["toxicity_score"] = 0.0

    # mapping → original column → toxicity score column
    mapping = {}
    for tcol in text_columns:
        candidates = [c for c in tox_cols if c.startswith(tcol + "_")]
        mapping[tcol] = candidates[0] if candidates else None

    def _tox_matches(row):
        matches = []
        for tcol, toxcol in mapping.items():
            if toxcol:
                score = _safe_float(row.get(toxcol))
                if score > TOXICITY_THRESHOLD:
                    matches.append({
                        "origin_col": tcol,
                        "value": row.get(tcol),
                        "score": score
                    })
        return matches

    df["toxicity_matches"] = df.progress_apply(_tox_matches, axis=1)

    # ----------------------------------------------------------------------
    # PII (Regex + Presidio Merged)
    # ----------------------------------------------------------------------
    def _pii_regex_matches(row):
        matches = []
        for col in text_columns:
            text = row.get(col, "")
            if not isinstance(text, str):
                continue

            for name, regex in _PII_REGEXES.items():
                found = regex.findall(text)
                for v in found:
                    matches.append({"origin_col": col, "value": v})
        return matches

    df["pii_regex_matches"] = df.progress_apply(_pii_regex_matches, axis=1)

    # MERGE FUNCTION THAT RETURNS ONLY LISTS
    def _merge_pii(row):
        merged = []

        # regex PII
        rx = row.get("pii_regex_matches", [])
        if isinstance(rx, list):
            merged.extend(rx)

        # presidio detailed (optional)
        detailed = row.get("pii_detailed", [])
        if isinstance(detailed, str):
            try:
                detailed = ast.literal_eval(detailed)
            except:
                detailed = []

        if isinstance(detailed, list):
            for block in detailed:
                origin = block.get("origin_col")
                ents = block.get("entities", [])
                if not isinstance(ents, list):
                    ents = [ents]

                for ent in ents:
                    merged.append({"origin_col": origin, "value": ent})

        # ALWAYS return a Python list
        if not isinstance(merged, list):
            return []
        return merged

    # --- CRITICAL FIX: Convert the entire column to a plain Python list BEFORE assignment ---
    pii_list = df.progress_apply(_merge_pii, axis=1).tolist()
    pii_list = [x if isinstance(x, list) else [] for x in pii_list]

    df["pii_matches"] = pii_list
    df["pii_score"] = df["pii_matches"].apply(lambda x: 1 if x else 0)

    # ----------------------------------------------------------------------
    # NSFW
    # ----------------------------------------------------------------------
    nsfw_cols = [c for c in df.columns if "nsfw" in c.lower()]
    if nsfw_cols:
        df[nsfw_cols] = df[nsfw_cols].applymap(_safe_float)
        df["nsfw_score"] = df[nsfw_cols].max(axis=1)
    else:
        df["nsfw_score"] = 0.0

    return df

