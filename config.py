import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.environ.get("COMPUTE_COMMUNITY_API_KEY")
if not API_KEY:
    raise RuntimeError("COMPUTE_COMMUNITY_API_KEY not set in .env")

RATE_LIMIT_SLEEP_SECONDS = 2.0
MAX_AGENT_STEPS = 10

MODELS = {
    "qwen": {
        "display_name": "Qwen 3.6 35B",
        "model_id": "Qwen/Qwen3.6-35B-A3B-FP8",
        "base_url": "https://computecommunity.com/u/C7XfWXayLelTkySS7to8stLtwvV3Lj3J/nodes/runpod-qwen3-5-35b/v1",
    },
    "gemma": {
        "display_name": "Gemma 4 31B",
        "model_id": "google/gemma-4-31B-it",
        "base_url": "https://computecommunity.com/u/CTFaQ3cxUcRbXCpuqCASNw9Y5xrU0LdQ/nodes/runpod-gemma-4-31b/v1",
    },
}


def get_client(model_key: str) -> OpenAI:
    """Return a configured OpenAI client for the given model key."""
    if model_key not in MODELS:
        raise ValueError(f"Unknown model: {model_key}. Must be one of {list(MODELS.keys())}")
    return OpenAI(
        base_url=MODELS[model_key]["base_url"],
        api_key=API_KEY,
    )
