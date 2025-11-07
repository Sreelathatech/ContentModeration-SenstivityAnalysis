"""
report_grouping.py

Combine service and provider moderation results into a unified final report.

- Merges toxicity, PII, and NSFW detections
- Keeps only flagged (true positive) NSFW URLs
- Groups all results per unique entity (service/provider)
- ✅ Deduplicates repeated content entries (flag, origin, value)
"""

import ast
import pandas as pd


# ===================== NSFW FLAGGING =====================
def _build_nsfw_flags(row):
    """
    Build NSFW flags only for URLs actually flagged as NSFW (score > threshold).
    Skip safe or missing URLs.
    """
    nsfw_flags = []
    nsfw_threshold = 0.7

    # NSFW score or list of scores
    nsfw_score = row.get("nsfw_score", None)
    nsfw_label = str(row.get("nsfw_label", "")).upper()
    url = row.get("image_url", None)

    # Case 1: Row has per-image detection
    if url and nsfw_label == "NSFW" and nsfw_score and float(nsfw_score) >= nsfw_threshold:
        nsfw_flags.append({
            "flag": "nsfw",
            "origin": "image",
            "value": url
        })

    # Case 2: Multi-image fields (fallback)
    elif "nsfw_candidates" in row:
        candidates = row.get("nsfw_candidates")
        if isinstance(candidates, str):
            try:
                candidates = ast.literal_eval(candidates)
            except Exception:
                candidates = [candidates]
        for c in candidates:
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
    """Construct all flags (toxicity, pii, nsfw) for a single row."""
    content = []

    # ---- Toxicity ----
    tox_score = float(row.get("toxicity_score", 0.0))
    if tox_score > 0.6:
        tox_matches = row.get("toxicity_matches")
        if isinstance(tox_matches, str):
            try:
                tox_matches = ast.literal_eval(tox_matches)
            except Exception:
                tox_matches = []
        if isinstance(tox_matches, list):
            for match in tox_matches:
                content.append({
                    "flag": "toxicity",
                    "origin": match.get("origin_col"),
                    "value": match.get("value"),
                    "toxicity_score": match.get("score")
                })

    # ---- PII ----
    pii_score = int(row.get("pii_score", 0))
    if pii_score > 0:
        pii_matches = row.get("pii_matches")
        if isinstance(pii_matches, str):
            try:
                pii_matches = ast.literal_eval(pii_matches)
            except Exception:
                pii_matches = []
        if isinstance(pii_matches, list):
            for match in pii_matches:
                content.append({
                    "flag": "pii",
                    "origin": match.get("origin_col"),
                    "value": match.get("value")
                })

    # ---- NSFW ----
    nsfw_flags = _build_nsfw_flags(row)
    if nsfw_flags:
        content.extend(nsfw_flags)

    return content


# ===================== REPORT UTILITIES =====================
def _reason_of_reporting(content_list):
    """Generate concise reason summary from content flags."""
    if not content_list:
        return ""
    reasons = sorted(set([c["flag"] for c in content_list if "flag" in c]))
    return ", ".join(reasons)


def _admin_check(reasons):
    """Return admin recommendation based on reasons."""
    if not reasons:
        return "No action needed"
    if any(flag in reasons for flag in ["toxicity", "pii", "nsfw"]):
        return "Review required"
    return "No action needed"


# ===================== DEDUPLICATION UTILITY =====================
def _deduplicate_content(content_list):
    """
    Remove duplicate moderation content entries for the same entity.
    Duplicates are defined by identical (flag, origin, value) triplets.
    """
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
def _group_entity_level(df, entity_col, entity_type):
    """Aggregate all moderation signals per entity (service/provider)."""
    if df.empty:
        return pd.DataFrame()

    temp_records = []
    for _, row in df.iterrows():
        content = _build_flags_for_row(row)
        temp_records.append({
            "entity_id": row.get(entity_col),
            "type": entity_type,
            "content": content,
            "toxicity_score": float(row.get("toxicity_score", 0.0)),
            "pii_score": int(row.get("pii_score", 0)),
            "nsfw_score": float(row.get("nsfw_score", 0.0))
        })

    temp_df = pd.DataFrame(temp_records)

    # Group by entity and merge content lists
    grouped = temp_df.groupby(["entity_id", "type"]).agg({
        "content": lambda x: sum(x, []),
        "toxicity_score": "max",
        "pii_score": "max",
        "nsfw_score": "max"
    }).reset_index()

    # ✅ Deduplicate content at entity level
    grouped["content"] = grouped["content"].apply(_deduplicate_content)

    # Derive report summaries
    grouped["reason_of_reporting"] = grouped["content"].apply(_reason_of_reporting)
    grouped["score_summary"] = grouped.apply(
        lambda r: {
            "toxicity": r["toxicity_score"],
            "pii": r["pii_score"],
            "nsfw": r["nsfw_score"]
        },
        axis=1
    )
    grouped["admin_check"] = grouped["reason_of_reporting"].apply(_admin_check)

    return grouped[
        ["entity_id", "type", "content", "reason_of_reporting", "score_summary", "admin_check"]
    ]
def generate_final_report(serviceDf, providerDf):
    """Combine service and provider grouped reports."""
    service_report = _group_entity_level(serviceDf, "service_id", "service")
    provider_report = _group_entity_level(providerDf, "provider_id", "provider")

    final_report = pd.concat([service_report, provider_report], ignore_index=True)
    return final_report
