import os
import mysql.connector
from config.env_setup import load_environment


def get_db_connection():
    """Establish a secure DB connection using environment variables."""
    load_environment()
    config = {
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "database": os.getenv("DB_NAME"),
        "charset": "utf8mb4",
        "collation": "utf8mb4_general_ci",
    }
    print(config)
    return mysql.connector.connect(**config)
