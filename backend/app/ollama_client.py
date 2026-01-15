import httpx

def ollama_generate(model: str, prompt: str, temperature: float = 0.0, timeout_s: int = 180) -> str:
    """
    Calls local Ollama HTTP API (non-stream).
    """
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature}
    }
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "")
