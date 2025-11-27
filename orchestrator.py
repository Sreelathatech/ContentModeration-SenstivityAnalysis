# ==========================================================
# orchestrator.py — Central Moderation Pipeline
# ==========================================================
import os
from datetime import datetime
from modules.data_extraction import fetch_records
from modules.pii_detection import run_for_all as run_pii
from modules.toxicity_detection import run_for_all as run_toxicity
from modules.nsfw_detection import run_for_all as run_nsfw
from modules.report_generation import generate_reporting_columns
from modules.report_grouping import generate_final_report
from modules.report_db_writer import upsert_final_report


def run_moderation_pipeline(sync_timestamp: datetime):
    """
    Runs the full content moderation pipeline for Services + Providers.

    Steps:
    1. Fetch updated records using sync timestamp
    2. Run PII detection
    3. Run Toxicity detection
    4. Run NSFW detection
    5. Generate reporting columns
    6. Group into final report
    7. Filter only review-required rows
    8. UPSERT into DB
    9. Return summary JSON
    """

    # ---------------------------------------
    # 1. Fetch updated service & provider data
    # ---------------------------------------
    serviceDf, providerDf = fetch_records(sync_timestamp)

    service_count = len(serviceDf)
    provider_count = len(providerDf)
    total_processed = service_count + provider_count

    if total_processed == 0:
        return {
            "sync_timestamp": sync_timestamp.isoformat(),
            "service_records": 0,
            "provider_records": 0,
            "total_records_processed": 0,
            "flagged_entities": 0,
            "db_rows_written": 0
        }

    # ---------------------------------------
    # 2. Run PII detection
    # ---------------------------------------
    serviceDf, providerDf = run_pii(serviceDf, providerDf)

    # ---------------------------------------
    # 3. Run Toxicity detection
    # ---------------------------------------
    serviceDf, providerDf = run_toxicity(serviceDf, providerDf)

    # ---------------------------------------
    # 4. Run NSFW detection
    # ---------------------------------------
    serviceDf, providerDf = run_nsfw(serviceDf, providerDf)

    # ---------------------------------------
    # 5. Generate reporting columns
    # ---------------------------------------
    service_final = generate_reporting_columns(serviceDf)
    provider_final = generate_reporting_columns(providerDf)

    # ---------------------------------------
    # 6. Group into final report
    # ---------------------------------------
    final_report = generate_final_report(service_final, provider_final)

    # ---------------------------------------
    # 7. Filter only entities requiring review
    # ---------------------------------------
    final_report["admin_comment"] = ""
    final_report = final_report.loc[
        final_report["admin_check"] == "Review required"
    ]

    flagged_count = len(final_report)

    if not final_report.empty:
        project_root = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(project_root, "outputs")
        os.makedirs(output_dir, exist_ok=True)

        csv_path = os.path.join(output_dir, "final_moderation_report.csv")
        final_report.to_csv(csv_path, index=False)
    else:
        csv_path = None

    # ---------------------------------------
    # 8. UPSERT into DB
    # ---------------------------------------
    #db_rows_written = upsert_final_report(final_report)

    # ---------------------------------------
    # 9. Return structured summary
    # ---------------------------------------
    return {
        "sync_timestamp": sync_timestamp.isoformat(),
        "service_records": service_count,
        "provider_records": provider_count,
        "total_records_processed": total_processed,
        "flagged_entities": flagged_count
       # "db_rows_written": db_rows_written
    }
