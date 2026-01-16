"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

function pillStyle(kind: "good" | "bad" | "neutral") {
  if (kind === "good") return { background: "#e7f6ec", color: "#146c2e", border: "1px solid #b7e0c2" };
  if (kind === "bad") return { background: "#ffecec", color: "#b42318", border: "1px solid #f5c2c2" };
  return { background: "#f2f2f2", color: "#555", border: "1px solid #ddd" };
}

function Pill({ text, kind }: { text: string; kind: "good" | "bad" | "neutral" }) {
  return (
    <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 999, fontSize: 12, fontWeight: 800, ...pillStyle(kind) }}>
      {text}
    </span>
  );
}

function Chip({ text }: { text: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 10px",
        borderRadius: 999,
        fontSize: 12,
        border: "1px solid #e5e5e5",
        background: "#fafafa",
      }}
    >
      {text}
    </span>
  );
}

export default function DocPage() {
  const params = useParams<{ docId: string }>();
  const docId = params?.docId;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  // Dev identity
  const [subjectId, setSubjectId] = useState<string>("staff_demo");
  const [role, setRole] = useState<string>("staff");
  const headers = { "X-Subject-Id": subjectId, "X-Role": role };

  const [chunks, setChunks] = useState<any[]>([]);
  const [chunksErr, setChunksErr] = useState<string>("");
  const [highlightChunkId, setHighlightChunkId] = useState<string>("");

  const [skills, setSkills] = useState<any[]>([]);
  const [skillId, setSkillId] = useState<string>("");

  const [roles, setRoles] = useState<any[]>([]);
  const [roleId, setRoleId] = useState<string>("");

  // Decision 2
  const [assessRes, setAssessRes] = useState<any>(null);
  const [assessErr, setAssessErr] = useState<string>("");
  const [assessing, setAssessing] = useState<boolean>(false);

  // Decision 3 (rule-based)
  const [profRes, setProfRes] = useState<any>(null);
  const [profErr, setProfErr] = useState<string>("");
  const [profing, setProfing] = useState<boolean>(false);

  // AI Proficiency
  const [aiProfRes, setAiProfRes] = useState<any>(null);
  const [aiProfErr, setAiProfErr] = useState<string>("");
  const [aiProfing, setAiProfing] = useState<boolean>(false);

  // AI Demonstration
  const [aiDemoRes, setAiDemoRes] = useState<any>(null);
  const [aiDemoErr, setAiDemoErr] = useState<string>("");
  const [aiDemoing, setAiDemoing] = useState<boolean>(false);

  // Decision 4/5
  const [readiness, setReadiness] = useState<any>(null);
  const [readinessErr, setReadinessErr] = useState<string>("");
  const [reading, setReading] = useState<boolean>(false);

  const [plan, setPlan] = useState<any>(null);
  const [planErr, setPlanErr] = useState<string>("");
  const [planning, setPlanning] = useState<boolean>(false);

  const chunksRef = useRef<HTMLDivElement | null>(null);

  const skillNameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of skills) m[s.skill_id] = s.canonical_name || s.skill_id;
    return m;
  }, [skills]);

  function skillLabel(id: string) {
    return skillNameById[id] || id;
  }

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        return true;
      } catch {
        return false;
      }
    }
  }

  function jumpToChunk(chunkId: string) {
    setHighlightChunkId(chunkId);
    chunksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    // also try to scroll to the specific chunk card
    setTimeout(() => {
      const el = document.getElementById(`chunk-${chunkId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 250);
  }

  useEffect(() => {
    try {
      const sid = localStorage.getItem("skillsight_subject_id");
      const r = localStorage.getItem("skillsight_role");
      if (sid) setSubjectId(sid);
      if (r) setRole(r);
    } catch {}
  }, []);

  useEffect(() => {
    fetch(`${apiBase}/skills`)
      .then((r) => r.json())
      .then((d) => {
        const items = d.items || [];
        setSkills(items);
        if (!skillId && items[0]) setSkillId(items[0].skill_id);
      })
      .catch(() => {});

    fetch(`${apiBase}/roles`)
      .then((r) => r.json())
      .then((d) => {
        const items = d.items || [];
        setRoles(items);
        if (!roleId && items[0]) setRoleId(items[0].role_id);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!docId) return;
    setChunksErr("");
    fetch(`${apiBase}/documents/${docId}/chunks?limit=200`, { headers })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        setChunks(data.items || []);
      })
      .catch((e: any) => setChunksErr(String(e.message || e)));
  }, [docId, subjectId, role]);

  async function runDecision2() {
    setAssessErr(""); setAssessRes(null);
    if (!docId || !skillId) return;
    setAssessing(true);
    try {
      const r = await fetch(`${apiBase}/assess/skill`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ skill_id: skillId, doc_id: docId, k: 5, store: false }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setAssessRes(data);
    } catch (e: any) {
      setAssessErr(String(e.message || e));
    } finally {
      setAssessing(false);
    }
  }

  async function runDecision3() {
    setProfErr(""); setProfRes(null);
    if (!docId || !skillId) return;
    setProfing(true);
    try {
      const r = await fetch(`${apiBase}/assess/proficiency`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ skill_id: skillId, doc_id: docId, k: 10, store: false }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setProfRes(data);
    } catch (e: any) {
      setProfErr(String(e.message || e));
    } finally {
      setProfing(false);
    }
  }

  async function runAIProficiency() {
    setAiProfErr(""); setAiProfRes(null);
    if (!docId || !skillId) return;
    setAiProfing(true);
    try {
      const r = await fetch(`${apiBase}/ai/proficiency`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ skill_id: skillId, doc_id: docId, k: 5, min_score: 0.2 }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setAiProfRes(data);
    } catch (e: any) {
      setAiProfErr(String(e.message || e));
    } finally {
      setAiProfing(false);
    }
  }

  async function runAIDemonstration() {
    setAiDemoErr(""); setAiDemoRes(null);
    if (!docId || !skillId) return;
    setAiDemoing(true);
    try {
      const r = await fetch(`${apiBase}/ai/demonstration`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ skill_id: skillId, doc_id: docId, k: 5, min_score: 0.2 }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setAiDemoRes(data);
    } catch (e: any) {
      setAiDemoErr(String(e.message || e));
    } finally {
      setAiDemoing(false);
    }
  }

  async function runReadiness() {
    setReadinessErr(""); setReadiness(null);
    if (!docId || !roleId) return;
    setReading(true);
    try {
      const r = await fetch(`${apiBase}/assess/role_readiness`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ doc_id: docId, role_id: roleId, store: false }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setReadiness(data);
    } catch (e: any) {
      setReadinessErr(String(e.message || e));
    } finally {
      setReading(false);
    }
  }

  async function runPlan() {
    setPlanErr(""); setPlan(null);
    if (!docId || !roleId) return;
    setPlanning(true);
    try {
      const r = await fetch(`${apiBase}/actions/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ doc_id: docId, role_id: roleId }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setPlan(data);
    } catch (e: any) {
      setPlanErr(String(e.message || e));
    } finally {
      setPlanning(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 1100 }}>
      <div style={{ marginBottom: 14 }}>
        <Link href="/" style={{ textDecoration: "underline" }}>← Back</Link>
      </div>

      <h1 style={{ fontSize: 22, marginBottom: 6 }}>Document view</h1>
      <div style={{ color: "#666", marginBottom: 16 }}>doc_id: {docId}</div>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ fontWeight: 800, marginBottom: 8 }}>Dev identity</div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, color: "#666" }}>subject_id</label>
          <input value={subjectId} onChange={(e)=>{setSubjectId(e.target.value); try{localStorage.setItem("skillsight_subject_id", e.target.value)}catch{}}}
            style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 220 }} />
          <label style={{ fontSize: 13, color: "#666" }}>role</label>
          <select value={role} onChange={(e)=>{setRole(e.target.value); try{localStorage.setItem("skillsight_role", e.target.value)}catch{}}}
            style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 140 }}>
            <option value="staff">staff</option>
            <option value="admin">admin</option>
            <option value="student">student</option>
          </select>
        </div>
      </section>

      <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 16, marginBottom: 18 }}>
        <h2 style={{ fontSize: 16, marginBottom: 10 }}>Skill assessment</h2>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <select value={skillId} onChange={(e)=>setSkillId(e.target.value)} style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 520 }}>
            {skills.map((x:any)=>(
              <option key={x.skill_id} value={x.skill_id}>
                {x.canonical_name} ({x.skill_id})
              </option>
            ))}
          </select>

          <button onClick={runDecision2} disabled={assessing} style={{ padding:"8px 14px", cursor:"pointer" }}>{assessing?"Running...":"Decision 2"}</button>
          <button onClick={runDecision3} disabled={profing} style={{ padding:"8px 14px", cursor:"pointer" }}>{profing?"Running...":"Decision 3"}</button>
          <button onClick={runAIProficiency} disabled={aiProfing} style={{ padding:"8px 14px", cursor:"pointer" }}>{aiProfing?"Running...":"AI Proficiency"}</button>
          <button onClick={runAIDemonstration} disabled={aiDemoing} style={{ padding:"8px 14px", cursor:"pointer" }}>{aiDemoing?"Running...":"AI Demonstration"}</button>
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 12 }}>
          <div style={{ border:"1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 8, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span>Decision 2</span>
              {assessRes?.decision && <Pill text={assessRes.decision} kind={assessRes.decision==="not_enough_information" ? "bad" : "good"} />}
            </div>
            {assessErr && <div style={{ color:"crimson" }}>{assessErr}</div>}
            {!assessErr && !assessRes && <div style={{ color:"#666" }}>Run Decision 2.</div>}
            {assessRes && (
              <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                <div><b>Skill:</b> {skillLabel(skillId)} <span style={{ color:"#999" }}>[{skillId}]</span></div>
                <div><b>Matched terms:</b> {(assessRes.matched_terms || []).join(", ") || "—"}</div>
                {assessRes.best_evidence?.chunk_id && (
                  <div style={{ marginTop: 8 }}>
                    <b>Best evidence:</b>{" "}
                    <a onClick={()=>jumpToChunk(assessRes.best_evidence.chunk_id)} style={{ cursor:"pointer", textDecoration:"underline" }}>
                      open chunk
                    </a>
                    <div style={{ marginTop: 6, color:"#555" }}>{assessRes.best_evidence.snippet || "—"}</div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div style={{ border:"1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 8, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span>Decision 3 (rule)</span>
              {typeof profRes?.level === "number" && <Pill text={`L${profRes.level} ${profRes.label}`} kind={profRes.level>=2 ? "good" : "neutral"} />}
            </div>
            {profErr && <div style={{ color:"crimson" }}>{profErr}</div>}
            {!profErr && !profRes && <div style={{ color:"#666" }}>Run Decision 3.</div>}
            {profRes && (
              <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                <div><b>Rationale:</b> {profRes.rationale}</div>
                {profRes.best_evidence?.chunk_id && (
                  <div style={{ marginTop: 8 }}>
                    <b>Best evidence:</b>{" "}
                    <a onClick={()=>jumpToChunk(profRes.best_evidence.chunk_id)} style={{ cursor:"pointer", textDecoration:"underline" }}>
                      open chunk
                    </a>
                    <div style={{ marginTop: 6, color:"#555" }}>{profRes.best_evidence.snippet || "—"}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div style={{ marginTop: 12, border:"1px solid #eee", borderRadius: 12, padding: 12 }}>
          <div style={{ fontWeight: 900, marginBottom: 8, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <span>AI Proficiency (Rubric v1)</span>
            {typeof aiProfRes?.level === "number" && <Pill text={`L${aiProfRes.level} ${aiProfRes.label}`} kind={aiProfRes.level>=2 ? "good" : "neutral"} />}
          </div>
          {aiProfErr && <div style={{ color:"crimson" }}>{aiProfErr}</div>}
          {!aiProfErr && !aiProfRes && <div style={{ color:"#666" }}>Run AI Proficiency.</div>}
          {aiProfRes && (
            <div style={{ fontSize: 13, lineHeight: 1.7 }}>
              <div style={{ display:"flex", gap: 8, flexWrap:"wrap", marginBottom: 8 }}>
                {(aiProfRes.matched_criteria || []).map((c:string)=> <Chip key={c} text={c} />)}
              </div>
              <div><b>Why:</b> {aiProfRes.why}</div>
              <div style={{ marginTop: 8 }}>
                <b>Evidence:</b>{" "}
                {(aiProfRes.evidence_chunk_ids || []).slice(0,8).map((cid:string)=>(
                  <a key={cid} onClick={()=>jumpToChunk(cid)} style={{ cursor:"pointer", textDecoration:"underline", marginRight: 10 }}>
                    {cid.slice(0,8)}…
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>

        <div style={{ marginTop: 12, border:"1px solid #eee", borderRadius: 12, padding: 12 }}>
          <div style={{ fontWeight: 900, marginBottom: 8, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <span>AI Demonstration (LLM)</span>
            {aiDemoRes?.label && <Pill text={aiDemoRes.label} kind={aiDemoRes.label==="not_enough_information" ? "bad" : "good"} />}
          </div>
          {aiDemoErr && <div style={{ color:"crimson" }}>{aiDemoErr}</div>}
          {!aiDemoErr && !aiDemoRes && <div style={{ color:"#666" }}>Run AI Demonstration.</div>}
          {aiDemoRes && (
            <div style={{ fontSize: 13, lineHeight: 1.7 }}>
              <div><b>Rationale:</b> {aiDemoRes.rationale}</div>
              <div style={{ marginTop: 8 }}>
                <b>Evidence:</b>{" "}
                {(aiDemoRes.evidence_chunk_ids || []).slice(0,8).map((cid:string)=>(
                  <a key={cid} onClick={()=>jumpToChunk(cid)} style={{ cursor:"pointer", textDecoration:"underline", marginRight: 10 }}>
                    {cid.slice(0,8)}…
                  </a>
                ))}
              </div>
              {aiDemoRes.refusal_reason && (
                <div style={{ marginTop: 8, color:"#666" }}>
                  <b>Refusal reason:</b> {String(aiDemoRes.refusal_reason)}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      <section style={{ border:"1px solid #ddd", borderRadius: 10, padding: 16, marginBottom: 18 }}>
        <h2 style={{ fontSize: 16, marginBottom: 10 }}>Role readiness + actions</h2>

        <div style={{ display:"flex", gap: 10, flexWrap:"wrap", alignItems:"center", marginBottom: 12 }}>
          <select value={roleId} onChange={(e)=>setRoleId(e.target.value)} style={{ padding:8, border:"1px solid #ccc", borderRadius:6, minWidth: 680 }}>
            {roles.map((x:any)=>(
              <option key={x.role_id} value={x.role_id}>
                {x.role_title} ({x.role_id})
              </option>
            ))}
          </select>

          <button onClick={runReadiness} disabled={reading} style={{ padding:"8px 14px", cursor:"pointer" }}>{reading?"Running...":"Decision 4"}</button>
          <button onClick={runPlan} disabled={planning} style={{ padding:"8px 14px", cursor:"pointer" }}>{planning?"Generating...":"Decision 5"}</button>
        </div>

        {readinessErr && <div style={{ color:"crimson" }}>{readinessErr}</div>}
        {readiness && (
          <div style={{ border:"1px solid #eee", borderRadius: 12, padding: 12, marginBottom: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 6 }}>
              {readiness.role_title} <span style={{ color:"#999", fontWeight:600 }}>({readiness.role_id})</span>
            </div>
            <div style={{ color:"#666", fontSize: 13, marginBottom: 10 }}>
              summary: meet={readiness.summary?.meet ?? 0}, missing_proof={readiness.summary?.missing_proof ?? 0}, needs_strengthening={readiness.summary?.needs_strengthening ?? 0}
            </div>

            <div style={{ display:"grid", gap: 8 }}>
              {(readiness.items || []).map((it:any)=>{
                const kind = it.status==="meet" ? "good" : (it.status==="missing_proof" ? "neutral" : "bad");
                return (
                  <div key={it.skill_id} style={{ padding: 10, border:"1px solid #f0f0f0", borderRadius: 12 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", gap: 10, flexWrap:"wrap" }}>
                      <div style={{ display:"flex", gap: 10, flexWrap:"wrap", alignItems:"center" }}>
                        <span style={{ fontWeight: 800 }}>{skillLabel(it.skill_id)}</span>
                        <span style={{ color:"#999", fontSize: 12 }}>{it.skill_id}</span>
                        <Pill text={it.status} kind={kind} />
                      </div>
                      <div style={{ color:"#666", fontSize: 13 }}>
                        observed {it.observed_level} ({it.observed_label}) / target {it.target_level}{it.required ? " (required)" : " (optional)"}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {planErr && <div style={{ color:"crimson" }}>{planErr}</div>}
        {plan && (
          <div style={{ border:"1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 6 }}>Action cards (Decision 5)</div>
            {(plan.action_cards || []).length === 0 && <div style={{ color:"#666" }}>No actions needed (all meet).</div>}

            <div style={{ display:"grid", gap: 10 }}>
              {(plan.action_cards || []).map((c:any, idx:number)=>(
                <CopyActionCard key={idx} c={c} skillName={skillLabel(c.skill_id)} toText={(x:any)=>actionText(x)} onCopy={copyText} />
              ))}
            </div>
          </div>
        )}
      </section>

      <section ref={chunksRef} style={{ border:"1px solid #ddd", borderRadius: 10, padding: 16 }}>
        <h2 style={{ fontSize: 16, marginBottom: 10 }}>Chunks</h2>
        {chunksErr && <div style={{ color:"crimson" }}>{chunksErr}</div>}
        {!chunksErr && chunks.length===0 && <div style={{ color:"#666" }}>No chunks.</div>}
        {chunks.length>0 && (
          <div style={{ display:"grid", gap: 10 }}>
            {chunks.slice(0, 50).map((c:any)=>{
              const isHi = highlightChunkId && c.chunk_id === highlightChunkId;
              return (
                <div
                  id={`chunk-${c.chunk_id}`}
                  key={c.chunk_id}
                  style={{
                    border:"1px solid #eee",
                    borderRadius:12,
                    padding: 12,
                    background: isHi ? "#fff7e6" : "white",
                    outline: isHi ? "2px solid #f5b041" : "none"
                  }}
                >
                  <div style={{ color:"#666", fontSize: 12 }}>
                    chunk {c.idx} · section {c.section_path ?? "—"} · id {String(c.chunk_id).slice(0,8)}…
                  </div>
                  <div style={{ fontFamily:"ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 13, marginTop: 6 }}>
                    {c.snippet}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

function CopyActionCard({ c, skillName, toText, onCopy }: any) {
  const [copied, setCopied] = useState(false);
  const text = toText(c);

  async function doCopy() {
    const ok = await onCopy(text.replace(`[${c.skill_id}]`, `[${c.skill_id}]`));
    setCopied(ok);
    setTimeout(()=>setCopied(false), 1200);
  }

  return (
    <div style={{ padding: 12, border:"1px solid #f0f0f0", borderRadius: 14 }}>
      <div style={{ display:"flex", justifyContent:"space-between", gap: 10, flexWrap:"wrap", alignItems:"center" }}>
        <div>
          <b>{c.title}</b> <span style={{ color:"#666" }}>({c.gap_type})</span>
        </div>
        <div style={{ display:"flex", gap: 10, alignItems:"center" }}>
          <span style={{ color:"#666", fontSize: 12 }}>{skillName} <span style={{ color:"#999" }}>[{c.skill_id}]</span></span>
          <button onClick={doCopy} style={{ padding:"6px 12px", cursor:"pointer" }}>{copied ? "Copied" : "Copy"}</button>
        </div>
      </div>

      {c.why_this_card && <div style={{ marginTop: 8, fontSize: 13 }}><b>Why:</b> {c.why_this_card}</div>}
      {c.what_to_do && <div style={{ marginTop: 6, fontSize: 13 }}><b>What to do:</b> {c.what_to_do}</div>}
      {c.artifact && <div style={{ marginTop: 6, fontSize: 13 }}><b>Artifact:</b> {c.artifact}</div>}
      {c.how_verified && <div style={{ marginTop: 6, fontSize: 13 }}><b>How verified:</b> {c.how_verified}</div>}

      <textarea
        readOnly
        value={text.replace(`Skill: ${c.skill_id}`, `Skill: ${skillName} [${c.skill_id}]`)}
        style={{
          marginTop: 10,
          width: "100%",
          minHeight: 110,
          padding: 10,
          borderRadius: 12,
          border: "1px solid #e5e5e5",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: 12,
          background: "#fafafa"
        }}
      />
    </div>
  );
}
