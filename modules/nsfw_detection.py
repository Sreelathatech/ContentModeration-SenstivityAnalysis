# ====================== NSFW DETECTION MODULE ======================
import ast
import json
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel

# ---------------------- MODEL SETUP (Silent) ----------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device).eval()
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")


# ---------------------- URL EXTRACTION ----------------------
def extract_urls(value):
    """Extract valid image URLs from various formats."""
    if value is None:
        return []

    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.startswith("http")]

    if isinstance(value, str):
        val = value.strip()

        # Case 1: Double-quoted JSON string e.g. '"["url1", "url2"]"'
        if val.startswith('"[') and val.endswith(']"'):
            try:
                val = json.loads(val)
            except Exception:
                pass

        # Case 2: Stringified list
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                parsed = ast.literal_eval(val)
                if isinstance(parsed, list):
                    return [v for v in parsed if isinstance(v, str) and v.startswith("http")]
            except Exception:
                pass

        # Case 3: Single direct URL
        if val.startswith("http"):
            return [val]

    return []


# ---------------------- IMAGE PREPARATION ----------------------
def prepare_image_dataframe(df, id_column, image_columns):
    """
    Flatten image columns into a single DataFrame:
    Each row contains an ID and one image URL.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[id_column, "image_url"])

    image_rows = []
    for _, row in df.iterrows():
        sid = row.get(id_column)
        for col in image_columns:
            urls = extract_urls(row.get(col))
            for url in urls:
                image_rows.append({id_column: sid, "image_url": url})

    if not image_rows:
        return pd.DataFrame(columns=[id_column, "image_url"])

    return pd.DataFrame(image_rows)


# ---------------------- CLASSIFICATION ----------------------
def classify_images(image_df, batch_size=8):
    """
    Run CLIP-based NSFW classification.
    Returns a DataFrame with nsfw_score, nsfw_label, and errors.
    """
    if image_df is None or image_df.empty:
        return pd.DataFrame(columns=["provider_id", "image_url", "nsfw_score", "nsfw_label", "error"])

    texts = ["a pornographic image", "a naked person", "a violent image", "safe content"]
    text_inputs = clip_processor(text=texts, return_tensors="pt", padding=True).to(device)
    text_features = clip_model.get_text_features(**text_inputs)
    text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    nsfw_results = []

    # Process in batches without tqdm
    total_rows = len(image_df)
    for i in range(0, total_rows, batch_size):
        batch = image_df.iloc[i:i + batch_size]
        valid_images, ids, urls = [], [], []

        # Step 1: Download images
        for _, row in batch.iterrows():
            sid = row.get("provider_id") or row.get("service_id")
            url = row.get("image_url")
            try:
                if not isinstance(url, str):
                    raise Exception("Invalid URL")
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                img = Image.open(BytesIO(response.content)).convert("RGB")
                valid_images.append(img)
                ids.append(sid)
                urls.append(url)
            except Exception as e:
                nsfw_results.append({
                    "provider_id": sid,
                    "image_url": url,
                    "nsfw_score": None,
                    "nsfw_label": "URL_NOT_FOUND",
                    "error": str(e),
                })

        if not valid_images:
            continue

        # Step 2: Run CLIP inference
        image_inputs = clip_processor(images=valid_images, return_tensors="pt", padding=True).to(device)
        with torch.no_grad():
            image_features = clip_model.get_image_features(**image_inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            sims = image_features @ text_features.T
        sims = sims.softmax(dim=-1).cpu().numpy()

        # Step 3: Store results
        for sid, url, sim in zip(ids, urls, sims):
            nsfw_score = float(sim[0] + sim[1])
            nsfw_results.append({
                "provider_id": sid,
                "image_url": url,
                "nsfw_score": nsfw_score,
                "nsfw_label": "NSFW" if nsfw_score > 0.7 else "SAFE",
                "error": None,
            })

    result_df = pd.DataFrame(nsfw_results)

    # Ensure every input URL has at least one row
    if not result_df.empty:
        if "provider_id" in result_df.columns and "image_url" in result_df.columns:
            result_df = result_df.drop_duplicates(subset=["provider_id", "image_url"])
    else:
        # No valid images processed at all
        result_df = image_df.copy()
        if "provider_id" not in result_df.columns:
            # Fallback: ensure provider_id column exists
            result_df["provider_id"] = result_df.get("service_id")
        result_df["nsfw_score"] = None
        result_df["nsfw_label"] = "URL_NOT_FOUND"
        result_df["error"] = "No valid image URLs"

    return result_df


# ---------------------- WRAPPER FOR SERVICE & PROVIDER ----------------------
def run_for_all(serviceDf, providerDf):
    """
    Run NSFW detection for both service and provider dataframes.
    Handles cases where there are no valid image URLs.
    """

    # -------- Services --------
    if serviceDf is not None and not serviceDf.empty:
        service_images_df = prepare_image_dataframe(
            serviceDf,
            id_column="service_id",
            image_columns=["image_url", "other_image_urls"],
        )

        if not service_images_df.empty:
            # Re-use provider_id column in classification to keep downstream merge handling simple
            service_images_df = service_images_df.rename(columns={"service_id": "provider_id"})
            service_nsfw_df = classify_images(service_images_df)

            # Merge back on service_id (original ID)
            serviceDf = serviceDf.merge(
                service_nsfw_df[["provider_id", "image_url", "nsfw_label", "nsfw_score"]],
                left_on="service_id",
                right_on="provider_id",
                how="left",
            )
            serviceDf.drop(columns=["provider_id"], inplace=True, errors="ignore")
        else:
            serviceDf["nsfw_score"] = 0.0
            serviceDf["nsfw_label"] = "SAFE"
            # Do not override existing image_url columns
    else:
        # If the entire DF is empty or None, just return it as is
        pass

    # -------- Providers --------
    if providerDf is not None and not providerDf.empty:
        provider_images_df = prepare_image_dataframe(
            providerDf,
            id_column="provider_id",
            image_columns=["profile_picture_url", "bio_image", "provider_store_images", "about_image"],
        )

        if not provider_images_df.empty:
            provider_nsfw_df = classify_images(provider_images_df)
            if not provider_nsfw_df.empty and "provider_id" in provider_nsfw_df.columns:
                providerDf = providerDf.merge(
                    provider_nsfw_df[["provider_id", "image_url", "nsfw_label", "nsfw_score"]],
                    on="provider_id",
                    how="left",
                )
            else:
                providerDf["nsfw_score"] = 0.0
                providerDf["nsfw_label"] = "SAFE"
        else:
            providerDf["nsfw_score"] = 0.0
            providerDf["nsfw_label"] = "SAFE"
    else:
        # If the entire DF is empty or None, just return it as is
        pass

    return serviceDf, providerDf
