import pandas as pd
from datetime import datetime, timedelta
import mysql.connector
from utils.vault_utils import get_vault_client, get_db_config


def fetch_records_page(sync_timestamp: datetime, page: int, batch_size: int):
    """
    Paginated fetch:
    Pulls ONLY a specific page of services & providers using LIMIT + OFFSET.

    Returns:
        serviceDf, providerDf, new_sync_timestamp
    """

    offset = page * batch_size
    ts_str = sync_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Vault client
    client = get_vault_client()
    db_config = get_db_config(client)
    conn = mysql.connector.connect(**db_config)

    # -------------------------
    # SERVICES PAGE
    # -------------------------
    service_query = f"""
        SELECT *
        FROM prod_she_careers.services
        WHERE (updated_on >= '{ts_str}' - INTERVAL 6 HOUR
           OR created_on >= '{ts_str}' - INTERVAL 6 HOUR)
           and status in ('ACTIVE','DRAFT')
        ORDER BY updated_on ASC
        LIMIT {batch_size} OFFSET {offset};
    """

    # -------------------------
    # PROVIDERS PAGE
    # -------------------------
    provider_query = f"""
        SELECT *
        FROM prod_she_careers.provider
        WHERE (updated_on >= '{ts_str}' - INTERVAL 6 HOUR
           OR created_on >= '{ts_str}' - INTERVAL 6 HOUR)
        AND   status in ('ACTIVE','DRAFT')
        ORDER BY updated_on ASC
        LIMIT {batch_size} OFFSET {offset};
    """

    serviceDf = pd.read_sql_query(service_query, conn)
    providerDf = pd.read_sql_query(provider_query, conn)

    conn.close()

    # ------------------------- Type Column Logic -------------------------
    if "is_multi_city" in serviceDf.columns and "is_pre_owned_item" in serviceDf.columns:

        def resolve_type(row):
            mc = int(row["is_multi_city"]) if pd.notnull(row["is_multi_city"]) else 0
            po = int(row["is_pre_owned_item"]) if pd.notnull(row["is_pre_owned_item"]) else 0

            if mc == 0 and po == 0:
                return "service"
            if mc == 1 and po == 0:
                return "product"
            if mc == 1 and po == 1:
                return "preowned"

            return "service"

        serviceDf["type"] = serviceDf.apply(resolve_type, axis=1)

    providerDf["type"] = "provider"

    # -------------------------
    # Return new sync timestamp (UTC - 1 hr)
    # -------------------------
    new_sync_timestamp = datetime.utcnow() - timedelta(hours=1)

    return serviceDf, providerDf, new_sync_timestamp
