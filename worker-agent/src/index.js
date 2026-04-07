const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

const TUTOR_SYSTEM_PROMPT = `You are SkillSight, an HKU career advisor.
Provide concise and practical coaching.`;

const SCENARIOS = {
  "HKU.SKILL.COMMUNICATION.v1": [
    "Describe a time you influenced a team decision.",
    "Explain a complex idea to a non-technical audience.",
  ],
  "HKU.SKILL.PYTHON.v1": [
    "Walk through how you debugged a failing Python data pipeline.",
    "Explain a Python project where you improved performance.",
  ],
  "HKU.SKILL.CRITICAL_THINKING.v1": [
    "Describe a situation where you had conflicting evidence and made a decision.",
  ],
};

const RUBRICS = {
  novice: "Shows limited evidence and mostly theory.",
  developing: "Shows partial practice with some concrete steps.",
  proficient: "Shows repeated application with outcomes.",
  advanced: "Shows high ownership, trade-off reasoning, and measurable impact.",
};

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (path === "/health" || path === "/bff/health") return jsonResponse({ status: "ok", ok: true, agent: true });
      if (path === "/bff/student/tutor-session/start" && request.method === "POST") return handleTutorSessionStart(request, env);
      if (path.match(/^\/bff\/student\/tutor-session\/[^/]+\/message$/) && request.method === "POST") return handleTutorMessage(request, env);
      if (path === "/bff/student/auth/dev_login" && request.method === "POST") return handleDevLogin();
      return jsonResponse({ error: "Not implemented", path }, 404);
    } catch (error) {
      return jsonResponse({ error: "Internal Server Error", detail: error.message }, 500);
    }
  },
};

function buildAssessmentPrompt(skillId, turnCount) {
  const scenarios = SCENARIOS[skillId] || SCENARIOS["HKU.SKILL.COMMUNICATION.v1"];
  return `You are SkillSight Assessment Agent.
Current skill_id: ${skillId}
Scenarios:
${scenarios.map((s, i) => `${i + 1}. ${s}`).join("\n")}

Rubric:
- 0 novice: ${RUBRICS.novice}
- 1 developing: ${RUBRICS.developing}
- 2 proficient: ${RUBRICS.proficient}
- 3 advanced: ${RUBRICS.advanced}

Rules:
1) Stay on this skill only.
2) Ask probing follow-ups when evidence is vague.
3) If confidence >= 0.80 OR user_turns >= 10, conclude with:
ASSESSMENT: {"level":0|1|2|3,"confidence":0.0-1.0,"evidence_chunk_ids":[],"why":"...","mode_hint":"text|voice|code|case"}
Current user_turns=${turnCount}.`;
}

async function handleTutorSessionStart(request, env) {
  const body = await request.json();
  const sessionId = crypto.randomUUID();
  const session = {
    session_id: sessionId,
    skill_id: body.skill_id || "HKU.SKILL.COMMUNICATION.v1",
    user_id: body.user_id || "demo_student",
    mode: body.mode || "assessment",
    created_at: Date.now(),
    turns: [],
  };
  await env.SKILLSIGHT_KV.put(`session:${sessionId}`, JSON.stringify(session), { expirationTtl: 3600 });
  return jsonResponse({ session_id: sessionId, skill_id: session.skill_id, mode: session.mode, doc_ids: [] });
}

async function handleTutorMessage(request, env) {
  const pathMatch = request.url.match(/tutor-session\/([^/]+)/);
  const sessionId = pathMatch ? pathMatch[1] : null;
  if (!sessionId) return jsonResponse({ error: "Session ID required" }, 400);
  const body = await request.json();
  const text = (body.text || body.content || "").trim();
  if (!text) return jsonResponse({ error: "text is required" }, 422);

  const sessionData = await env.SKILLSIGHT_KV.get(`session:${sessionId}`);
  if (!sessionData) return jsonResponse({ error: "Session not found" }, 404);
  const session = JSON.parse(sessionData);
  const turnCount = session.turns.filter((t) => t.role === "user").length;
  const assessmentPrompt = buildAssessmentPrompt(session.skill_id, turnCount);
  const systemPrompt = session.mode === "assessment" ? assessmentPrompt : TUTOR_SYSTEM_PROMPT;
  const messages = [{ role: "system", content: systemPrompt }, ...session.turns.map((t) => ({ role: t.role, content: t.content })), { role: "user", content: text }];
  const reply = await callOpenAI(messages, env);

  session.turns.push({ role: "user", content: text, ts: Date.now() }, { role: "assistant", content: reply, ts: Date.now() });
  await env.SKILLSIGHT_KV.put(`session:${sessionId}`, JSON.stringify(session), { expirationTtl: 3600 });

  let assessment = null;
  if (session.mode === "assessment") assessment = parseAssessment(reply);
  let concluded = Boolean(assessment);
  if (!concluded && session.mode === "assessment" && turnCount >= 9) {
    assessment = { level: 1, confidence: 0.6, evidence_chunk_ids: [], why: "Auto-concluded due to max turns", mode_hint: "text" };
    concluded = true;
  }

  if (concluded && assessment) {
    await syncResultToBackend(env, session, assessment, text, sessionId);
  }
  return jsonResponse({ reply, concluded, assessment });
}

async function syncResultToBackend(env, session, assessment, responseText, sessionId) {
  const backendBase = env.BACKEND_API_URL || "http://127.0.0.1:8001";
  const token = env.BACKEND_BEARER_TOKEN || "";
  const payload = {
    user_id: session.user_id || "demo_student",
    skill_id: session.skill_id,
    session_id: sessionId,
    assessment_type: "agent_dialogue",
    response_text: responseText,
    evaluation: {
      overall_score: Math.round(((assessment.level || 0) / 3) * 100),
      level: assessment.level || 0,
      feedback: assessment.why || "Agent dialogue assessment",
      confidence: assessment.confidence || 0.5,
    },
  };
  try {
    await fetch(`${backendBase}/interactive/agent/sync-result`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(payload),
    });
  } catch (_) {}
}

async function callOpenAI(messages, env) {
  const apiKey = env.OPENAI_API_KEY;
  if (!apiKey) {
    return `Let's run a short assessment.\nASSESSMENT: {"level":2,"confidence":0.72,"evidence_chunk_ids":[],"why":"Mock assessment - API key not configured","mode_hint":"text"}`;
  }
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: env.OPENAI_MODEL || "gpt-4o-mini",
      messages,
      temperature: 0.3,
      max_tokens: 800,
    }),
  });
  if (!response.ok) throw new Error(`OpenAI API error: ${await response.text()}`);
  const data = await response.json();
  return data.choices?.[0]?.message?.content || "Let's continue.";
}

function parseAssessment(reply) {
  const match = reply.match(/ASSESSMENT:\s*(\{[\s\S]*\})/);
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[1]);
    if (typeof parsed.level !== "number") return null;
    return parsed;
  } catch (_) {
    return null;
  }
}

function handleDevLogin() {
  return jsonResponse({
    token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.demo",
    subject_id: "demo_student",
    role: "student",
  });
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders },
  });
}
