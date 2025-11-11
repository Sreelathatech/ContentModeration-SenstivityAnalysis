# ====================== TOXICITY DETECTION MODULE ======================
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from tqdm import tqdm

device = "cuda" if torch.cuda.is_available() else "cpu"
tox_model_name = "unitary/toxic-bert"
tox_tokenizer = AutoTokenizer.from_pretrained(tox_model_name)
tox_model = AutoModelForSequenceClassification.from_pretrained(tox_model_name).to(device).eval()

TOXICITY_LABELS = [
    "toxicity",
    "severe_toxicity",
    "obscene",
    "identity_attack",
    "insult",
    "threat"
]

def classify_toxicity(texts, batch_size=8):
    results = []
    for i in tqdm(range(0, len(texts), batch_size), desc="🧪 Toxicity batches"):
        batch = texts[i:i + batch_size]
        inputs = tox_tokenizer(batch, padding=True, truncation=True, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = tox_model(**inputs)
            scores = torch.sigmoid(outputs.logits).cpu().numpy()
        results.extend(scores)
    return np.array(results)

def run_toxicity_detection(df, text_columns):
    """
    Runs toxicity detection per text column (not combined).
    Creates separate toxicity columns for each text field.
    """
    print(f"Running toxicity detection on columns: {text_columns}")

    for col in text_columns:
        if col not in df.columns:
            print(f"Skipping missing column: {col}")
            continue

        print(f"⚙️ Processing column: {col}")
        texts = df[col].fillna("").astype(str).tolist()
        scores = classify_toxicity(texts)

        # Create prefixed columns
        tox_df = pd.DataFrame(scores, columns=[f"{col}_{lbl}" for lbl in TOXICITY_LABELS])
        df = pd.concat([df.reset_index(drop=True), tox_df], axis=1)

    return df


def run_for_all(serviceDf, providerDf):
    """
    Run per-column toxicity detection for service and provider datasets.
    Handles missing 'tags' column gracefully.
    """
    service_text_cols = ["title", "description"]
    if "tags" in serviceDf.columns:
        service_text_cols.append("tags")

    print("⚙️ Running Toxicity Detection for Services...")
    serviceDf = run_toxicity_detection(serviceDf, service_text_cols)

    print("⚙️ Running Toxicity Detection for Providers...")
    providerDf = run_toxicity_detection(providerDf, ["name", "about"])

    return serviceDf, providerDf
