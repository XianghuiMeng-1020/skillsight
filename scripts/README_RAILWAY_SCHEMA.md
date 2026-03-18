# Railway / 无 pgvector 的 Postgres 建表

Railway 默认 Postgres **未安装 pgvector**，`alembic upgrade head` 会在 `CREATE EXTENSION vector` 处失败，且历史上可能只存在 `assessment_*` 表。

## 一键修复（已链接 `skillsight-backend` 服务时）

```bash
# 需已安装: pip install 'psycopg[binary]'
railway run python3 scripts/apply_fix_railway_schema.py
```

脚本会执行 [`fix_railway_missing_tables.sql`](fix_railway_missing_tables.sql)，创建：

- `skills`, `roles`, `role_skill_requirements`, `skill_aliases`
- `documents`, `chunks`
- `skill_assessments`, `skill_proficiency`, `consents`

**不包含** `chunk_embeddings`（依赖 `vector` 类型）。若需向量入库，请换用带 pgvector 的 Postgres 或仅用 Qdrant 等外部向量库。

## 技能表为空时

若镜像内种子未跑成功（例如旧版启动逻辑），可手动灌入 `skills.json`：

```bash
railway run python3 scripts/seed_skills_if_empty.py
```

## 部署后

- 重新部署后，`/health` 的 `schema.ok` 会反映当前库表；若仍为 `false`，确认流量已切到新实例。
- 应用启动时会尝试种子 `skills` / `roles`（若表为空且代码与数据文件一致）。
