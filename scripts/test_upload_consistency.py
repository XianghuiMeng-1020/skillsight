#!/usr/bin/env python3
"""
Upload parser consistency test.

For each extension in SUPPORTED_EXTENSIONS:
- Build a minimal input payload
- Parse it 10 times
- Verify media_type and chunk_count stay consistent
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    backend = repo_root / "backend"
    scripts_dir = repo_root / "scripts"
    if scripts_dir.is_dir():
        sys.path.insert(0, str(scripts_dir))
    if backend.is_dir():
        sys.path.insert(0, str(backend))
        os.chdir(backend)

    from app.parsers_multimodal import SUPPORTED_EXTENSIONS, parse_multimodal_file
    from verify_upload_formats import minimal_content

    rounds = 10
    failed: list[tuple[str, str]] = []

    for ext in sorted(SUPPORTED_EXTENSIONS.keys()):
        baseline = None
        for i in range(rounds):
            try:
                result = parse_multimodal_file(
                    file_bytes=minimal_content(ext),
                    filename=f"consistency_{i}{ext}",
                    min_chunk_len=30,
                )
            except Exception as e:  # pragma: no cover - test script output path
                failed.append((ext, f"round {i + 1} raised: {e}"))
                break

            signature = (
                result.get("media_type", "unknown"),
                len(result.get("chunks", [])),
            )
            if baseline is None:
                baseline = signature
            elif baseline != signature:
                failed.append(
                    (
                        ext,
                        f"inconsistent result: baseline={baseline}, round {i + 1}={signature}",
                    )
                )
                break

        if baseline is not None and not any(item[0] == ext for item in failed):
            print(f"OK {ext:8} -> media_type={baseline[0]:12} chunks={baseline[1]} (x{rounds})")

    if failed:
        print("\nConsistency failures:")
        for ext, reason in failed:
            print(f"- {ext}: {reason}")
        return 1

    print(f"\nAll formats consistent across {rounds} runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
