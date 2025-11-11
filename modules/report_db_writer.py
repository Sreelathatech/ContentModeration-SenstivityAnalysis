import mysql.connector
import json
from utils.vault_utils import get_vault_client, get_db_config

def upsert_final_report(final_report, table_name="content_moderation_report"):
    """
    Inserts or updates entity-level moderation report in MySQL.
    Uses entity_id as the unique key (covers both service and provider).
    """

    # --- Load connection config from Vault ---
    '''load_env(".env.dev")'''
    client = get_vault_client()
    db_config = get_db_config(client)

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    # --- Ensure table exists ---
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        entity_id VARCHAR(255) PRIMARY KEY,
        type VARCHAR(50),
        content TEXT,
        reason_of_reporting TEXT,
        score_summary TEXT,
        admin_check VARCHAR(100),
        admin_comment TEXT
    );
    """
    cursor.execute(create_table_sql)

    # --- Prepare UPSERT SQL ---
    insert_sql = f"""
    INSERT INTO {table_name}
    (entity_id, type, content, reason_of_reporting, score_summary, admin_check, admin_comment)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        type = VALUES(type),
        content = VALUES(content),
        reason_of_reporting = VALUES(reason_of_reporting),
        score_summary = VALUES(score_summary),
        admin_check = VALUES(admin_check),
        admin_comment = VALUES(admin_comment);
    """

    # --- Convert DataFrame rows to tuples ---
    rows = []
    for _, row in final_report.iterrows():
        rows.append((
            str(row.get("entity_id")),
            str(row.get("type")),
            json.dumps(row.get("content", []), ensure_ascii=False),
            str(row.get("reason_of_reporting", "")),
            json.dumps(row.get("score_summary", {}), ensure_ascii=False),
            str(row.get("admin_check", "")),
            str(row.get("admin_comment", "")) if "admin_comment" in row else "",
        ))

    # --- Execute batch upsert ---
    cursor.executemany(insert_sql, rows)
    conn.commit()
    print(f"✅ Upserted {cursor.rowcount} entity reports into {table_name}.")

    cursor.close()
    conn.close()
