import pandas as pd
from datetime import datetime
import mysql.connector
from utils.vault_utils import get_vault_client, get_db_config


def fetch_records(sync_timestamp: datetime):
    """
    Fetch service and provider records updated after the given timestamp.
    
    - sync_timestamp (UTC) comes directly from the FastAPI request.
    - Uses only dev_she_careers tables.
    - No SYNC_FILE logic.
    - No limits.
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
               tags, image_url, updated_on, created_on
        FROM prod_she_careers.services
        WHERE updated_on > '{ts_str}' 
           OR created_on > '{ts_str}' ;
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

    return serviceDf, providerDf
