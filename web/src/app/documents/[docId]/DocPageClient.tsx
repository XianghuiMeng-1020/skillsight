"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useLanguage, getDateLocale } from "@/lib/contexts";
import { getToken } from "@/lib/bffClient";
import { logger } from "@/lib/logger";

// 文档信息接口
interface DocInfo {
  doc_id: string;
  filename: string;
  created_at: string;
  doc_type: string;
  user_id: string;
}

// Chunk接口
interface Chunk {
  chunk_id: string;
  idx: number;
  section_path?: string;
  snippet: string;
  chunk_text?: string;
  page_start?: number;
  page_end?: number;
}

// 评估结果接口
interface AssessResult {
  decision?: string;
  matched_terms?: string[];
  best_evidence?: { chunk_id: string; snippet: string };
}

interface ProfResult {
  level?: number;
  label?: string;
  rationale?: string;
  best_evidence?: { chunk_id: string; snippet: string };
}

interface AIProfResult {
  level?: number;
  label?: string;
  matched_criteria?: string[];
  why?: string;
  evidence_chunk_ids?: string[];
}

interface AIDemoResult {
  label?: string;
  rationale?: string;
  evidence_chunk_ids?: string[];
  refusal_reason?: string;
}

// 工具函数：获取文件图标
function getFileIcon(filename: string) {
  const ext = filename?.split('.').pop()?.toLowerCase() || '';
  const icons: Record<string, string> = {
    pdf: '📕', docx: '📘', doc: '📘', txt: '📄', rtf: '📄', md: '📝',
    xlsx: '📊', xls: '📊', csv: '📊', pptx: '📽️', ppt: '📽️',
    jpg: '🖼️', jpeg: '🖼️', png: '🖼️', webp: '🖼️', gif: '🖼️', svg: '🖼️',
    mp4: '🎬', webm: '🎬', mov: '🎬', avi: '🎬',
    mp3: '🎵', wav: '🎵', m4a: '🎵',
    py: '🐍', ipynb: '📓', js: '💛', ts: '💙', java: '☕',
    cpp: '⚙️', c: '⚙️', go: '🔷', rs: '🦀',
    json: '📋', yaml: '📋', html: '🌐', css: '🎨',
  };
  return icons[ext] || '📄';
}

// 状态指示组件
function StatusPill({ text, kind }: { text: string; kind: "success" | "warning" | "error" | "neutral" }) {
  const styles: Record<string, React.CSSProperties> = {
    success: { background: "var(--sage-light)", color: "#146c2e", border: "1px solid var(--sage)" },
    warning: { background: "#fff8e6", color: "#8a6d00", border: "1px solid #f5d66e" },
    error: { background: "#ffecec", color: "#b42318", border: "1px solid #f5c2c2" },
    neutral: { background: "var(--gray-100)", color: "var(--gray-600)", border: "1px solid var(--gray-200)" },
  };
  return (
    <span style={{ 
      display: "inline-flex", 
      alignItems: "center",
      padding: "4px 12px", 
      borderRadius: 999, 
      fontSize: 12, 
      fontWeight: 600,
      ...styles[kind] 
    }}>
      {text}
    </span>
  );
}

// 标签组件
function Tag({ text }: { text: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "4px 10px",
      borderRadius: 8,
      fontSize: 12,
      border: "1px solid var(--gray-200)",
      background: "var(--gray-50)",
      color: "var(--gray-600)",
    }}>
      {text}
    </span>
  );
}

// 加载骨架屏
function Skeleton({ width = "100%", height = "1rem" }: { width?: string; height?: string }) {
  return (
    <div style={{
      width,
      height,
      background: "linear-gradient(90deg, var(--gray-100) 25%, var(--gray-50) 50%, var(--gray-100) 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.5s infinite",
      borderRadius: 6,
    }} />
  );
}

// 卡片组件
function Card({ title, icon, children, actions }: { 
  title: string; 
  icon?: string; 
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="card-header" style={{ 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center",
        borderBottom: "1px solid var(--gray-100)",
        padding: "1rem 1.25rem"
      }}>
        <h3 style={{ 
          fontSize: "1rem", 
          fontWeight: 600, 
          display: "flex", 
          alignItems: "center", 
          gap: "0.5rem",
          margin: 0
        }}>
          {icon && <span>{icon}</span>}
          {title}
        </h3>
        {actions}
      </div>
      <div className="card-content" style={{ padding: "1.25rem" }}>
        {children}
      </div>
    </div>
  );
}

export default function DocPage() {
  const { t, language } = useLanguage();
  const locale = getDateLocale(language);
  const params = useParams<{ docId: string }>();
  const docId = params?.docId;
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

  const authHeaders = useMemo(() => {
    const token = getToken();
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  }, []);

  // 文档信息
  const [docInfo, setDocInfo] = useState<DocInfo | null>(null);
  const [docLoading, setDocLoading] = useState(true);

  // Chunks
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [chunksErr, setChunksErr] = useState<string>("");
  const [chunksLoading, setChunksLoading] = useState(true);
  const [highlightChunkId, setHighlightChunkId] = useState<string>("");
  const [expandedChunk, setExpandedChunk] = useState<string | null>(null);

  // Skills & Roles
  const [skills, setSkills] = useState<any[]>([]);
  const [skillId, setSkillId] = useState<string>("");
  const [roles, setRoles] = useState<any[]>([]);
  const [roleId, setRoleId] = useState<string>("");
  const [metaLoadErr, setMetaLoadErr] = useState<string>("");

  // 评估状态
  const [assessRes, setAssessRes] = useState<AssessResult | null>(null);
  const [assessErr, setAssessErr] = useState<string>("");
  const [assessing, setAssessing] = useState(false);

  const [profRes, setProfRes] = useState<ProfResult | null>(null);
  const [profErr, setProfErr] = useState<string>("");
  const [profing, setProfing] = useState(false);

  const [aiProfRes, setAiProfRes] = useState<AIProfResult | null>(null);
  const [aiProfErr, setAiProfErr] = useState<string>("");
  const [aiProfing, setAiProfing] = useState(false);

  const [aiDemoRes, setAiDemoRes] = useState<AIDemoResult | null>(null);
  const [aiDemoErr, setAiDemoErr] = useState<string>("");
  const [aiDemoing, setAiDemoing] = useState(false);

  // 角色就绪度
  const [readiness, setReadiness] = useState<any>(null);
  const [readinessErr, setReadinessErr] = useState<string>("");
  const [reading, setReading] = useState(false);

  const [plan, setPlan] = useState<any>(null);
  const [planErr, setPlanErr] = useState<string>("");
  const [planning, setPlanning] = useState(false);

  const chunksRef = useRef<HTMLDivElement | null>(null);

  const skillNameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of skills) m[s.skill_id] = s.canonical_name || s.skill_id;
    return m;
  }, [skills]);

  function skillLabel(id: string) {
    return skillNameById[id] || id;
  }

  function jumpToChunk(chunkId: string) {
    setHighlightChunkId(chunkId);
    setExpandedChunk(chunkId);
    chunksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => {
      const el = document.getElementById(`chunk-${chunkId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 250);
  }

  // 获取文档信息
  useEffect(() => {
    if (!docId) return;
    setDocLoading(true);
    fetch(`${apiBase}/documents/${docId}`, { headers: authHeaders })
      .then(async (r) => {
        if (!r.ok) throw new Error(t("doc.notFound"));
        return r.json();
      })
      .then((data) => setDocInfo(data))
      .catch(() => setDocInfo(null))
      .finally(() => setDocLoading(false));
  }, [docId, apiBase, authHeaders]);

  // 获取 Skills 和 Roles
  useEffect(() => {
    setMetaLoadErr("");
    fetch(`${apiBase}/skills`, { headers: authHeaders })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => {
        const items = d.items || [];
        setSkills(items);
        if (!skillId && items[0]) setSkillId(items[0].skill_id);
      })
      .catch((e) => {
        logger.error("Failed to load skills", e);
        setSkills([]);
        setMetaLoadErr("Failed to load skills/roles metadata");
      });

    fetch(`${apiBase}/roles`, { headers: authHeaders })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => {
        const items = d.items || [];
        setRoles(items);
        if (!roleId && items[0]) setRoleId(items[0].role_id);
      })
      .catch((e) => {
        logger.error("Failed to load roles", e);
        setRoles([]);
        setMetaLoadErr("Failed to load skills/roles metadata");
      });
  }, [apiBase, authHeaders]);

  // 获取 Chunks
  useEffect(() => {
    if (!docId) return;
    setChunksErr("");
    setChunksLoading(true);
    fetch(`${apiBase}/documents/${docId}/chunks?limit=200`, { headers: authHeaders })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
        setChunks(data.items || []);
      })
      .catch((e: any) => setChunksErr(String(e.message || e)))
      .finally(() => setChunksLoading(false));
  }, [docId, apiBase, authHeaders]);

  // 评估函数
  async function runSkillMatch() {
    setAssessErr(""); setAssessRes(null);
    if (!docId || !skillId) return;
    setAssessing(true);
    try {
      const r = await fetch(`${apiBase}/assess/skill`, {
        method: "POST",
        headers: authHeaders,
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

  async function runProficiency() {
    setProfErr(""); setProfRes(null);
    if (!docId || !skillId) return;
    setProfing(true);
    try {
      const r = await fetch(`${apiBase}/assess/proficiency`, {
        method: "POST",
        headers: authHeaders,
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
        headers: authHeaders,
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
        headers: authHeaders,
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
        headers: authHeaders,
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
        headers: authHeaders,
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
    <div className="page">
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <Link href="/" className="logo">
            <span>🎓</span>
            <span>SkillSight</span>
          </Link>
          <nav className="nav">
            <Link href="/" className="nav-link">{t("nav.home")}</Link>
            <Link href="/upload" className="nav-link">{t("nav.upload")}</Link>
            <Link href="/assess" className="nav-link">{t("nav.assess")}</Link>
            <Link href="/dashboard" className="nav-link">{t("doc.dashboard")}</Link>
          </nav>
        </div>
      </header>

      <main className="main" style={{ paddingTop: "2rem", paddingBottom: "3rem" }}>
        <div className="container" style={{ maxWidth: "1100px" }}>
          {/* 面包屑导航 */}
          <nav style={{ 
            display: "flex", 
            alignItems: "center", 
            gap: "0.5rem", 
            marginBottom: "1.5rem",
            fontSize: "0.875rem",
            color: "var(--gray-500)"
          }}>
            <Link href="/dashboard" style={{ color: "var(--primary)", textDecoration: "none" }}>
              {t("doc.dashboard")}
            </Link>
            <span>/</span>
            <Link href="/upload" style={{ color: "var(--primary)", textDecoration: "none" }}>
              {t("doc.document")}
            </Link>
            <span>/</span>
            <span style={{ color: "var(--gray-700)" }}>
              {docLoading ? t("common.loading") : (docInfo?.filename || t("doc.details"))}
            </span>
          </nav>

          <Card title={t("doc.info")} icon="📄">
            {docLoading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <Skeleton width="60%" height="1.5rem" />
                <Skeleton width="40%" />
                <Skeleton width="30%" />
              </div>
            ) : docInfo ? (
              <div style={{ display: "flex", alignItems: "flex-start", gap: "1.25rem" }}>
                <div style={{ 
                  fontSize: "3rem",
                  width: "80px",
                  height: "80px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: "var(--gray-50)",
                  borderRadius: "16px"
                }}>
                  {getFileIcon(docInfo.filename)}
                </div>
                <div style={{ flex: 1 }}>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                    {docInfo.filename}
                  </h2>
                  <div style={{ 
                    display: "flex", 
                    flexWrap: "wrap", 
                    gap: "1rem", 
                    fontSize: "0.875rem", 
                    color: "var(--gray-600)" 
                  }}>
                    <span>ID: <code style={{ 
                      background: "var(--gray-100)", 
                      padding: "2px 6px", 
                      borderRadius: 4,
                      fontSize: "0.75rem"
                    }}>{docInfo.doc_id.slice(0, 8)}...</code></span>
                    <span>{t("doc.type")} {docInfo.doc_type?.toUpperCase() || t("common.unknown")}</span>
                    <span>{t("doc.uploadTime")} {new Date(docInfo.created_at).toLocaleString(locale)}</span>
                  </div>
                </div>
                <StatusPill text={t("doc.processed")} kind="success" />
              </div>
            ) : (
              <div style={{ color: "var(--gray-500)", textAlign: "center", padding: "2rem" }}>
                {t("doc.notFound")}
              </div>
            )}
          </Card>

          {/* 技能评估区域 */}
          <Card 
            title={t("doc.skillAssess")} 
            icon="🎯"
            actions={
              <div style={{ fontSize: "0.75rem", color: "var(--gray-500)" }}>
                {t("doc.selectSkill")}
              </div>
            }
          >
            {metaLoadErr && (
              <div className="alert alert-error" style={{ marginBottom: "1rem" }}>
                <span>⚠</span>
                <div style={{ fontSize: "0.875rem" }}>{metaLoadErr}</div>
              </div>
            )}
            <div style={{ marginBottom: "1.25rem" }}>
              <label style={{ 
                display: "block", 
                fontSize: "0.875rem", 
                fontWeight: 500, 
                marginBottom: "0.5rem",
                color: "var(--gray-700)"
              }}>
                {t("doc.selectSkillLabel")}
              </label>
              <select 
                value={skillId} 
                onChange={(e) => setSkillId(e.target.value)} 
                className="input"
                style={{ width: "100%", maxWidth: "500px" }}
              >
                {skills.map((x: any) => (
                  <option key={x.skill_id} value={x.skill_id}>
                    {x.canonical_name}
                  </option>
                ))}
              </select>
            </div>

            {/* 评估按钮组 */}
            <div style={{ 
              display: "grid", 
              gridTemplateColumns: "repeat(4, 1fr)", 
              gap: "0.75rem",
              marginBottom: "1.5rem"
            }}>
              <button 
                onClick={runSkillMatch} 
                disabled={assessing}
                className="btn btn-ghost"
                style={{ 
                  display: "flex", 
                  flexDirection: "column", 
                  alignItems: "center", 
                  gap: "0.5rem",
                  padding: "1rem",
                  height: "auto"
                }}
              >
                <span style={{ fontSize: "1.5rem" }}>🔍</span>
                <span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
                  {assessing ? t("doc.analyzing") : t("doc.skillMatch")}
                </span>
                <span style={{ fontSize: "0.625rem", color: "var(--gray-500)" }}>
                  检测相关证据
                </span>
              </button>

              <button 
                onClick={runProficiency} 
                disabled={profing}
                className="btn btn-ghost"
                style={{ 
                  display: "flex", 
                  flexDirection: "column", 
                  alignItems: "center", 
                  gap: "0.5rem",
                  padding: "1rem",
                  height: "auto"
                }}
              >
                <span style={{ fontSize: "1.5rem" }}>📊</span>
                <span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
                  {profing ? t("doc.assessing") : t("doc.proficiencyAssess")}
                </span>
                <span style={{ fontSize: "0.625rem", color: "var(--gray-500)" }}>
                  规则判定等级
                </span>
              </button>

              <button 
                onClick={runAIProficiency} 
                disabled={aiProfing}
                className="btn btn-ghost"
                style={{ 
                  display: "flex", 
                  flexDirection: "column", 
                  alignItems: "center", 
                  gap: "0.5rem",
                  padding: "1rem",
                  height: "auto"
                }}
              >
                <span style={{ fontSize: "1.5rem" }}>🤖</span>
                <span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
                  {aiProfing ? t("doc.analyzing") : t("doc.aiAssess")}
                </span>
                <span style={{ fontSize: "0.625rem", color: "var(--gray-500)" }}>
                  深度分析熟练度
                </span>
              </button>

              <button 
                onClick={runAIDemonstration} 
                disabled={aiDemoing}
                className="btn btn-ghost"
                style={{ 
                  display: "flex", 
                  flexDirection: "column", 
                  alignItems: "center", 
                  gap: "0.5rem",
                  padding: "1rem",
                  height: "auto"
                }}
              >
                <span style={{ fontSize: "1.5rem" }}>✅</span>
                <span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
                  {aiDemoing ? t("doc.verifying") : t("doc.capabilityVerify")}
                </span>
                <span style={{ fontSize: "0.625rem", color: "var(--gray-500)" }}>
                  验证实际应用
                </span>
              </button>
            </div>

            {/* 评估结果展示 */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
              {/* 技能匹配结果 */}
              <div style={{ 
                padding: "1rem", 
                background: "var(--gray-50)", 
                borderRadius: "12px",
                border: assessRes ? "1px solid var(--sage)" : "1px solid var(--gray-200)"
              }}>
                <div style={{ 
                  display: "flex", 
                  justifyContent: "space-between", 
                  alignItems: "center",
                  marginBottom: "0.75rem"
                }}>
                  <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>🔍 技能匹配</span>
                  {assessRes?.decision && (
                    <StatusPill 
                      text={assessRes.decision === "not_enough_information" ? t("skills.insufficient") : t("doc.matched")} 
                      kind={assessRes.decision === "not_enough_information" ? "warning" : "success"} 
                    />
                  )}
                </div>
                {assessErr && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{assessErr}</div>}
                {!assessErr && !assessRes && (
                  <div style={{ color: "var(--gray-500)", fontSize: "0.875rem" }}>
                    {t("doc.clickToDetect")}
                  </div>
                )}
                {assessRes && (
                  <div style={{ fontSize: "0.875rem" }}>
                    <div style={{ marginBottom: "0.5rem" }}>
                      <strong>{t("doc.matchedTerms")}</strong>
                      {(assessRes.matched_terms || []).length > 0 ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", marginTop: "0.375rem" }}>
                          {assessRes.matched_terms?.map((t) => <Tag key={t} text={t} />)}
                        </div>
                      ) : "无"}
                    </div>
                    {assessRes.best_evidence?.chunk_id && (
                      <div>
                        <strong>{t("doc.bestEvidence")}</strong>
                        <button 
                          onClick={() => jumpToChunk(assessRes.best_evidence!.chunk_id)}
                          style={{ 
                            color: "var(--primary)", 
                            textDecoration: "underline", 
                            background: "none", 
                            border: "none",
                            cursor: "pointer",
                            fontSize: "0.875rem",
                            marginLeft: "0.25rem"
                          }}
                        >
                          {t("doc.viewChunk")}
                        </button>
                        <div style={{ 
                          marginTop: "0.375rem", 
                          padding: "0.5rem", 
                          background: "white", 
                          borderRadius: "8px",
                          fontSize: "0.8125rem",
                          color: "var(--gray-600)",
                          lineHeight: 1.5
                        }}>
                          "{assessRes.best_evidence.snippet?.slice(0, 150)}..."
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 熟练度评估结果 */}
              <div style={{ 
                padding: "1rem", 
                background: "var(--gray-50)", 
                borderRadius: "12px",
                border: profRes ? "1px solid var(--sage)" : "1px solid var(--gray-200)"
              }}>
                <div style={{ 
                  display: "flex", 
                  justifyContent: "space-between", 
                  alignItems: "center",
                  marginBottom: "0.75rem"
                }}>
                  <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{t("doc.proficiencyTitle")}</span>
                  {typeof profRes?.level === "number" && (
                    <StatusPill 
                      text={`L${profRes.level} ${profRes.label || ""}`} 
                      kind={profRes.level >= 2 ? "success" : profRes.level >= 1 ? "warning" : "neutral"} 
                    />
                  )}
                </div>
                {profErr && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{profErr}</div>}
                {!profErr && !profRes && (
                  <div style={{ color: "var(--gray-500)", fontSize: "0.875rem" }}>
                    {t("doc.clickToProficiency")}
                  </div>
                )}
                {profRes && (
                  <div style={{ fontSize: "0.875rem" }}>
                    <div style={{ marginBottom: "0.5rem" }}>
                      <strong>{t("doc.assessReason")}</strong> {profRes.rationale}
                    </div>
                    {profRes.best_evidence?.chunk_id && (
                      <div>
                        <strong>{t("doc.evidenceSource")}</strong>
                        <button 
                          onClick={() => jumpToChunk(profRes.best_evidence!.chunk_id)}
                          style={{ 
                            color: "var(--primary)", 
                            textDecoration: "underline", 
                            background: "none", 
                            border: "none",
                            cursor: "pointer",
                            fontSize: "0.875rem",
                            marginLeft: "0.25rem"
                          }}
                        >
                          {t("doc.viewChunk")}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* AI评估结果 */}
            {(aiProfRes || aiProfErr || aiDemoRes || aiDemoErr) && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: "1rem" }}>
                {/* AI智能评估 */}
                {(aiProfRes || aiProfErr) && (
                  <div style={{ 
                    padding: "1rem", 
                    background: "linear-gradient(135deg, var(--sage-50), var(--sage-light))", 
                    borderRadius: "12px",
                    border: "1px solid var(--sage)"
                  }}>
                    <div style={{ 
                      display: "flex", 
                      justifyContent: "space-between", 
                      alignItems: "center",
                      marginBottom: "0.75rem"
                    }}>
                      <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{t("doc.aiAssessTitle")}</span>
                      {typeof aiProfRes?.level === "number" && (
                        <StatusPill 
                          text={`L${aiProfRes.level} ${aiProfRes.label || ""}`} 
                          kind={aiProfRes.level >= 2 ? "success" : "warning"} 
                        />
                      )}
                    </div>
                    {aiProfErr && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{aiProfErr}</div>}
                    {aiProfRes && (
                      <div style={{ fontSize: "0.875rem" }}>
                        {aiProfRes.matched_criteria && aiProfRes.matched_criteria.length > 0 && (
                          <div style={{ marginBottom: "0.5rem" }}>
                            <strong>{t("doc.matchCriteria")}</strong>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", marginTop: "0.375rem" }}>
                              {aiProfRes.matched_criteria.map((c) => <Tag key={c} text={c} />)}
                            </div>
                          </div>
                        )}
                        <div style={{ marginBottom: "0.5rem" }}>
                          <strong>{t("doc.analysisNote")}</strong> {aiProfRes.why}
                        </div>
                        {aiProfRes.evidence_chunk_ids && aiProfRes.evidence_chunk_ids.length > 0 && (
                          <div>
                            <strong>{t("doc.evidenceSource")}</strong>
                            {aiProfRes.evidence_chunk_ids.slice(0, 5).map((cid) => (
                              <button 
                                key={cid}
                                onClick={() => jumpToChunk(cid)}
                                style={{ 
                                  color: "var(--primary)", 
                                  textDecoration: "underline", 
                                  background: "none", 
                                  border: "none",
                                  cursor: "pointer",
                                  fontSize: "0.8125rem",
                                  marginLeft: "0.375rem"
                                }}
                              >
                                #{cid.slice(0, 6)}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* 能力验证 */}
                {(aiDemoRes || aiDemoErr) && (
                  <div style={{ 
                    padding: "1rem", 
                    background: "linear-gradient(135deg, var(--peach-50), var(--peach-light))", 
                    borderRadius: "12px",
                    border: "1px solid var(--peach)"
                  }}>
                    <div style={{ 
                      display: "flex", 
                      justifyContent: "space-between", 
                      alignItems: "center",
                      marginBottom: "0.75rem"
                    }}>
                      <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{t("doc.capabilityTitle")}</span>
                      {aiDemoRes?.label && (
                        <StatusPill 
                          text={
                            aiDemoRes.label === "demonstrated" ? t("skills.verified") :
                            aiDemoRes.label === "mentioned" ? t("doc.onlyMentioned") : t("skills.insufficient")
                          } 
                          kind={
                            aiDemoRes.label === "demonstrated" ? "success" :
                            aiDemoRes.label === "mentioned" ? "warning" : "error"
                          } 
                        />
                      )}
                    </div>
                    {aiDemoErr && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{aiDemoErr}</div>}
                    {aiDemoRes && (
                      <div style={{ fontSize: "0.875rem" }}>
                        <div style={{ marginBottom: "0.5rem" }}>
                          <strong>{t("doc.verifyNote")}</strong> {aiDemoRes.rationale}
                        </div>
                        {aiDemoRes.evidence_chunk_ids && aiDemoRes.evidence_chunk_ids.length > 0 && (
                          <div>
                            <strong>{t("doc.evidenceSource")}</strong>
                            {aiDemoRes.evidence_chunk_ids.slice(0, 5).map((cid) => (
                              <button 
                                key={cid}
                                onClick={() => jumpToChunk(cid)}
                                style={{ 
                                  color: "var(--primary)", 
                                  textDecoration: "underline", 
                                  background: "none", 
                                  border: "none",
                                  cursor: "pointer",
                                  fontSize: "0.8125rem",
                                  marginLeft: "0.375rem"
                                }}
                              >
                                #{cid.slice(0, 6)}
                              </button>
                            ))}
                          </div>
                        )}
                        {aiDemoRes.refusal_reason && (
                          <div style={{ marginTop: "0.5rem", color: "var(--gray-600)" }}>
                            <strong>{t("doc.remarks")}</strong> {aiDemoRes.refusal_reason}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* 角色匹配区域 */}
          <Card 
            title={t("doc.roleMatch")} 
            icon="💼"
            actions={
              <div style={{ fontSize: "0.75rem", color: "var(--gray-500)" }}>
                {t("doc.assessRoleReadiness")}
              </div>
            }
          >
            <div style={{ marginBottom: "1.25rem" }}>
              <label style={{ 
                display: "block", 
                fontSize: "0.875rem", 
                fontWeight: 500, 
                marginBottom: "0.5rem",
                color: "var(--gray-700)"
              }}>
                {t("doc.selectRole")}
              </label>
              <select 
                value={roleId} 
                onChange={(e) => setRoleId(e.target.value)} 
                className="input"
                style={{ width: "100%", maxWidth: "500px" }}
              >
                {roles.map((x: any) => (
                  <option key={x.role_id} value={x.role_id}>
                    {x.role_title}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
              <button 
                onClick={runReadiness} 
                disabled={reading}
                className="btn btn-primary"
              >
                {reading ? t("doc.analyzing") : t("doc.assessReadiness")}
              </button>
              <button 
                onClick={runPlan} 
                disabled={planning}
                className="btn btn-ghost"
              >
                {planning ? t("doc.generating") : t("doc.getActions")}
              </button>
            </div>

            {readinessErr && <div style={{ color: "var(--error)", marginBottom: "1rem" }}>{readinessErr}</div>}
            {readiness && (
              <div style={{ 
                padding: "1rem", 
                background: "var(--gray-50)", 
                borderRadius: "12px",
                marginBottom: "1rem"
              }}>
                <div style={{ 
                  display: "flex", 
                  justifyContent: "space-between", 
                  alignItems: "center",
                  marginBottom: "1rem"
                }}>
                  <h4 style={{ margin: 0, fontSize: "1rem" }}>{readiness.role_title}</h4>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <StatusPill text={`${readiness.summary?.meet || 0} ${t("doc.met")}`} kind="success" />
                    <StatusPill text={`${readiness.summary?.needs_strengthening || 0} ${t("doc.needsImprovement")}`} kind="warning" />
                    <StatusPill text={`${readiness.summary?.missing_proof || 0} ${t("doc.lackEvidence")}`} kind="error" />
                  </div>
                </div>
                <div style={{ display: "grid", gap: "0.5rem" }}>
                  {(readiness.items || []).map((it: any) => (
                    <div 
                      key={it.skill_id}
                      style={{ 
                        display: "flex", 
                        justifyContent: "space-between", 
                        alignItems: "center",
                        padding: "0.75rem",
                        background: "white",
                        borderRadius: "8px",
                        border: "1px solid var(--gray-200)"
                      }}
                    >
                      <div>
                        <span style={{ fontWeight: 500 }}>{skillLabel(it.skill_id)}</span>
                        <span style={{ 
                          marginLeft: "0.5rem", 
                          fontSize: "0.75rem", 
                          color: "var(--gray-500)" 
                        }}>
                          L{it.observed_level} / 目标L{it.target_level}
                        </span>
                      </div>
                      <StatusPill 
                        text={it.status === "meet" ? t("doc.met") : it.status === "needs_strengthening" ? t("doc.needsImprovement") : t("doc.lackEvidence")} 
                        kind={it.status === "meet" ? "success" : it.status === "needs_strengthening" ? "warning" : "error"} 
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {planErr && <div style={{ color: "var(--error)", marginBottom: "1rem" }}>{planErr}</div>}
            {plan && plan.action_cards && plan.action_cards.length > 0 && (
              <div>
                <h4 style={{ fontSize: "0.9375rem", marginBottom: "0.75rem" }}>{t("doc.actionTitle")}</h4>
                <div style={{ display: "grid", gap: "0.75rem" }}>
                  {plan.action_cards.map((card: any, idx: number) => (
                    <div 
                      key={idx}
                      style={{ 
                        padding: "1rem", 
                        background: "linear-gradient(135deg, var(--coral-50), var(--coral-light))",
                        borderRadius: "12px",
                        border: "1px solid var(--coral-light)"
                      }}
                    >
                      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>{card.title}</div>
                      {card.what_to_do && (
                        <p style={{ fontSize: "0.875rem", color: "var(--gray-600)", marginBottom: "0.5rem" }}>
                          {card.what_to_do}
                        </p>
                      )}
                      {card.artifact && (
                        <div style={{ fontSize: "0.8125rem", color: "var(--gray-500)" }}>
                          <strong>{t("doc.output")}</strong> {card.artifact}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* 文档内容片段 */}
          <Card 
            title={`${t("doc.chunksPrefix")}${chunks.length})`}
            icon="📋"
            actions={
              chunksLoading ? (
                <div className="spinner" style={{ width: "1rem", height: "1rem" }}></div>
              ) : null
            }
          >
            <div ref={chunksRef}>
              {chunksErr && (
                <div className="alert alert-error" style={{ marginBottom: "1rem" }}>
                  <span>⚠</span>
                  <div>
                    <strong>{t("doc.loadFailed")}</strong>
                    <p style={{ fontSize: "0.875rem", margin: "0.25rem 0 0" }}>{chunksErr}</p>
                  </div>
                  <button 
                    onClick={() => window.location.reload()}
                    className="btn btn-sm btn-ghost"
                  >
                    {t("common.retry")}
                  </button>
                </div>
              )}

              {chunksLoading && (
                <div style={{ display: "grid", gap: "0.75rem" }}>
                  {[1, 2, 3].map((i) => (
                    <div key={i} style={{ padding: "1rem", background: "var(--gray-50)", borderRadius: "12px" }}>
                      <Skeleton width="30%" height="0.875rem" />
                      <div style={{ marginTop: "0.75rem" }}>
                        <Skeleton width="100%" height="3rem" />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!chunksLoading && !chunksErr && chunks.length === 0 && (
                <div style={{ textAlign: "center", padding: "3rem", color: "var(--gray-500)" }}>
                  <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📭</div>
                  <div>{t("doc.noChunks")}</div>
                </div>
              )}

              {!chunksLoading && chunks.length > 0 && (
                <div style={{ display: "grid", gap: "0.75rem" }}>
                  {chunks.map((chunk) => {
                    const isHighlighted = highlightChunkId === chunk.chunk_id;
                    const isExpanded = expandedChunk === chunk.chunk_id;
                    return (
                      <div
                        id={`chunk-${chunk.chunk_id}`}
                        key={chunk.chunk_id}
                        style={{
                          padding: "1rem",
                          background: isHighlighted ? "var(--peach-light)" : "var(--gray-50)",
                          borderRadius: "12px",
                          border: isHighlighted ? "2px solid var(--peach)" : "1px solid var(--gray-200)",
                          transition: "all 0.2s ease",
                          cursor: "pointer"
                        }}
                        onClick={() => setExpandedChunk(isExpanded ? null : chunk.chunk_id)}
                      >
                        <div style={{ 
                          display: "flex", 
                          justifyContent: "space-between", 
                          alignItems: "center",
                          marginBottom: "0.5rem"
                        }}>
                          <div style={{ 
                            display: "flex", 
                            alignItems: "center", 
                            gap: "0.75rem",
                            fontSize: "0.8125rem",
                            color: "var(--gray-600)"
                          }}>
                            <span style={{ 
                              background: "var(--primary)", 
                              color: "white", 
                              padding: "2px 8px", 
                              borderRadius: "6px",
                              fontSize: "0.75rem",
                              fontWeight: 600
                            }}>
                              #{chunk.idx + 1}
                            </span>
                            {chunk.section_path && (
                              <span>{chunk.section_path}</span>
                            )}
                            {chunk.page_start && (
                              <span>{t("common.pagePrefix")}{chunk.page_start} {t("common.page")}</span>
                            )}
                          </div>
                          <code style={{ 
                            fontSize: "0.6875rem", 
                            color: "var(--gray-400)",
                            background: "var(--gray-100)",
                            padding: "2px 6px",
                            borderRadius: "4px"
                          }}>
                            {chunk.chunk_id.slice(0, 8)}
                          </code>
                        </div>
                        <div style={{ 
                          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                          fontSize: "0.8125rem",
                          lineHeight: 1.6,
                          color: "var(--gray-700)",
                          whiteSpace: isExpanded ? "pre-wrap" : "nowrap",
                          overflow: "hidden",
                          textOverflow: isExpanded ? "unset" : "ellipsis"
                        }}>
                          {isExpanded ? (chunk.chunk_text || chunk.snippet) : chunk.snippet}
                        </div>
                        {isExpanded && chunk.chunk_text && chunk.chunk_text.length > 200 && (
                          <div style={{ 
                            marginTop: "0.75rem", 
                            paddingTop: "0.75rem", 
                            borderTop: "1px solid var(--gray-200)",
                            fontSize: "0.75rem",
                            color: "var(--gray-500)"
                          }}>
                            {t("common.chars")} {chunk.chunk_text.length} | {t("common.collapse")}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>
        </div>
      </main>

      {/* Footer */}
      <footer style={{ 
        padding: "1.5rem", 
        textAlign: "center", 
        borderTop: "1px solid var(--gray-200)",
        color: "var(--gray-500)",
        fontSize: "0.875rem"
      }}>
        <p>© 2026 SkillSight · HKU Skills-to-Jobs Transparency System</p>
      </footer>

      {/* CSS for shimmer animation */}
      <style jsx>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}
