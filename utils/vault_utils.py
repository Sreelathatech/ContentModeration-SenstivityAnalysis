# utils/vault_utils.py
import os
import hvac
from dotenv import load_dotenv

''''def load_env(env_file="dev.py"):
    """Load environment variables from a given .env file."""
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"✅ Loaded environment from {env_file}")
    else:
        raise FileNotFoundError(f"{env_file} not found. Please create it with Vault credentials.")'''


def get_vault_client(): 
    """Authenticate with Vault using AppRole."""
    vault_addr = os.getenv("VAULT_ADDR")
    role_id = os.getenv("VAULT_ROLE_ID")
    secret_id = os.getenv("VAULT_SECRET_ID")

    if not vault_addr or not role_id or not secret_id:
        raise RuntimeError("Missing Vault credentials in environment variables.")

    client = hvac.Client(url=vault_addr)
    auth = client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    client.token = auth["auth"]["client_token"]

    if not client.is_authenticated():
        raise RuntimeError("Vault authentication failed.")
    
    print("🔐 Authenticated to Vault.")
    return client


def get_db_config(client):
    """Fetch DB credentials for dev_she_careers from Vault."""
    vault_kv_path = os.getenv("VAULT_KV_PATH", "database/prod/prod_she_careers")
    mount_point = os.getenv("KV_MOUNT_POINT", "secret")

    secret = client.secrets.kv.v2.read_secret_version(
        path=vault_kv_path,
        mount_point=mount_point
    )
    data = secret["data"]["data"]

    db_config = {
        "user": data.get("username") or data.get("user"),
        "password": data.get("password"),
        "host": data.get("host"),
        "database": data.get("database"),
        "port": int(data.get("port", 3306)),
        "charset": "utf8mb4",
        "collation": "utf8mb4_general_ci",
    }

    print(f"✅ Fetched DB config from Vault (keys): {list(data.keys())}")
    return db_config
