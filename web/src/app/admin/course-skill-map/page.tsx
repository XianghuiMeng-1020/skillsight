"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function CourseSkillMapAdmin() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
  const [subjectId, setSubjectId] = useState("staff_demo");
  const [role, setRole] = useState("staff");

  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [noteById, setNoteById] = useState<Record<string,string>>({});

  useEffect(() => {
    try {
      const sid = localStorage.getItem("skillsight_subject_id");
      const r = localStorage.getItem("skillsight_role");
      if (sid) setSubjectId(sid);
      if (r) setRole(r);
    } catch {}
  }, []);

  async function refresh() {
    setMsg("");
    const qs = new URLSearchParams({ status, limit: "200" });
    const r = await fetch(`${apiBase}/db/course_skill_map?${qs.toString()}`, { headers: { "X-Subject-Id": subjectId, "X-Role": role } });
    const data = await r.json().catch(()=>({}));
    if (!r.ok) { setMsg(data?.detail || `HTTP ${r.status}`); setItems([]); return; }
    setItems(data.items || []);
  }

  async function act(mapId: string, action: "approve"|"reject") {
    setMsg("");
    const note = noteById[mapId] || "";
    const r = await fetch(`${apiBase}/db/course_skill_map/${mapId}/${action}`, {
      method: "POST",
      headers: { "Content-Type":"application/json", "X-Subject-Id": subjectId, "X-Role": role },
      body: JSON.stringify({ note })
    });
    const data = await r.json().catch(()=>({}));
    if (!r.ok) { setMsg(data?.detail || `HTTP ${r.status}`); return; }
    setMsg(`${action} OK`);
    await refresh();
  }

  useEffect(() => { refresh(); }, [subjectId, role]);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 1100 }}>
      <div style={{ marginBottom: 14 }}>
        <Link href="/admin" style={{ textDecoration:"underline" }}>← Back</Link>
      </div>
      <h1 style={{ fontSize: 22, marginBottom: 10 }}>Course→Skill review queue</h1>

      <section style={{ border:"1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ display:"flex", gap: 12, alignItems:"center", flexWrap:"wrap" }}>
          <label>Status</label>
          <select value={status} onChange={(e)=>setStatus(e.target.value)} style={{ padding:8, border:"1px solid #ccc", borderRadius:6 }}>
            <option value="pending">pending</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
          </select>
          <button onClick={refresh} style={{ padding:"8px 14px", cursor:"pointer" }}>Refresh</button>
        </div>
        {msg && <div style={{ marginTop: 10, color: msg.includes("OK") ? "#146c2e" : "crimson" }}>{msg}</div>}
      </section>

      <div style={{ color:"#666", marginBottom: 8 }}>items: {items.length}</div>

      <div style={{ display:"grid", gap: 10 }}>
        {items.map((it) => (
          <div key={it.map_id} style={{ border:"1px solid #eee", borderRadius: 8, padding: 12 }}>
            <div><b>{it.course_id}</b> → <b>{it.skill_id}</b></div>
            <div style={{ color:"#666", fontSize: 13 }}>status={it.status}, intended_level={it.intended_level ?? "null"}, evidence_type={it.evidence_type ?? "null"}</div>
            <div style={{ marginTop: 8, display:"flex", gap: 10, alignItems:"center", flexWrap:"wrap" }}>
              <input
                placeholder="review note (optional)"
                value={noteById[it.map_id] || ""}
                onChange={(e)=>setNoteById({...noteById, [it.map_id]: e.target.value})}
                style={{ padding:8, border:"1px solid #ccc", borderRadius:6, minWidth: 420 }}
              />
              <button onClick={()=>act(it.map_id, "approve")} style={{ padding:"6px 12px", cursor:"pointer" }}>Approve</button>
              <button onClick={()=>act(it.map_id, "reject")} style={{ padding:"6px 12px", cursor:"pointer" }}>Reject</button>
            </div>
          </div>
        ))}
        {items.length===0 && <div style={{ color:"#666" }}>No items.</div>}
      </div>
    </main>
  );
}
