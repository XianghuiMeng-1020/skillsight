"use client";
import Link from "next/link";
import { useEffect, useState, memo } from "react";
import { getToken } from "@/lib/bffClient";
import { useToast } from "@/components/Toast";

const JobRow = memo(function JobRow({ it, onRetry }: { it: { job_id: string; status: string; job_type?: string; doc_id?: string; attempts?: number; last_error?: string }; onRetry: (id: string) => void }) {
  return (
    <div key={it.job_id} style={{ border:"1px solid #eee", borderRadius: 8, padding: 12 }}>
      <div style={{ display:"flex", justifyContent:"space-between", flexWrap:"wrap", gap: 12 }}>
        <div>
          <div><b>{it.status}</b> — {it.job_type ?? "embed"}</div>
          <div style={{ color:"#666", fontSize: 13 }}>job_id: {it.job_id}</div>
          <div style={{ color:"#666", fontSize: 13 }}>doc_id: {it.doc_id}</div>
          <div style={{ color:"#666", fontSize: 13 }}>attempts: {it.attempts ?? 0}</div>
        </div>
        <div>
          <button onClick={()=>onRetry(it.job_id)} style={{ padding:"6px 12px", cursor:"pointer" }}>Retry</button>
        </div>
      </div>
      {it.last_error && <div style={{ marginTop: 8, color:"crimson", fontSize: 13 }}><b>last_error:</b> {it.last_error}</div>}
    </div>
  );
});

export default function JobsAdmin() {
  const { addToast } = useToast();
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
  const [status, setStatus] = useState("");
  const [docId, setDocId] = useState("");
  const [items, setItems] = useState<any[]>([]);
  const [msg, setMsg] = useState("");

  function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function refresh() {
    setMsg("");
    const qs = new URLSearchParams({ limit: "100" });
    if (status.trim()) qs.set("status", status.trim());
    if (docId.trim()) qs.set("doc_id", docId.trim());
    const r = await fetch(`${apiBase}/bff/admin/jobs?${qs.toString()}`, { headers: authHeaders() });
    const data = await r.json().catch(()=>({}));
    if (!r.ok) {
      const err = data?.detail || `HTTP ${r.status}`;
      setMsg(err);
      addToast('error', typeof err === 'string' ? err : JSON.stringify(err));
      setItems([]);
      return;
    }
    setItems(data.items || []);
  }

  async function retry(jobId: string) {
    setMsg("");
    const r = await fetch(`${apiBase}/bff/admin/jobs/${jobId}/retry`, { method:"POST", headers: authHeaders() });
    const data = await r.json().catch(()=>({}));
    if (!r.ok) {
      const err = data?.detail || `HTTP ${r.status}`;
      setMsg(err);
      addToast('error', typeof err === 'string' ? err : JSON.stringify(err));
      return;
    }
    setMsg(`Retry queued: ${jobId}`);
    addToast('success', `Retry queued: ${jobId}`);
    await refresh();
  }

  useEffect(() => { refresh(); }, []);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 1100 }}>
      <div style={{ marginBottom: 14 }}>
        <Link href="/admin" style={{ textDecoration:"underline" }}>← Back</Link>
      </div>
      <h1 style={{ fontSize: 22, marginBottom: 10 }}>Jobs dashboard</h1>

      <section style={{ border:"1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ display:"flex", gap: 10, alignItems:"center", flexWrap:"wrap" }}>
          <label>Status</label>
          <input value={status} onChange={(e)=>setStatus(e.target.value)} placeholder="queued|running|succeeded|failed"
            style={{ padding:8, border:"1px solid #ccc", borderRadius:6, minWidth:220 }} />
          <label>doc_id</label>
          <input value={docId} onChange={(e)=>setDocId(e.target.value)}
            style={{ padding:8, border:"1px solid #ccc", borderRadius:6, minWidth:380 }} />
          <button onClick={refresh} style={{ padding:"8px 14px", cursor:"pointer" }}>Refresh</button>
        </div>
        {msg && <div style={{ marginTop: 10, color: msg.includes("Retry") ? "#146c2e" : "crimson" }}>{msg}</div>}
      </section>

      <div style={{ color:"#666", marginBottom: 8 }}>items: {items.length}</div>

      <div style={{ display:"grid", gap: 10 }}>
        {items.map((it) => (
          <JobRow key={it.job_id} it={it} onRetry={retry} />
        ))}
        {items.length===0 && <div style={{ color:"#666" }}>No jobs.</div>}
      </div>
    </main>
  );
}
