# ==========================================================
# orchestrator.py — Paginated Moderation Pipeline (Write ONLY review_final)
# ==========================================================
import os
import pandas as pd
from datetime import datetime
from modules.data_extraction import fetch_records_page
from modules.pii_detection import run_for_all as run_pii
from modules.toxicity_detection import run_for_all as run_toxicity
from modules.nsfw_detection import run_for_all as run_nsfw
from modules.report_generation import generate_reporting_columns
from modules.report_grouping import generate_final_report
from modules.report_db_writer import upsert_final_report  # disabled for now

BATCH_SIZE = 50  # configurable


def run_moderation_pipeline(sync_timestamp: datetime):

    # Prepare output folder
    project_root = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    service_frames = []
    provider_frames = []

    total_service = 0
    total_provider = 0
    page = 0

    while True:

        serviceDf, providerDf, new_sync_timestamp = fetch_records_page(
            sync_timestamp, page, BATCH_SIZE
        )

        if serviceDf.empty and providerDf.empty:
            break

        print(f"Processing page {page}: "
              f"{len(serviceDf)} services, {len(providerDf)} providers")

        total_service += len(serviceDf)
        total_provider += len(providerDf)

        # 1. PII
        serviceDf, providerDf = run_pii(serviceDf, providerDf)

        # 2. Toxicity
        print("Started toxicity detection")
        serviceDf, providerDf = run_toxicity(serviceDf, providerDf)

        # 3. NSFW
        print("Started nfsw detection")
        serviceDf, providerDf = run_nsfw(serviceDf, providerDf)
        print("Finished nfsw detection")

        # 4. Reporting Columns
        service_final = generate_reporting_columns(serviceDf)
        provider_final = generate_reporting_columns(providerDf)

        # Store all batches in memory
        if not service_final.empty:
            service_frames.append(service_final)
        if not provider_final.empty:
            provider_frames.append(provider_final)

        page += 1

    # ------------------------- MERGE RESULTS -------------------------
    service_full = pd.concat(service_frames, ignore_index=True) if service_frames else pd.DataFrame()
    provider_full = pd.concat(provider_frames, ignore_index=True) if provider_frames else pd.DataFrame()

    # ------------------------- FINAL REPORT -------------------------
    final_report = generate_final_report(service_full, provider_full)

    # ------------------------- FILTER REVIEW REQUIRED -------------------------
    review_df = final_report.loc[final_report["admin_check"] == "Review required"].copy()
    review_df["admin_comment"] = ""

    # ------------------------- SAVE REVIEW REPORT ONLY -------------------------
    review_path = os.path.join(output_dir, "review_final.csv")
    review_df.to_csv(review_path, index=False)
    print(f"Saved final review-only report: {review_path}")

    # ------------------------- (OPTIONAL) DB UPSERT -------------------------
    db_rows = 0
    try:
        db_rows = upsert_final_report(review_df)
        print(f"DB Inserted Rows: {db_rows}")
    except Exception as e:
        print("DB upsert failed:", e)
        db_rows = 0
    

    # ------------------------- RETURN SUMMARY -------------------------
    return {
        "sync_timestamp": new_sync_timestamp.isoformat(),
        "service_records": total_service,
        "provider_records": total_provider,
        "total_records_processed": total_service + total_provider,
        "batches": page,
        "flagged_entities": len(review_df),
        "db_rows_written": db_rows,
    }
