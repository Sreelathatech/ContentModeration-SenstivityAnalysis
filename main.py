# ==========================================================
# main.py — Content Moderation Pipeline Orchestrator
# ==========================================================
import os
import pandas as pd

from modules.data_extraction import fetch_records
from modules.pii_detection import run_for_all as run_pii
from modules.toxicity_detection import run_for_all as run_toxicity
from modules.nsfw_detection import run_for_all as run_nsfw
from modules.report_generation import generate_reporting_columns
from modules.report_grouping import generate_final_report
from modules.report_db_writer import upsert_final_report
from utils.vault_utils import get_vault_client


def main(env_file: str = ".env.dev"):
    """
    Orchestrator for the full content moderation pipeline.
    Includes PII, Toxicity, and NSFW detection, followed by report generation.
    """
    print("🚀 Starting Content Moderation Pipeline")

    # 1️⃣ Load environment variables
    '''load_env(env_file)
    print(f"✅ Environment loaded from {env_file}")'''

    # 2️⃣ Fetch data 
    print("📥 Fetching service and provider data...")
    # Replace testingData() with fetch_records() when using DB connection
    serviceDf, providerDf = fetch_records()
    print(f"✅ Fetched {len(serviceDf)} service rows, {len(providerDf)} provider rows")
    if serviceDf.empty and providerDf.empty:
        print("⚠️ No data fetched from database. Both service and provider tables are empty.")
        print("🛑 Exiting pipeline gracefully.")
        return

    if serviceDf.empty:
        print("⚠️ No Service data found — skipping service checks.")
    if providerDf.empty:
        print("⚠️ No Provider data found — skipping provider checks.")

    # 3️⃣ Run PII detection
    print("🔐 Running PII detection...")
    serviceDf, providerDf = run_pii(serviceDf, providerDf)
    print("✅ PII detection complete.")

    # 4️⃣ Run Toxicity detection
    print("💬 Running Toxicity detection...")
    serviceDf, providerDf = run_toxicity(serviceDf, providerDf)
    print("✅ Toxicity detection complete.")

    # 5️⃣ Run NSFW detection
    print("🔞 Running NSFW detection...")
    serviceDf, providerDf = run_nsfw(serviceDf, providerDf)
    print("✅ NSFW detection complete.")

    # 6️⃣ Generate reporting columns
    print("🧩 Generating reporting columns for service & provider...")
    serviceDf_final = generate_reporting_columns(serviceDf)
    providerDf_final = generate_reporting_columns(providerDf)
    print("✅ Reporting columns generated.")

    # 7️⃣ Group the results
    print("📊 Grouping reports...")
    final_report = generate_final_report(serviceDf_final, providerDf_final)
    print("✅ Grouping completed.")

    ''''# 8️⃣ Combine and save reports
    print("🧾 Combining service and provider reports...")
    combined_report = combine_reports(service_report, provider_report)
    print("✅ Combined report generated.")'''

    project_root = os.path.dirname(os.path.abspath(__file__))
    output_folder = os.path.join(project_root, "outputs")
    os.makedirs(output_folder, exist_ok=True)

    combined_path = os.path.join(output_folder, "combined_moderation_report.xlsx")

# Save final report as Excel
    #final_report.to_excel(combined_path, index=False, engine="openpyxl")

    #print(f"📁 Combined moderation report saved to: {combined_path}")
    final_report["admin_comment"] = ""
    final_report=final_report.loc[final_report['admin_check'] == "review_required"]
    final_report.to_excel(combined_path, index=False, engine="openpyxl")

#    upsert_final_report(final_report)

    print("🎉 Pipeline completed successfully.")
    return final_report


if __name__ == "__main__":
    try:
        main(".env.dev")    # change the environemnt here
    except Exception as e:
        print("❌ Pipeline failed with error:", e)
