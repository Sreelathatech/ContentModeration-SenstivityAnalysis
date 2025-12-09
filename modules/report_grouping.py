"""
report_grouping.py

Combine service and provider moderation results into a unified final report.

- Merges toxicity, PII, and NSFW detections
- Keeps only flagged NSFW URLs
- Groups all results per unique entity (service/product/preowned/provider)
- Deduplicates repeated moderation content entries
"""

import ast
import pandas as pd

# ===================== NSFW FLAGGING =====================
def _build_nsfw_flags(row):
    """Build NSFW flags only for URLs actually marked as NSFW."""
    nsfw_flags = []
    nsfw_threshold = 0.7

    nsfw_score = row.get("nsfw_score", None)
    nsfw_label = str(row.get("nsfw_label", "")).upper()
    url = row.get("image_url", None)

    # Direct detection
    if url and nsfw_label == "NSFW" and nsfw_score and float(nsfw_score) >= nsfw_threshold:
        nsfw_flags.append({
            "flag": "nsfw",
            "origin": "image",
            "value": url
        })

    # Fallback from list
    elif "nsfw_candidates" in row:
        candidates = row.get("nsfw_candidates")
        if isinstance(candidates, str):
            try:
                candidates = ast.literal_eval(candidates)
            except Exception:
                candidates = [candidates]

        for c in candidates or []:
            if isinstance(c, dict):
                if c.get("label") == "NSFW" and c.get("score", 0) >= nsfw_threshold:
                    nsfw_flags.append({
                        "flag": "nsfw",
                        "origin": "image",
                        "value": c.get("url")
                    })

    return nsfw_flags


# ===================== FLAG BUILDING =====================
def _build_flags_for_row(row):
    """Construct toxicity, PII, and NSFW flags for a single row."""
    content = []

    # Toxicity
    tox_score = float(row.get("toxicity_score", 0.0))
    if tox_score > 0.6:
        tox_matches = row.get("toxicity_matches", [])
        if isinstance(tox_matches, str):
            try:
                tox_matches = ast.literal_eval(tox_matches)
            except Exception:
                tox_matches = []

        for match in tox_matches or []:
            content.append({
                "flag": "toxicity",
                "origin": match.get("origin_col"),
                "value": match.get("value"),
                "toxicity_score": match.get("score")
            })

    # PII
    pii_score = int(row.get("pii_score", 0))
    if pii_score > 0:
        pii_matches = row.get("pii_matches", [])
        if isinstance(pii_matches, str):
            try:
                pii_matches = ast.literal_eval(pii_matches)
            except Exception:
                pii_matches = []

        for match in pii_matches or []:
            content.append({
                "flag": "pii",
                "origin": match.get("origin_col"),
                "value": match.get("value")
            })

    # NSFW
    nsfw_flags = _build_nsfw_flags(row)
    if nsfw_flags:
        content.extend(nsfw_flags)

    return content


# ===================== REPORT UTILITIES =====================
def _reason_of_reporting(content_list):
    if not content_list:
        return ""
    return ", ".join(sorted({c["flag"] for c in content_list if "flag" in c}))


def _admin_check(reasons):
    if not reasons:
        return "No action needed"
    if any(flag in reasons for flag in ["toxicity", "pii", "nsfw"]):
        return "Review required"
    return "No action needed"


# ===================== DEDUPLICATION =====================
def _deduplicate_content(content_list):
    """Remove duplicate moderation content entries."""
    if not isinstance(content_list, list):
        return content_list

    seen = set()
    unique = []

    for item in content_list:
        key = (item.get("flag"), item.get("origin"), str(item.get("value")))
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


# ===================== ENTITY GROUPING =====================
def _group_entity_level(df, entity_col):
    """
    Aggregate moderation signals per entity.

    NOTE:
    - Uses df['type'] directly from data_extraction.py
      (service/product/preowned/provider)
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if "type" not in df.columns:
        raise ValueError("Missing 'type' column — ensure data_extraction.py adds it.")

    temp_records = []
    for _, row in df.iterrows():
        content = _build_flags_for_row(row)

        temp_records.append({
            "entity_id": row.get(entity_col),
            "type": row.get("type"),  # ← Use precomputed type
            "content": content,
            "toxicity_score": float(row.get("toxicity_score", 0.0)),
            "pii_score": int(row.get("pii_score", 0)),
            "nsfw_score": float(row.get("nsfw_score", 0.0)),
        })

    temp_df = pd.DataFrame(temp_records)

    # Aggregate per entity_id + type
    grouped = temp_df.groupby(["entity_id", "type"]).agg({
        "content": lambda x: sum(x, []),
        "toxicity_score": "max",
        "pii_score": "max",
        "nsfw_score": "max",
    }).reset_index()

    grouped["content"] = grouped["content"].apply(_deduplicate_content)
    grouped["reason_of_reporting"] = grouped["content"].apply(_reason_of_reporting)

    grouped["score_summary"] = grouped.apply(
        lambda r: {
            "toxicity": r["toxicity_score"],
            "pii": r["pii_score"],
            "nsfw": r["nsfw_score"],
        },
        axis=1,
    )

    grouped["admin_check"] = grouped["reason_of_reporting"].apply(_admin_check)

    return grouped[
        [
            "entity_id",
            "type",
            "content",
            "reason_of_reporting",
            "score_summary",
            "admin_check"
        ]
    ]


# ===================== FINAL REPORT =====================
def generate_final_report(serviceDf, providerDf):
    """Combine service/product/preowned/provider grouped reports."""
    service_report = _group_entity_level(serviceDf, "service_id")
    provider_report = _group_entity_level(providerDf, "provider_id")

    return pd.concat([service_report, provider_report], ignore_index=True)
