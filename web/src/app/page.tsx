"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type DocItem = {
  doc_id: string;
  filename: string;
  created_at: string;
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
};

export default function Home() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  const [status, setStatus] = useState<string>("checking...");
  const [file, setFile] = useState<File | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string>("");

  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState<boolean>(false);

  // Search state
  const [query, setQuery] = useState<string>("privacy academic integrity");
  const [k, setK] = useState<number>(5);
  const [selectedDocId, setSelectedDocId] = useState<string>("ALL");
  const [searchMsg, setSearchMsg] = useState<string>("");
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [searching, setSearching] = useState<boolean>(false);
  const [tokens, setTokens] = useState<string[]>([]);

  async function refreshDocs() {
    setLoadingDocs(true);
    try {
      const res = await fetch(`${apiBase}/documents?limit=50`);
      const data = await res.json();
      setDocs(data.items || []);
    } catch {
      // ignore
    } finally {
      setLoadingDocs(false);
    }
  }

  useEffect(() => {
    fetch(`${apiBase}/health`)
      .then((r) => r.json())
      .then((data) => setStatus(data?.ok ? "API ok ✅" : "API not ok ❌"))
      .catch(() => setStatus("API unreachable ❌"));

    refreshDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const docOptions = useMemo(() => {
    return [
      { value: "ALL", label: "All documents" },
      ...docs.map((d) => ({
        value: d.doc_id,
        label: `${d.filename} (${d.doc_id.slice(0, 8)}…)`,
      })),
    ];
  }, [docs]);

  async function onUpload() {
    setUploadMsg("");
    if (!file) {
      setUploadMsg("Please choose a .txt file first.");
      return;
    }
    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch(`${apiBase}/documents/upload`, {
        method: "POST",
        body: form,
      });

      const data = await res.json();
      if (!res.ok) {
        setUploadMsg(`Upload failed: ${data?.detail || "unknown error"}`);
        return;
      }

      setUploadMsg(`Uploaded ✅ doc_id = ${data.doc_id}`);
      setFile(null);
      await refreshDocs();
    } catch (e: any) {
      setUploadMsg(`Upload error: ${String(e)}`);
    }
  }

  async function onSearch() {
    setSearchMsg("");
    setEvidence([]);
    setTokens([]);

    const q = query.trim();
    if (!q) {
      setSearchMsg("Please enter a query first.");
      return;
    }

    setSearching(true);
    try {
      const body: any = { query: q, k };
      if (selectedDocId !== "ALL") body.doc_id = selectedDocId;

      const res = await fetch(`${apiBase}/search/evidence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setSearchMsg(`Search failed: ${data?.detail || `HTTP ${res.status}`}`);
        return;
      }

      setEvidence(data.items || []);
      setTokens(data.query_tokens || []);
      if ((data.items || []).length === 0) setSearchMsg("No evidence found (score>0). Try different words.");
    } catch (e: any) {
      setSearchMsg(`Search error: ${String(e.message || e)}`);
    } finally {
      setSearching(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 980 }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>SkillSight running</h1>
      <p style={{ marginBottom: 12 }}>
        Backend status: <b>{status}</b>
      </p>
      <p style={{ marginBottom: 24, color: "#666" }}>API base: {apiBase}</p>

      {/* Evidence Search */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 10 }}>Week 3: Evidence search (Decision 1 baseline)</h2>
        <div style={{ color: "#666", fontSize: 13, marginBottom: 12 }}>
          This baseline ranks chunks by keyword match count. Use "Document scope" to search within one uploaded artifact.
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., academic integrity, privacy, teamwork..."
            style={{ flex: "1 1 460px", padding: 8, border: "1px solid #ccc", borderRadius: 6 }}
          />

          <select
            value={selectedDocId}
            onChange={(e) => setSelectedDocId(e.target.value)}
            style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 220 }}
          >
            {docOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "#666" }}>Top K:</span>
            <input
              type="number"
              value={k}
              onChange={(e) => setK(Number(e.target.value))}
              min={1}
              max={50}
              style={{ width: 80, padding: 8, border: "1px solid #ccc", borderRadius: 6 }}
            />
          </div>

          <button onClick={onSearch} disabled={searching} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {searching ? "Searching..." : "Search"}
          </button>
        </div>

        {tokens.length > 0 && (
          <div style={{ marginTop: 10, color: "#666", fontSize: 13 }}>
            tokens used: {tokens.join(", ")}
          </div>
        )}

        {searchMsg && <div style={{ marginTop: 10, color: "crimson" }}>{searchMsg}</div>}

        {evidence.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <h3 style={{ fontSize: 16, marginBottom: 10 }}>Top evidence</h3>
            <ul style={{ paddingLeft: 16 }}>
              {evidence.map((ev) => (
                <li key={ev.chunk_id} style={{ marginBottom: 12 }}>
                  <div style={{ marginBottom: 4 }}>
                    <b>score={ev.score}</b>{" "}
                    <span style={{ color: "#666" }}>
                      (doc {ev.doc_id.slice(0, 8)}…, chunk {ev.idx}, char [{ev.char_start},{ev.char_end}])
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: "#333", marginBottom: 4 }}>
                    {ev.snippet}
                  </div>
                  <div style={{ fontSize: 13 }}>
                    <Link href={`/documents/${ev.doc_id}`} style={{ textDecoration: "underline" }}>
                      Open document chunks →
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Upload */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>Upload a .txt document</h2>

        <input type="file" accept=".txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />

        <button onClick={onUpload} style={{ marginLeft: 12, padding: "6px 12px", cursor: "pointer" }}>
          Upload
        </button>

        <div style={{ marginTop: 12, color: uploadMsg.includes("failed") ? "crimson" : "#111" }}>{uploadMsg}</div>

        <div style={{ marginTop: 8, color: "#666", fontSize: 13 }}>
          Note: documents are auto-chunked by blank-line paragraphs.
        </div>
      </section>

      {/* Recent uploads */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>Recent uploads</h2>

        <button onClick={refreshDocs} style={{ padding: "6px 12px", cursor: "pointer" }}>
          Refresh
        </button>

        {loadingDocs && <p style={{ color: "#666" }}>Loading...</p>}
        {!loadingDocs && docs.length === 0 && <p style={{ color: "#666" }}>No documents yet.</p>}

        {!loadingDocs && docs.length > 0 && (
          <ul style={{ marginTop: 12 }}>
            {docs.map((d) => (
              <li key={d.doc_id} style={{ marginBottom: 10 }}>
                <div><b>{d.filename}</b></div>
                <div style={{ color: "#666", fontSize: 13 }}>
                  doc_id:{" "}
                  <Link href={`/documents/${d.doc_id}`} style={{ textDecoration: "underline" }}>
                    {d.doc_id}
                  </Link>
                </div>
                <div style={{ color: "#666", fontSize: 13 }}>created_at: {d.created_at}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
