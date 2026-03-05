import os
import requests

# Allow override via environment variable, default to 127.0.0.1 to avoid IPv6 issues
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

def ollama_generate(model: str, prompt: str, temperature: float = 0.0, timeout_s: int = 180) -> str:
    """
    Calls local Ollama HTTP API (non-stream).
    Bypasses proxy settings to ensure direct connection to local Ollama.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature}
    }
    # Bypass proxy for local Ollama connection
    r = requests.post(url, json=payload, timeout=timeout_s, proxies={"http": None, "https": None})
    r.raise_for_status()
    data = r.json()
    return data.get("response", "")
