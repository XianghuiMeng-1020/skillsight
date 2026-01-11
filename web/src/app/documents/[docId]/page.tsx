"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

type ChunkItem = {
  chunk_id: string;
  doc_id: string;
  idx: number;
  char_start: number;
  char_end: number;
  snippet: string;
  quote_hash?: string;
  created_at: string;
};

type SkillItem = {
  skill_id: string;
  canonical_name: string;
  aliases?: string[];
  definition?: string;
};

type EvidenceItem = {
  chunk_id: string;
  doc_id: string;
  idx: number;
  char_start: number;
  char_end: number;
  snippet: string;
  created_at: string;
  score: number;
  score_meta?: any;
};

type AssessResult = {
  skill_id: string;
  doc_id: string;
  decision: "demonstrated" | "mentioned" | "not_enough_information";
  matched_terms: string[];
  best_evidence: EvidenceItem | null;
  evidence: EvidenceItem[];
  decision_meta: any;
};

export default function DocChunksPage() {
  const params = useParams<{ docId: string }>();
  const docId = params?.docId;

  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  // chunks view
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [err, setErr] = useState<string>("");

  // skills + assess
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [skillId, setSkillId] = useState<string>("");
  const [assessing, setAssessing] = useState<boolean>(false);
  const [assessErr, setAssessErr] = useState<string>("");
  const [assessRes, setAssessRes] = useState<AssessResult | null>(null);

  useEffect(() => {
    // load skills
    fetch(`${apiBase}/skills`)
      .then((r) => r.json())
      .then((data) => {
        const items: SkillItem[] = data.items || [];
        setSkills(items);
        if (!skillId && items.length > 0) setSkillId(items[0].skill_id);
      })
      .catch(() => {
        // ignore
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!docId) return;

    setLoading(true);
    setErr("");

    fetch(`${apiBase}/documents/${docId}/chunks?limit=200`)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        setChunks(data.items || []);
      })
      .catch((e) => setErr(`Failed to load chunks: ${String(e.message || e)}`))
      .finally(() => setLoading(false));
  }, [apiBase, docId]);

  async function runAssess() {
    setAssessErr("");
    setAssessRes(null);

    if (!docId) {
      setAssessErr("Missing doc_id.");
      return;
    }
    if (!skillId) {
      setAssessErr("Please choose a skill first.");
      return;
    }

    setAssessing(true);
    try {
      const res = await fetch(`${apiBase}/assess/skill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_id: skillId, doc_id: docId, k: 10, store: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setAssessRes(data as AssessResult);
    } catch (e: any) {
      setAssessErr(String(e.message || e));
    } finally {
      setAssessing(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 980 }}>
      <div style={{ marginBottom: 14 }}>
        <Link href="/" style={{ textDecoration: "underline" }}>← Back</Link>
      </div>

      <h1 style={{ fontSize: 22, marginBottom: 6 }}>Document view</h1>
      <div style={{ color: "#666", marginBottom: 16 }}>doc_id: {docId}</div>

      {/* Decision 2 assess panel */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 18 }}>
        <h2 style={{ fontSize: 16, marginBottom: 10 }}>Decision 2: Assess skill on this document (rule_v0)</h2>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <select
            value={skillId}
            onChange={(e) => setSkillId(e.target.value)}
            style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 320 }}
          >
            {skills.length === 0 && <option>Loading skills...</option>}
            {skills.map((s) => (
              <option key={s.skill_id} value={s.skill_id}>
                {s.canonical_name} ({s.skill_id})
              </option>
            ))}
          </select>

          <button
            onClick={runAssess}
            disabled={assessing}
            style={{ padding: "8px 14px", cursor: "pointer" }}
          >
            {assessing ? "Assessing..." : "Assess"}
          </button>
        </div>

        {assessErr && <div style={{ marginTop: 10, color: "crimson" }}>{assessErr}</div>}

        {assessRes && (
          <div style={{ marginTop: 12 }}>
            <div style={{ marginBottom: 6 }}>
              <b>decision:</b> {assessRes.decision}
            </div>
            <div style={{ marginBottom: 10 }}>
              <b>matched_terms:</b> {assessRes.matched_terms?.join(", ") || "(none)"}
            </div>

            {assessRes.best_evidence && (
              <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12 }}>
                <div style={{ marginBottom: 6 }}>
                  <b>best_evidence</b>{" "}
                  <span style={{ color: "#666" }}>
                    (chunk {assessRes.best_evidence.idx}, score {assessRes.best_evidence.score?.toFixed?.(3) ?? assessRes.best_evidence.score})
                  </span>
                </div>
                <div style={{ fontSize: 13 }}>{assessRes.best_evidence.snippet}</div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Chunks list */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>Chunks</h2>

        {loading && <p style={{ color: "#666" }}>Loading...</p>}
        {!loading && err && <p style={{ color: "crimson" }}>{err}</p>}
        {!loading && !err && chunks.length === 0 && <p style={{ color: "#666" }}>No chunks found for this document.</p>}

        {!loading && !err && chunks.length > 0 && (
          <ul style={{ marginTop: 12 }}>
            {chunks.map((c) => (
              <li
                key={c.chunk_id}
                style={{ marginBottom: 14, padding: 12, border: "1px solid #eee", borderRadius: 8 }}
              >
                <div style={{ marginBottom: 6 }}>
                  <b>Chunk {c.idx}</b> | char [{c.char_start}, {c.char_end}]
                </div>
                <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 13 }}>
                  {c.snippet}
                </div>
                <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
                  chunk_id: {c.chunk_id}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
