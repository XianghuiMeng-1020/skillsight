"use client";

import { useEffect, useState } from "react";

type DocItem = {
  doc_id: string;
  filename: string;
  created_at: string;
};

export default function Home() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  const [status, setStatus] = useState<string>("checking...");
  const [file, setFile] = useState<File | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string>("");
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState<boolean>(false);

  async function refreshDocs() {
    setLoadingDocs(true);
    try {
      const res = await fetch(`${apiBase}/documents?limit=20`);
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

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 900 }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>SkillSight running</h1>
      <p style={{ marginBottom: 16 }}>
        Backend status: <b>{status}</b>
      </p>
      <p style={{ marginBottom: 24, color: "#666" }}>API base: {apiBase}</p>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>Week 1: Upload a .txt document</h2>

        <input
          type="file"
          accept=".txt"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />

        <button
          onClick={onUpload}
          style={{ marginLeft: 12, padding: "6px 12px", cursor: "pointer" }}
        >
          Upload
        </button>

        <div style={{ marginTop: 12, color: uploadMsg.includes("failed") ? "crimson" : "#111" }}>
          {uploadMsg}
        </div>

        <div style={{ marginTop: 8, color: "#666", fontSize: 13 }}>
          Note: Week1 backend only accepts .txt files (we'll add PDF/DOCX later).
        </div>
      </section>

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
                  doc_id: {d.doc_id}
                </div>
                <div style={{ color: "#666", fontSize: 13 }}>
                  created_at: {d.created_at}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
