import pandas as pd
from datetime import datetime, timedelta
import mysql.connector
from utils.vault_utils import get_vault_client, get_db_config


def fetch_records(sync_timestamp: datetime):
    """
    Fetch service and provider records updated after the given timestamp.

    Returns a new sync timestamp = current UTC time - 1 hour.
    """

    # Ensure proper datetime formatting for SQL
    ts_str = sync_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Get Vault client
    client = get_vault_client()

    # Step 2: Fetch DB config from Vault
    db_config = get_db_config(client)

    # Step 3: Connect to MySQL
    conn = mysql.connector.connect(**db_config)

    # --- SQL Queries (dev only) ---
    service_query = f"""
        SELECT service_id, provider_id, title, description, other_image_urls,
               tags, image_url, updated_on, created_on,
               is_multi_city, is_pre_owned_item
        FROM prod_she_careers.services
        WHERE updated_on > '{ts_str}' 
           OR created_on > '{ts_str}';
    """

    provider_query = f"""
        SELECT provider_id, name, bio_image, profile_picture_url, about,
               provider_store_images, about_image,
               created_on, updated_on
        FROM prod_she_careers.provider
        WHERE updated_on > '{ts_str}'
           OR created_on > '{ts_str}' ;
    """

    # Execute queries
    serviceDf = pd.read_sql_query(service_query, conn)
    providerDf = pd.read_sql_query(provider_query, conn)

    conn.close()

    # ---- Utility: Convert bytes safely to string ----
    def safe_to_str(x):
        if isinstance(x, (bytearray, bytes)):
            try:
                return x.decode("utf-8")
            except UnicodeDecodeError:
                return x.hex()
        return str(x)

    # ---- Convert identifiers safely ----
    if "service_id" in serviceDf.columns:
        serviceDf["service_id"] = serviceDf["service_id"].apply(safe_to_str)

    if "provider_id" in serviceDf.columns:
        serviceDf["provider_id"] = serviceDf["provider_id"].apply(safe_to_str)

    if "provider_id" in providerDf.columns:
        providerDf["provider_id"] = providerDf["provider_id"].apply(safe_to_str)

    # ============================================================
    #               ADD TYPE COLUMN TO servicedf
    # ============================================================

    if {"is_multi_city", "is_pre_owned_item"}.issubset(serviceDf.columns):

        def resolve_service_type(row):
            mc = str(row["is_multi_city"]).lower()
            po = str(row["is_pre_owned_item"]).lower()

            if mc == "false" and po == "false":
                return "service"
            if mc == "true" and po == "false":
                return "product"
            if mc == "true" and po == "true":
                return "preowned"

            return "service"  # default

        serviceDf["type"] = serviceDf.apply(resolve_service_type, axis=1)

    # ============================================================
    #               ADD TYPE COLUMN TO providerDf
    # ============================================================

    providerDf["type"] = "provider"

    # ============================================================
    #     UPDATE sync_timestamp TO (current_time - 1 hour)
    # ============================================================

    new_sync_timestamp = datetime.utcnow() - timedelta(hours=1)

    return serviceDf, providerDf, new_sync_timestamp
