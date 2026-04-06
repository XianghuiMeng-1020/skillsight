# SkillSight 完整功能文档

> HKU Skills-to-Jobs Transparency System - v0.2.0

---

## 📊 系统概览

SkillSight 是一个基于证据的技能评估系统，帮助学生展示可验证的技能，并将其与就业要求对接。

### 核心理念
- **Evidence-First**: 任何技能结论必须有证据指针支持
- **Explainable**: 所有评估结果可解释、可追溯
- **Privacy-by-Design**: 严格的同意管理和数据删除

---

## 🎯 MVP 6项核心功能

### 1. 文档上传与同意管理

**功能描述**: 学生上传文档（PDF/DOCX/TXT/图片/视频）并选择同意处理

**实现方式**:
- **端点**: `POST /documents/upload`, `POST /documents/upload_multimodal`
- **文件**: `backend/app/routers/documents.py`
- **解析**: `backend/app/parsers.py`, `backend/app/parsers_multimodal.py`

**支持格式**:
| 类型 | 格式 | 处理方式 |
|------|------|----------|
| 文档 | .txt, .docx, .pdf, .pptx | 文本提取 + 分块 |
| 图片 | .jpg, .png, .webp, .gif | OCR 文本提取 |
| 视频/音频 | .mp4, .mp3, .wav | Whisper 转录 |
| 代码 | .py, .js, .java, .cpp | 语法感知分块 |

**代码示例**:
```python
# backend/app/routers/documents.py
@router.post("/upload")
async def upload_document(
    file: UploadFile,
    doc_type: str = Query(default="demo"),
    user_id: str = Query(default="anonymous"),
    consent: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    # 1. 验证同意
    # 2. 保存文件
    # 3. 解析成 chunks
    # 4. 创建 consent 记录
    # 5. 创建 embedding job
```

### 1.5 简历增强与 DOCX 导出

**功能描述**: 学生完成 Rubric 评分与 AI 建议后，可将合并后的正文套用内置模板导出 `.docx`；可选 PDF（需服务端安装 LibreOffice / `soffice`）；支持 HTML 近似预览与导出前版面体检。

**实现方式**:
- **端点**:
  - `POST /bff/student/resume-review/{review_id}/apply-template` — body 可含 `export_format`: `docx` | `pdf`
  - `GET /bff/student/resume-review/{review_id}/preview-html?template_id=` — 返回与模板配色一致的 HTML 预览
  - `GET /bff/student/resume-review/{review_id}/layout-check` — 启发式版面/可读性提示
  - `GET /bff/student/resume-templates?review_id=` — 按目标岗位标签排序并标记 `recommended`
- **代码**: `backend/app/services/resume_template_service.py`, `backend/app/services/resume_text_merge.py`, `backend/app/services/resume_structured.py`, `backend/app/services/docx_pdf.py`, `backend/app/routers/resume_review.py`
- **可观测性**: 见 [OBSERVABILITY_RESUME.md](OBSERVABILITY_RESUME.md)

**限制与提示**: 扫描版或图片型 PDF 若无可用文本则无法生成高质量导出；复杂版式在 Microsoft Word 中最稳定，WPS / LibreOffice 可能对表格底纹或边距略有差异（学生端「模板与导出」步骤有说明）。PDF 依赖本机/容器内 LibreOffice；不可用时接口仍返回 DOCX 并带 `pdf_unavailable`。

---

### 2. 文件解析与分块

**功能描述**: 将文件解析成可引用的片段（chunk），保留原文位置信息

**实现方式**:
- **文件**: `backend/app/parsers.py`
- **分块策略**: 按段落/标题分块，保留 char_start/char_end
- **数据结构**:

```python
Chunk = {
    "chunk_id": "uuid",
    "doc_id": "uuid",
    "idx": 0,
    "char_start": 0,
    "char_end": 500,
    "chunk_text": "原文内容...",
    "snippet": "截断摘要...",
    "quote_hash": "sha256_hash",  # 防篡改
    "section_path": "Heading 1 > Heading 2",
    "page_start": 1,
    "page_end": 1
}
```

---

### 3. Evidence Retrieval (Decision 1)

**功能描述**: 基于技能定义检索相关证据片段

**实现方式**:
- **端点**: `POST /search/evidence_vector`
- **文件**: `backend/app/routers/search.py`
- **向量库**: Qdrant
- **嵌入模型**: all-MiniLM-L6-v2 (384维)

**工作流程**:
```
Skill Definition → Embedding → Qdrant Search → Top-K Chunks → Evidence Pointers
```

**API 请求**:
```json
POST /search/evidence_vector
{
    "skill_id": "HKU.SKILL.PRIVACY.v1",
    "doc_id": "optional-filter",
    "k": 5,
    "min_score": 0.5
}
```

**API 响应**:
```json
{
    "query_text": "Privacy data protection...",
    "items": [
        {
            "chunk_id": "...",
            "doc_id": "...",
            "snippet": "...",
            "score": 0.85,
            "char_start": 100,
            "char_end": 500
        }
    ]
}
```

---

### 4. Demonstration Assessment (Decision 2)

**功能描述**: 判断技能是否被 demonstrated / mentioned / not_enough_information

**实现方式**:
- **端点**: `POST /ai/demonstration`
- **文件**: `backend/app/routers/ai.py`
- **Prompt**: `packages/prompts/demonstration_v1.txt`
- **LLM**: Ollama (本地) / OpenAI API

**严格规则**:
1. 不能捏造证据，只能使用提供的 chunks
2. 证据不足必须返回 "not_enough_information"
3. 输出必须包含 evidence_chunk_ids
4. 无证据时必须给出 refusal_reason

**输出 Schema**:
```json
{
    "label": "demonstrated|mentioned|not_enough_information",
    "evidence_chunk_ids": ["chunk_id_1", "chunk_id_2"],
    "rationale": "理由说明...",
    "refusal_reason": null | "原因说明"
}
```

---

### 5. Proficiency Assessment (Decision 3)

**功能描述**: 基于 Rubric 评估技能熟练度等级 (0-3)

**实现方式**:
- **端点**: `POST /ai/proficiency`
- **文件**: `backend/app/routers/ai.py`
- **Prompt**: `packages/prompts/proficiency_v1.txt`

**等级定义**:
| Level | Label | 描述 |
|-------|-------|------|
| 0 | Novice | 无证据或太模糊 |
| 1 | Developing | 提及但无具体应用 |
| 2 | Intermediate | 有具体应用实例 |
| 3 | Advanced | 深度应用，多个实例 |

**Rubric 驱动**: 每个技能都有明确的评估标准 (`rubric_v1`)，LLM 必须引用具体的 criteria ID。

---

### 6. Role Readiness & Action Cards (Decision 4-5)

**功能描述**: 将学生技能与岗位要求对比，生成准备度报告和行动建议

**实现方式**:
- **端点**: `POST /assess/role_readiness`, `POST /actions/recommend`
- **文件**: `backend/app/routers/assess.py`, `backend/app/routers/actions.py`

**Readiness 状态**:
| 状态 | 条件 |
|------|------|
| `meet` | demonstrated 且 level >= target |
| `needs_strengthening` | demonstrated 但 level < target |
| `missing_proof` | not_enough_information 或 only mentioned |

**Action Card 结构**:
```json
{
    "skill_id": "HKU.SKILL.PRIVACY.v1",
    "gap_type": "missing_proof",
    "title": "Add evidence for privacy awareness",
    "what_to_do": "具体任务描述...",
    "artifact": "需要产出的证据类型",
    "how_verified": "如何验证完成"
}
```

---

## 🆕 交互式评估功能

### Communication Assessment (Kira-style)

**功能描述**: 类似 Kira Talent 的视频面试评估

**特性**:
- 随机话题生成 (15+ 话题库)
- 可配置时长 (30/60/90秒)
- 30秒准备时间
- 最多3次重试
- 一致性评分

**端点**:
- `POST /interactive/communication/start`
- `POST /interactive/communication/submit`
- `GET /interactive/sessions/{id}/consistency`

**评估指标**:
- 词数 (word count)
- 语速 (WPM)
- 内容相关性
- 表达结构

**实现文件**: `backend/app/routers/interactive_assess.py`

---

### Programming Assessment (LeetCode-style)

**功能描述**: 编程能力评估

**特性**:
- 难度分级 (Easy/Medium/Hard)
- 自动生成题目
- 时间限制 (10-30分钟)
- 代码静态分析

**题目示例**:
- Two Sum (Easy)
- Longest Substring Without Repeating Characters (Medium)
- Merge K Sorted Lists (Hard)

**端点**:
- `POST /interactive/programming/start`
- `POST /interactive/programming/submit`

**实现文件**: `backend/app/routers/interactive_assess.py`

---

### Writing Assessment

**功能描述**: 限时写作评估

**特性**:
- 随机话题生成
- 严格计时 (15-60分钟)
- **防复制检测**:
  - 键盘输入监控
  - 粘贴事件检测
  - 打字速度异常检测
- 字数限制 (300-500词)

**评估指标**:
- 字数得分
- 结构得分 (段落数)
- 句子多样性
- 真实性得分

**端点**:
- `POST /interactive/writing/start`
- `POST /interactive/writing/submit`

---

## 🔒 数据治理功能

### Consent Management

**功能描述**: 同意管理与数据删除

**端点**:
- `POST /consent/grant` - 授予同意
- `POST /consent/revoke` - 撤回同意（触发级联删除）
- `GET /consent/status/{doc_id}` - 查询状态

**级联删除流程**:
```
revoke → role_readiness → skill_proficiency → skill_assessments → chunks → embeddings (Qdrant) → 文件 → document
```

---

### Audit Log

**功能描述**: 操作审计追踪

**记录内容**:
- 用户 ID
- 事件类型 (upload, assess, revoke, override)
- 对象类型和 ID
- 详细信息
- 时间戳

**实现文件**: `backend/app/audit.py`

---

### Change Log

**功能描述**: 技能评估变化记录

**记录内容**:
- 变化前后的状态
- 变化原因 (新文档、rubric更新、人工覆盖)
- 触发时间

**实现文件**: `backend/app/change_log.py`

---

## 🖥️ 前端页面

### 首页 (`/`)
- API 状态检查
- 快捷导航链接
- 文档上传 (简化版)
- 向量证据搜索
- 最近上传列表

### 多模态上传 (`/upload`)
- 拖拽上传
- 支持所有格式
- 同意确认
- 上传结果展示

### 交互式评估 (`/assess`)
- 三种评估类型切换
- Communication: 话题 + 录音模拟
- Programming: 题目 + 代码编辑器
- Writing: 话题 + 限时写作

### 文档详情 (`/documents/[docId]`)
- 文档元数据
- Chunk 列表
- 证据高亮

### 管理面板 (`/admin`)
- 任务管理
- 技能别名管理
- 课程技能映射

---

## 📁 项目结构

```
skillsight/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── routers/             # 15 个路由模块
│   │   ├── db/                  # 数据库连接
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── services/            # 业务逻辑服务
│   │   ├── parsers.py           # 文档解析
│   │   ├── parsers_multimodal.py# 多模态解析
│   │   ├── embeddings.py        # 嵌入生成
│   │   ├── vector_store.py      # Qdrant 客户端
│   │   ├── guardrails.py        # AI 护栏
│   │   └── queue.py             # 任务队列
│   ├── alembic/                 # 数据库迁移
│   ├── data/                    # 种子数据
│   ├── tests/                   # 测试文件
│   └── worker.py                # 后台 Worker
├── web/
│   └── src/app/                 # Next.js 页面
├── packages/
│   ├── prompts/                 # LLM Prompt 模板
│   └── schemas/                 # JSON Schema
├── docs/
│   └── protocols/               # 10 个协议文档
└── docker-compose.yml           # 基础设施
```

---

## 🔌 技术栈

| 层 | 技术 | 版本 |
|---|------|------|
| 前端 | Next.js (React) | 15.x |
| 后端 | FastAPI | 0.110+ |
| 数据库 | PostgreSQL + pgvector | 16 |
| 向量库 | Qdrant | 1.7+ |
| 嵌入 | Sentence Transformers | 2.2+ |
| LLM | Ollama / OpenAI | - |
| 任务队列 | Redis + RQ | 7.x |
| 容器 | Docker Compose | - |

---

## 📊 API 端点汇总

### 文档管理 (6个)
- `GET /documents`
- `GET /documents/{doc_id}`
- `GET /documents/{doc_id}/chunks`
- `POST /documents/upload`
- `POST /documents/upload_multimodal`
- `POST /documents/{doc_id}/reindex`

### 证据搜索 (2个)
- `POST /search/evidence_vector`
- `POST /search/evidence_keyword`

### AI 评估 (2个)
- `POST /ai/demonstration`
- `POST /ai/proficiency`

### 角色准备度 (1个)
- `POST /assess/role_readiness`

### 行动建议 (2个)
- `POST /actions/recommend`
- `GET /actions/templates`

### 交互式评估 (9个)
- `POST /interactive/communication/start`
- `POST /interactive/communication/submit`
- `POST /interactive/programming/start`
- `POST /interactive/programming/submit`
- `POST /interactive/writing/start`
- `POST /interactive/writing/submit`
- `GET /interactive/sessions/{session_id}`
- `GET /interactive/sessions/user/{user_id}`
- `GET /interactive/sessions/{session_id}/consistency`

### 同意管理 (3个)
- `POST /consent/grant`
- `POST /consent/revoke`
- `GET /consent/status/{doc_id}`

### 任务管理 (5个)
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/retry`
- `POST /jobs/enqueue/{doc_id}`
- `GET /jobs/queue/status`

### 数据管理 (10+)
- `/skills/*`
- `/roles/*`
- `/courses/*`
- `/chunks/*`
- `/assessments/*`
- `/proficiency/*`

**总计: 40+ API 端点**

---

## 🎨 设计原则

1. **Evidence Pointer 必须可跳转**: 任何证据引用都能定位到原文
2. **Refusal is OK**: 证据不足时拒答是正确行为
3. **Audit Everything**: 所有操作都有审计记录
4. **Consent First**: 先同意后处理
5. **Explainable Results**: 每个结论都有理由

---

*文档版本: v0.2.0 | 更新日期: 2026-01-21*
