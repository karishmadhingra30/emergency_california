"""Titan embeddings via AWS Bedrock — EVAL HARNESS ONLY, never on the device.

HOW THIS FILE FITS INTO THE PROJECT
-----------------------------------
An embedding turns text into a list of numbers that captures its MEANING, so
"he's gushing red stuff" can match the bleeding entry even though they share
no words. evals/configs.py uses this for the 'embedding_grounded' comparison
configuration: it embeds every corpus entry once plus each gold-set query,
then ranks entries by cosine similarity.

This exists purely to compare meaning-search against the device's keyword
search (FTS). The device itself never embeds anything — that would need a
model and (here) a network call, both banned from the emergency path.

Uses AWS_PROFILE (must be 'emergency' — personal account; the machine default
profile is a shared collaborator account and must never be billed).
Every embedding is cached on disk, so repeat runs are free.
"""
import hashlib
import json
import math
import os

from evals.llm import load_env

load_env()  # ensure AWS_* vars from .env are set even if imported standalone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "evals", ".llm_cache")
MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
DIMENSIONS = 256  # vector length; 256 is Titan's smallest and plenty for 25 entries

# Lazily-created boto3 client, shared across calls (same pattern as llm.py).
_client = None


def _bedrock():
    """Return the (cached) Bedrock client. Called by embed()."""
    global _client
    if _client is None:
        import boto3
        _client = boto3.Session(
            profile_name=os.environ.get("AWS_PROFILE", "emergency"),
            region_name=os.environ.get("AWS_REGION", "us-east-2"),
        ).client("bedrock-runtime")
    return _client


def embed(text):
    """Turn one string into its 256-number embedding vector.

    Called by evals/configs.py — once per corpus entry (cached forever after)
    and once per gold-set query. Checks the disk cache first; only new text
    reaches AWS.
    """
    key = hashlib.sha256(f"emb|{MODEL_ID}|{DIMENSIONS}|{text}".encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)["embedding"]

    response = _bedrock().invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": DIMENSIONS}),
    )
    vector = json.loads(response["body"].read())["embedding"]

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"model": MODEL_ID, "text": text, "embedding": vector}, f)
    return vector


def cosine(a, b):
    """Similarity between two vectors: 1.0 = same direction, 0 = unrelated.

    Standard cosine similarity — the dot product divided by both lengths.
    Called by evals/configs.py to rank corpus entries against a query.
    """
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
