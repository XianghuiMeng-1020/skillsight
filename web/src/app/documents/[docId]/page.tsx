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
  created_at: string;
  section_path?: string | null;
  page_start?: number | null;
  page_end?: number | null;
};

type SkillItem = {
  skill_id: string;
  canonical_name: string;
};

type RoleItem = {
  role_id: string;
  role_title: string;
};

type RoleReadiness = {
  role_id: string;
  role_title: string;
  summary: any;
  items: Array<{
    skill_id: string;
    required: boolean;
    target_level: number;
    observed_level: number;
    observed_label: string;
    status: "meet" | "missing_proof" | "needs_strengthening";
    source: string;
  }>;
};

type ActionPlan = {
  role_id: string;
  role_title: string;
  summary: any;
  action_cards: Array<{
    skill_id: string;
    gap_type: string;
    title: string;
    why_this_card?: string;
    based_on?: any;
    what_to_do: string;
    artifact: string;
    how_verified: string;
  }>;
};

type AssessResult = {
  decision: string;
  matched_terms: string[];
};

type ProfResult = {
  level: number;
  label: string;
  rationale: string;
};

type AuditItem = {
  audit_id: string;
  event_type: string;
  path: string;
  method: string;
  doc_id_text: string | null;
  status_code: number;
  created_at: string;
  payload: any;
};

type ChangeItem = {
  change_id: string;
  object_type: string;
  doc_id_text: string | null;
  key_text: string | null;
  change_summary: any;
  created_at: string;
};

export default function DocPage() {
  const params = useParams<{ docId: string }>();
  const docId = params?.docId;
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  // Dev identity (RBAC headers)
  const [subjectId, setSubjectId] = useState<string>("staff_demo");
  const [role, setRole] = useState<string>("staff");

  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [err, setErr] = useState<string>("");

  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [skillId, setSkillId] = useState<string>("");

  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [roleId, setRoleId] = useState<string>("");

  const [assessRes, setAssessRes] = useState<AssessResult | null>(null);
  const [assessErr, setAssessErr] = useState<string>("");
  const [assessing, setAssessing] = useState<boolean>(false);

  const [profRes, setProfRes] = useState<ProfResult | null>(null);
  const [profErr, setProfErr] = useState<string>("");
  const [profing, setProfing] = useState<boolean>(false);

  const [aiProfRes, setAiProfRes] = useState<any>(null);
  const [aiProfErr, setAiProfErr] = useState<string>("");
  const [aiProfing, setAiProfing] = useState<boolean>(false);

  const [aiDemoRes, setAiDemoRes] = useState<any>(null);
  const [aiDemoErr, setAiDemoErr] = useState<string>("");
  const [aiDemoing, setAiDemoing] = useState<boolean>(false);

  const [readiness, setReadiness] = useState<RoleReadiness | null>(null);
  const [readinessErr, setReadinessErr] = useState<string>("");
  const [reading, setReading] = useState<boolean>(false);

  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [planErr, setPlanErr] = useState<string>("");
  const [planning, setPlanning] = useState<boolean>(false);

  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [auditErr, setAuditErr] = useState<string>("");
  const [auditing, setAuditing] = useState<boolean>(false);

  const [changes, setChanges] = useState<ChangeItem[]>([]);
  const [changesErr, setChangesErr] = useState<string>("");
  const [changing, setChanging] = useState<boolean>(false);

  const headers = {
    "X-Subject-Id": subjectId,
    "X-Role": role,
  };

  useEffect(() => {
    try {
      const sid = localStorage.getItem("skillsight_subject_id");
      const r = localStorage.getItem("skillsight_role");
      if (sid) setSubjectId(sid);
      if (r) setRole(r);
    } catch {}
  }, []);

  async function refreshAudit() {
    if (!docId) return;
    setAuditing(true);
    setAuditErr("");
    try {
      const r = await fetch(`${apiBase}/audit?doc_id=${docId}&limit=20`, { headers });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setAudit(data.items || []);
    } catch (e: any) {
      setAuditErr(String(e.message || e));
    } finally {
      setAuditing(false);
    }
  }

  async function refreshChanges() {
    if (!docId) return;
    setChanging(true);
    setChangesErr("");
    try {
      const r = await fetch(`${apiBase}/changes?doc_id=${docId}&limit=20`, { headers });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      setChanges(data.items || []);
    } catch (e: any) {
      setChangesErr(String(e.message || e));
    } finally {
      setChanging(false);
    }
  }

  useEffect(() => {
    fetch(`${apiBase}/skills`)
      .then((r) => r.json())
      .then((data) => {
        const items: SkillItem[] = (data.items || []).map((x: any) => ({
          skill_id: x.skill_id,
          canonical_name: x.canonical_name,
        }));
        setSkills(items);
        if (!skillId && items.length > 0) setSkillId(items[0].skill_id);
      })
      .catch(() => {});

    fetch(`${apiBase}/roles`)
      .then((r) => r.json())
      .then((data) => {
        const items: RoleItem[] = (data.items || []).map((x: any) => ({
          role_id: x.role_id,
          role_title: x.role_title,
        }));
        setRoles(items);
        if (!roleId && items.length > 0) setRoleId(items[0].role_id);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!docId) return;
    setLoading(true);
    setErr("");

    fetch(`${apiBase}/documents/${docId}/chunks?limit=200`, { headers })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        setChunks(data.items || []);
      })
      .catch((e) => setErr(`Failed to load chunks: ${String(e.message || e)}`))
      .finally(() => setLoading(false));

    refreshAudit();
    refreshChanges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, docId, subjectId, role]);

  async function runDecision2() {
    setAssessErr("");
    setAssessRes(null);
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
      setAssessRes({ decision: data.decision, matched_terms: data.matched_terms || [] });
    } catch (e: any) {
      setAssessErr(String(e.message || e));
    } finally {
      setAssessing(false);
      refreshAudit();
    }
  }

  async function runDecision3() {
    setProfErr("");
    setProfRes(null);
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
      setProfRes({ level: data.level, label: data.label, rationale: data.rationale });
    } catch (e: any) {
      setProfErr(String(e.message || e));
    } finally {
      setProfing(false);
      refreshAudit();
    }
  }

  async function runAIProficiency() {
    setAiProfErr("");
    setAiProfRes(null);
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
      refreshAudit();
    }

  async function runAIDemonstration() {
    setAiDemoErr("");
    setAiDemoRes(null);
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
      refreshAudit?.();
    }
  }
  }

  async function runReadiness() {
    setReadinessErr("");
    setReadiness(null);
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
      refreshAudit();
      refreshChanges();
    }
  }

  async function runPlan() {
    setPlanErr("");
    setPlan(null);
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
      refreshAudit();
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui", maxWidth: 980 }}>
      <div style={{ marginBottom: 14 }}>
        <Link href="/" style={{ textDecoration: "underline" }}>← Back</Link>
      </div>

      <h1 style={{ fontSize: 22, marginBottom: 6 }}>Document view</h1>
      <div style={{ color: "#666", marginBottom: 16 }}>doc_id: {docId}</div>

      {/* Dev identity */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Dev identity</div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, color: "#666" }}>subject_id</label>
          <input
            value={subjectId}
            onChange={(e) => {
              const v = e.target.value;
              setSubjectId(v);
              try { localStorage.setItem("skillsight_subject_id", v); } catch {}
            }}
            style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 220 }}
          />
          <label style={{ fontSize: 13, color: "#666" }}>role</label>
          <select
            value={role}
            onChange={(e) => {
              const v = e.target.value;
              setRole(v);
              try { localStorage.setItem("skillsight_role", v); } catch {}
            }}
            style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 140 }}
          >
            <option value="student">student</option>
            <option value="staff">staff</option>
            <option value="admin">admin</option>
          </select>
        </div>
      </section>

      {/* Skill assessment */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 18 }}>
        <h2 style={{ fontSize: 16, marginBottom: 10 }}>Skill assessment</h2>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <select value={skillId} onChange={(e) => setSkillId(e.target.value)} style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 320 }}>
            {skills.length === 0 && <option>Loading skills...</option>}
            {skills.map((s) => (
              <option key={s.skill_id} value={s.skill_id}>
                {s.canonical_name} ({s.skill_id})
              </option>
            ))}
          </select>

          <button onClick={runDecision2} disabled={assessing} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {assessing ? "Running..." : "Decision 2"}
          </button>

          <button onClick={runDecision3} disabled={profing} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {profing ? "Running..." : "Decision 3"}
          </button>

          <button onClick={runAIProficiency} disabled={aiProfing} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {aiProfing ? "Running..." : "AI Proficiency (Rubric v1)"}
          </button>

          <button onClick={runAIDemonstration} disabled={aiDemoing} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {aiDemoing ? "Running..." : "AI Demonstration (LLM)"}
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Decision 2</div>
            {assessErr && <div style={{ color: "crimson" }}>{assessErr}</div>}
            {!assessErr && !assessRes && <div style={{ color: "#666" }}>Click Decision 2.</div>}
            {assessRes && (
              <>
                <div><b>decision:</b> {assessRes.decision}</div>
                <div style={{ marginTop: 6 }}><b>matched_terms:</b> {assessRes.matched_terms?.join(", ") || "(none)"}</div>
              </>
            )}
          </div>

          <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Decision 3</div>
            {profErr && <div style={{ color: "crimson" }}>{profErr}</div>}
            {!profErr && !profRes && <div style={{ color: "#666" }}>Click Decision 3.</div>}
            {profRes && (
              <>
                <div><b>level:</b> {profRes.level} ({profRes.label})</div>
                <div style={{ marginTop: 6, fontSize: 13, color: "#333" }}><b>rationale:</b> {profRes.rationale}</div>
              </>
            )}
          </div>
        </div>

        <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>AI Proficiency result (Rubric v1)</div>
          {aiProfErr && <div style={{ color: "crimson" }}>{aiProfErr}</div>}
          {!aiProfErr && !aiProfRes && <div style={{ color: "#666" }}>Click AI Proficiency (Rubric v1).</div>}
          {aiProfRes && (
            <>
              <div><b>level:</b> {aiProfRes.level} ({aiProfRes.label})</div>
              <div style={{ marginTop: 6, fontSize: 13 }}><b>matched_criteria:</b> {(aiProfRes.matched_criteria || []).join(", ")}</div>
              <div style={{ marginTop: 6, fontSize: 13 }}><b>evidence_chunk_ids:</b> {(aiProfRes.evidence_chunk_ids || []).join(", ")}</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "#333" }}><b>why:</b> {aiProfRes.why}</div>
            </>
          )}
        </div>
      
        <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>AI Demonstration result (LLM)</div>
          {aiDemoErr && <div style={{ color: "crimson" }}>{aiDemoErr}</div>}
          {!aiDemoErr && !aiDemoRes && <div style={{ color: "#666" }}>Click AI Demonstration (LLM).</div>}
          {aiDemoRes && (
            <>
              <div><b>label:</b> {aiDemoRes.label}</div>
              <div style={{ marginTop: 6, fontSize: 13 }}><b>evidence_chunk_ids:</b> {(aiDemoRes.evidence_chunk_ids || []).join(", ")}</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "#333" }}><b>rationale:</b> {aiDemoRes.rationale}</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "#666" }}><b>refusal_reason:</b> {String(aiDemoRes.refusal_reason)}</div>
            </>
          )}
        </div>

</section>

      {/* Role readiness + actions */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 18 }}>
        <h2 style={{ fontSize: 16, marginBottom: 10 }}>Role readiness + actions</h2>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <select value={roleId} onChange={(e) => setRoleId(e.target.value)} style={{ padding: 8, border: "1px solid #ccc", borderRadius: 6, minWidth: 360 }}>
            {roles.length === 0 && <option>Loading roles...</option>}
            {roles.map((r) => (
              <option key={r.role_id} value={r.role_id}>
                {r.role_title} ({r.role_id})
              </option>
            ))}
          </select>

          <button onClick={runReadiness} disabled={reading} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {reading ? "Running..." : "Decision 4: Readiness"}
          </button>

          <button onClick={runPlan} disabled={planning} style={{ padding: "8px 14px", cursor: "pointer" }}>
            {planning ? "Generating..." : "Decision 5: Actions"}
          </button>
        </div>

        {readinessErr && <div style={{ color: "crimson" }}>{readinessErr}</div>}
        {readiness && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ color: "#666", fontSize: 13 }}>
              summary: meet={readiness.summary.meet}, missing={readiness.summary.missing_proof}, needs={readiness.summary.needs_strengthening}
            </div>
            <ul style={{ marginTop: 10 }}>
              {readiness.items.map((it) => (
                <li key={it.skill_id} style={{ marginBottom: 8 }}>
                  <b>{it.skill_id}</b> — status: <b>{it.status}</b> — observed {it.observed_level} ({it.observed_label}) / target {it.target_level}
                </li>
              ))}
            </ul>
          </div>
        )}

        {planErr && <div style={{ color: "crimson" }}>{planErr}</div>}
        {plan && (
          <div>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Action cards</div>
            {plan.action_cards.length === 0 && <div style={{ color: "#666" }}>No actions needed (all meet).</div>}
            {plan.action_cards.length > 0 && (
              <ul>
                {plan.action_cards.map((c, idx) => (
                  <li key={idx} style={{ marginBottom: 12, padding: 12, border: "1px solid #eee", borderRadius: 8 }}>
                    <div><b>{c.title}</b> <span style={{ color: "#666" }}>({c.gap_type})</span></div>
                    {c.why_this_card && (
                      <div style={{ marginTop: 6, fontSize: 13, color: "#444" }}>
                        <b>why:</b> {c.why_this_card}
                      </div>
                    )}
                    {c.based_on && (
                      <div style={{ marginTop: 6, fontSize: 13, color: "#666" }}>
                        <b>based_on:</b> observed {c.based_on.observed_level} ({c.based_on.observed_label}) / target {c.based_on.target_level} — status {c.based_on.status}
                      </div>
                    )}
                    <div style={{ marginTop: 6, fontSize: 13 }}><b>what_to_do:</b> {c.what_to_do}</div>
                    <div style={{ marginTop: 6, fontSize: 13 }}><b>artifact:</b> {c.artifact}</div>
                    <div style={{ marginTop: 6, fontSize: 13 }}><b>how_verified:</b> {c.how_verified}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* Chunks */}
      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
        <h2 style={{ fontSize: 18, marginBottom: 12 }}>Chunks</h2>
        {loading && <p style={{ color: "#666" }}>Loading...</p>}
        {!loading && err && <p style={{ color: "crimson" }}>{err}</p>}
        {!loading && !err && chunks.length === 0 && <p style={{ color: "#666" }}>No chunks found for this document.</p>}
        {!loading && !err && chunks.length > 0 && (
          <ul style={{ marginTop: 12 }}>
            {chunks.map((c) => (
              <li key={c.chunk_id} style={{ marginBottom: 14, padding: 12, border: "1px solid #eee", borderRadius: 8 }}>
                <div style={{ marginBottom: 6 }}>
                  <b>Chunk {c.idx}</b> | char [{c.char_start}, {c.char_end}]
                </div>
                {c.section_path && (
                  <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
                    section: {c.section_path}
                  </div>
                )}
                {c.page_start && (
                  <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
                    pages: {c.page_start}-{c.page_end}
                  </div>
                )}
                <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 13 }}>
                  {c.snippet}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
