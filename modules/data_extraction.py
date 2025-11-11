import pandas as pd
from datetime import datetime
import os
from config.db_config import get_db_connection
from config.settings import SYNC_FILE
import mysql.connector
from utils.vault_utils import get_vault_client, get_db_config

def get_last_sync():
    """Reads last sync timestamp or defaults to year 2000."""
    if os.path.exists(SYNC_FILE):
        with open(SYNC_FILE, "r") as f:
            ts = f.read().strip()
            if ts:
                return datetime.fromisoformat(ts)
    return datetime(2000, 1, 1)



def fetch_records():
    '''# Step 1: Load .env.dev
    load_env(".env.dev")'''

    # Step 2: Get Vault client
    client = get_vault_client()

    # Step 3: Fetch DB config
    db_config = get_db_config(client)

    # Step 4: Connect to DB
    conn = mysql.connector.connect(**db_config)
    print("Connected to MySQL database (dev).")

    # Step 5: Fetch data
    service_queryProd = f"""
        SELECT *
        FROM prod_she_careers.services
        WHERE updated_on > '{get_last_sync}' OR created_on > '{get_last_sync}' limit 200;"""

    provider_queryProd = f"""
        SELECT *
        FROM prod_she_careers.provider
        WHERE updated_on > '{get_last_sync}' OR created_on > '{get_last_sync}' limit 200;
    """

    serviceDf = pd.read_sql_query(service_queryProd, conn)   #change query based on dev and prod
    providerDf = pd.read_sql_query(provider_queryProd, conn)
    conn.close()

    # ---- Utility: Convert bytes safely to string ----
    def safe_to_str(x):
        """Convert bytearray or bytes to string safely."""
        if isinstance(x, (bytearray, bytes)):
            try:
                return x.decode("utf-8")  # if stored as utf8 text
            except UnicodeDecodeError:
                return x.hex()  # fallback: represent as hex string
        return str(x)

    # ---- Convert IDs ----
    if "service_id" in serviceDf.columns:
        serviceDf["service_id"] = serviceDf["service_id"].apply(safe_to_str)

    if "provider_id" in serviceDf.columns:
        serviceDf["provider_id"] = serviceDf["provider_id"].apply(safe_to_str)

    if "provider_id" in providerDf.columns:
        providerDf["provider_id"] = providerDf["provider_id"].apply(safe_to_str)

    # ---- Verify (optional logging) ----
    print(f"Fetched {len(serviceDf)} rows from services.")
    print(f"Fetched {len(providerDf)} rows from providers.")


    return serviceDf, providerDf

def update_last_sync():
    """Updates the last sync time to now."""
    with open(SYNC_FILE, "w") as f:
        f.write(datetime.now().isoformat())