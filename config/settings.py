import os
TOXICITY_MODEL = "unitary/toxic-bert"
NSFW_MODEL = "openai/clip-vit-base-patch32"
NSFW_THRESHOLD = 0.7
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Sync file path (stored in project root)
SYNC_FILE = os.path.join(BASE_DIR, "last_sync.txt")


