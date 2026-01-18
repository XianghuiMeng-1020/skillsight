import json
from pathlib import Path

from schemas.skillsight_models import Skill, Role, EvidencePointer, AuditLog, ConsentRecord

OUT_DIR = Path(__file__).parent

def dump_schema(model, name: str):
    schema = model.model_json_schema()
    (OUT_DIR / f"{name}.schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"[WRITE] {name}.schema.json")

def main():
    dump_schema(Skill, "Skill")
    dump_schema(Role, "Role")
    dump_schema(EvidencePointer, "EvidencePointer")
    dump_schema(AuditLog, "AuditLog")
    dump_schema(ConsentRecord, "ConsentRecord")

if __name__ == "__main__":
    main()
