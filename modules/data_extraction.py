import pandas as pd
from datetime import datetime, timedelta
import mysql.connector
from utils.vault_utils import get_vault_client, get_db_config


def fetch_records(sync_timestamp: datetime):

    ts_str = sync_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    client = get_vault_client()
    db_config = get_db_config(client)
    conn = mysql.connector.connect(**db_config)

    # ---------------- SQL ----------------
    service_query = f"""
        SELECT *
    FROM prod_she_careers.services
    WHERE updated_on >= DATE_SUB('{ts_str}', INTERVAL 6 HOUR)
       OR created_on >= DATE_SUB('{ts_str}', INTERVAL 6 HOUR) limit 10;
    """

    provider_query = f"""
        SELECT *
    FROM prod_she_careers.provider
    WHERE updated_on >= DATE_SUB('{ts_str}', INTERVAL 6 HOUR)
       OR created_on >= DATE_SUB('{ts_str}', INTERVAL 6 HOUR) limit 10;
    """
    serviceDf = pd.read_sql_query(service_query, conn)
    providerDf = pd.read_sql_query(provider_query, conn)
    conn.close()

    # ---------------- SAFE ID CONVERSION ----------------
    def safe_to_str(x):
        if isinstance(x, (bytearray, bytes)):
            try: return x.decode("utf-8")
            except: return x.hex()
        return str(x)

    if "service_id" in serviceDf:
        serviceDf["service_id"] = serviceDf["service_id"].apply(safe_to_str)

    if "provider_id" in serviceDf:
        serviceDf["provider_id"] = serviceDf["provider_id"].apply(safe_to_str)

    if "provider_id" in providerDf:
        providerDf["provider_id"] = providerDf["provider_id"].apply(safe_to_str)

    # ============================================================
    #       NORMALIZE TINYINT → BOOLEAN (1 = True, else False)
    # ============================================================

    def normalize_bool_tinyint(val):
        return True if val == 1 else False

    if "is_multi_city" in serviceDf.columns:
        serviceDf["is_multi_city"] = serviceDf["is_multi_city"].apply(normalize_bool_tinyint)

    if "is_pre_owned_item" in serviceDf.columns:
        serviceDf["is_pre_owned_item"] = serviceDf["is_pre_owned_item"].apply(normalize_bool_tinyint)

    # ============================================================
    #                TYPE COLUMN LOGIC (final correct)
    # ============================================================

    def resolve_service_type(row):
        mc = row["is_multi_city"]
        po = row["is_pre_owned_item"]

        if not mc and not po:
            return "service"
        if mc and not po:
            return "product"
        if mc and po:
            return "preowned"

        return "service"  # fallback (should never reach)

    serviceDf["type"] = serviceDf.apply(resolve_service_type, axis=1)

    # Provider type = "provider"
    providerDf["type"] = "provider"

    # ============================================================
    #    NEW SYNC TIMESTAMP = current UTC time - 1 hour
    # ============================================================
    new_sync_timestamp = datetime.utcnow() - timedelta(hours=1)

    return serviceDf, providerDf, new_sync_timestamp
