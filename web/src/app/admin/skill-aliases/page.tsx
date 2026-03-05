"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function SkillAliasesAdmin() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  const [alias, setAlias] = useState("cheating");
  const [resolveRes, setResolveRes] = useState<any>(null);
  const [conflicts, setConflicts] = useState<any[]>([]);
  const [msg, setMsg] = useState("");

  async function refreshConflicts() {
    setMsg("");
    const r = await fetch(`${apiBase}/skills/aliases/conflicts?limit=200`);
    const data = await r.json().catch(()=>({}));
    if (!r.ok) { setMsg(data?.detail || `HTTP ${r.status}`); setConflicts([]); return; }
    setConflicts(data.items || []);
  }

  async function doResolve() {
    setMsg("");
    setResolveRes(null);
    const r = await fetch(`${apiBase}/skills/resolve?alias=${encodeURIComponent(alias)}`);
    const data = await r.json().catch(()=>({}));
    if (!r.ok) { setMsg(data?.detail || `HTTP ${r.status}`); return; }
    setResolveRes(data);
  }

  useEffect(() => { refreshConflicts(); }, []);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 1000 }}>
      <div style={{ marginBottom: 14 }}>
        <Link href="/admin" style={{ textDecoration:"underline" }}>← Back</Link>
      </div>
      <h1 style={{ fontSize: 22, marginBottom: 10 }}>Skill alias conflicts</h1>

      <section style={{ border:"1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ display:"flex", gap: 10, alignItems:"center", flexWrap:"wrap" }}>
          <input value={alias} onChange={(e)=>setAlias(e.target.value)} style={{ padding:8, border:"1px solid #ccc", borderRadius:6, minWidth: 260 }} />
          <button onClick={doResolve} style={{ padding:"8px 14px", cursor:"pointer" }}>Resolve</button>
          <button onClick={refreshConflicts} style={{ padding:"8px 14px", cursor:"pointer" }}>Refresh conflicts</button>
          <a href={`${apiBase}/skills/aliases/conflicts/report?format=csv`} style={{ textDecoration:"underline" }}>Download CSV report</a>
        </div>
        {msg && <div style={{ marginTop: 10, color: "crimson" }}>{msg}</div>}
      </section>

      <section style={{ border:"1px solid #eee", borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Resolve result</div>
        {!resolveRes && <div style={{ color:"#666" }}>Run Resolve to see canonical skill or conflict.</div>}
        {resolveRes && <pre style={{ fontSize: 12, whiteSpace:"pre-wrap" }}>{JSON.stringify(resolveRes, null, 2)}</pre>}
      </section>

      <section>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Conflicts ({conflicts.length})</div>
        {conflicts.map((c) => (
          <div key={c.alias} style={{ border:"1px solid #eee", borderRadius: 8, padding: 12, marginBottom: 10 }}>
            <div><b>{c.alias}</b> → n_skills={c.n_skills}</div>
            <div style={{ color:"#666", fontSize: 13 }}>{(c.skill_ids||[]).join(", ")}</div>
          </div>
        ))}
        {conflicts.length===0 && <div style={{ color:"#666" }}>No conflicts.</div>}
      </section>
    </main>
  );
}
