# ====================== TOXICITY DETECTION MODULE ======================
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# -------------------- Load Model (Silent Initialization) --------------------
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

# -------------------- Batch Toxicity Classification --------------------
def classify_toxicity(texts, batch_size=8):
    if not texts:
        return np.zeros((0, len(TOXICITY_LABELS)))

    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        inputs = tox_tokenizer(
            batch,
            padding=True,
            truncation=True,
            return_tensors="pt"
        ).to(device)

        with torch.no_grad():
            outputs = tox_model(**inputs)
            scores = torch.sigmoid(outputs.logits).cpu().numpy()

        results.extend(scores)

    return np.array(results)


# -------------------- Apply Toxicity Detection to a DataFrame --------------------
def run_toxicity_detection(df, text_columns):
    """
    Runs toxicity detection per text column (not combined).
    Creates separate toxicity score columns per text field.
    """
    if df is None or df.empty:
        return df

    for col in text_columns:
        if col not in df.columns:
            continue

        texts = df[col].fillna("").astype(str).tolist()
        scores = classify_toxicity(texts)

        # Add output columns, ex: title_toxicity, title_insult, etc.
        tox_df = pd.DataFrame(scores, columns=[f"{col}_{lbl}" for lbl in TOXICITY_LABELS])
        df = pd.concat([df.reset_index(drop=True), tox_df], axis=1)

    return df


# -------------------- Run Detection on Both Service & Provider --------------------
def run_for_all(serviceDf, providerDf):
    # Services
    if serviceDf is not None and not serviceDf.empty:
        service_text_cols = ["title", "description"]
        if "tags" in serviceDf.columns:
            service_text_cols.append("tags")

        serviceDf = run_toxicity_detection(serviceDf, service_text_cols)

    # Providers
    if providerDf is not None and not providerDf.empty:
        providerDf = run_toxicity_detection(providerDf, ["name", "about"])

    return serviceDf, providerDf
