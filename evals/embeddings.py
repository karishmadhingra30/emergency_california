"""Titan embeddings via Bedrock — EVAL HARNESS ONLY, never on the device.

Uses AWS_PROFILE (must be 'emergency' — personal account; the machine default
profile is a shared collaborator account). Embeddings are cached per text.
"""
import hashlib
import json
import math
import os

from evals.llm import load_env

load_env()

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "evals", ".llm_cache")
MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
DIMENSIONS = 256

_client = None


def _bedrock():
    global _client
    if _client is None:
        import boto3
        _client = boto3.Session(
            profile_name=os.environ.get("AWS_PROFILE", "emergency"),
            region_name=os.environ.get("AWS_REGION", "us-east-2"),
        ).client("bedrock-runtime")
    return _client


def embed(text):
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
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
