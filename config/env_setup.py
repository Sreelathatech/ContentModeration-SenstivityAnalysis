import os
from dotenv import load_dotenv

def load_environment():
    """Load environment variables from .env file."""
    load_dotenv()
    env = os.getenv("ENVIRONMENT", "dev")    # change here for prod
    print(f"✅ Environment loaded: {env}")
    return env
