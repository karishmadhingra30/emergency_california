"""Swappable LLM interface: llm_call(prompt, model_role) -> text.

Two backends behind LLM_PROVIDER: 'anthropic' (default) and 'bedrock'.
Provider details never leak past this module. Every response is cached on
(provider, model, prompt) so harness re-runs are free.
"""
import hashlib
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "evals", ".llm_cache")

MODELS = {
    "anthropic": {"answer": "claude-opus-4-8", "judge": "claude-opus-4-8"},
    "bedrock": {"answer": "anthropic.claude-opus-4-8", "judge": "anthropic.claude-opus-4-8"},
}
MAX_TOKENS = 1024


def load_env(path=os.path.join(REPO, ".env")):
    """Populate os.environ from .env without overriding real env vars."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


load_env()

_clients = {}


def _client(provider):
    if provider not in _clients:
        if provider == "anthropic":
            import anthropic
            _clients[provider] = anthropic.Anthropic()
        elif provider == "bedrock":
            from anthropic import AnthropicBedrockMantle
            _clients[provider] = AnthropicBedrockMantle(
                aws_region=os.environ.get("AWS_REGION", "us-east-2"))
        else:
            raise ValueError(f"unknown LLM_PROVIDER {provider!r}")
    return _clients[provider]


def _cache_path(provider, model, prompt):
    key = hashlib.sha256(f"{provider}|{model}|{prompt}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, key + ".json")


def llm_call(prompt, model_role="answer"):
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    model = MODELS[provider][model_role]

    path = _cache_path(provider, model, prompt)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)["text"]

    response = _client(provider).messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        text = "[REFUSAL]"
    else:
        text = next((b.text for b in response.content if b.type == "text"), "")

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"provider": provider, "model": model, "role": model_role,
                   "prompt": prompt, "text": text}, f)
    return text
