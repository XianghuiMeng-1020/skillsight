import json
from jsonschema import validate

def load_schema(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_first_json_obj(text: str) -> dict:
    """
    Robustly extract the first {...} JSON object from model output.
    Handles models that output extra reasoning text.
    """
    t = (text or "").strip()

    # Remove markdown fences if present
    if "```" in t:
        parts = []
        in_fence = False
        for line in t.splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                parts.append(line)
        if parts:
            t = "\n".join(parts).strip()

    # Find first JSON object by brace matching
    start = t.find("{")
    if start == -1:
        raise ValueError("No JSON object found")
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = t[start:i+1]
                return json.loads(candidate)
    raise ValueError("Unclosed JSON object")

def validate_or_raise(obj: dict, schema: dict) -> dict:
    validate(instance=obj, schema=schema)
    return obj
