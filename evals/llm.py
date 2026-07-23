"""Swappable LLM interface: llm_call(prompt, model_role) -> text.

HOW THIS FILE FITS INTO THE PROJECT
-----------------------------------
Every LLM request in the eval harness goes through this one function, from two
callers:
  - evals/configs.py  calls llm_call(..., model_role="answer") to generate answers
  - evals/judge.py    calls llm_call(..., model_role="judge") to grade them

Two backends hide behind the LLM_PROVIDER environment variable: 'anthropic'
(the default, direct API) and 'bedrock' (AWS). Nothing outside this module
knows which one is in use — that isolation is a project ground rule, so
swapping providers later is a one-line env change, not a refactor.

Every response is cached on disk keyed by (provider, model, prompt), so
re-running the harness costs $0 — only never-before-seen prompts hit the API.
"""
import hashlib
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "evals", ".llm_cache")

# Which model serves each role, per provider. Both roles use the same model on
# purpose: the judge should be at least as capable as the answerer.
MODELS = {
    "anthropic": {"answer": "claude-opus-4-8", "judge": "claude-opus-4-8"},
    "bedrock": {"answer": "anthropic.claude-opus-4-8", "judge": "anthropic.claude-opus-4-8"},
}
MAX_TOKENS = 1024  # answers and judge verdicts are short; caps cost per call


def load_env(path=os.path.join(REPO, ".env")):
    """Populate os.environ from the repo's .env file (API keys live there).

    setdefault means a variable already set in the real environment wins over
    the file. Runs once at import time below; evals/embeddings.py also calls
    it so it works when imported on its own.
    """
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

# One API client per provider, created lazily on first use and then reused
# (creating a client per call would waste connections).
_clients = {}


def _client(provider):
    """Return the (cached) API client for a provider. Called by llm_call()."""
    if provider not in _clients:
        if provider == "anthropic":
            import anthropic
            _clients[provider] = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        elif provider == "bedrock":
            from anthropic import AnthropicBedrockMantle
            _clients[provider] = AnthropicBedrockMantle(
                aws_region=os.environ.get("AWS_REGION", "us-east-2"))
        else:
            raise ValueError(f"unknown LLM_PROVIDER {provider!r}")
    return _clients[provider]


def _cache_path(provider, model, prompt):
    """Deterministic cache filename: hash of everything that shapes the reply.

    Same provider + model + prompt -> same file -> cache hit. Called by
    llm_call().
    """
    key = hashlib.sha256(f"{provider}|{model}|{prompt}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, key + ".json")


def llm_call(prompt, model_role="answer"):
    """Send one prompt to the configured LLM and return its text reply.

    The only public function in this module. Flow:
      1. Pick provider (env var) and model (role table above).
      2. Cache hit? Return the stored text — no API call, no cost.
      3. Otherwise call the API, extract the text block, store it, return it.

    A safety refusal comes back as the marker string "[REFUSAL]" rather than
    raising, so one refused row can't crash a whole eval run.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    model = MODELS[provider][model_role]

    path = _cache_path(provider, model, prompt)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)["text"]

    response = _client(provider).messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},  # model decides how much to reason
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        text = "[REFUSAL]"
    else:
        # The response is a list of typed blocks; we want the first text one.
        text = next((b.text for b in response.content if b.type == "text"), "")

    # Store the full context alongside the text so cache files are debuggable.
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"provider": provider, "model": model, "role": model_role,
                   "prompt": prompt, "text": text}, f)
    return text
