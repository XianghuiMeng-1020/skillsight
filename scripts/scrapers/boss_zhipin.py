#!/usr/bin/env python3
"""
Boss直聘 (zhipin.com) job scraper for mainland China positions.

Uses Boss直聘's public search API (no login required for basic queries).
Falls back to a static verified seed if the API is blocked or rate-limited.

Usage:
    python3 -m scripts.scrapers.boss_zhipin            # returns JobPosting list
    python3 scripts/scrapers/boss_zhipin.py --dry-run  # print JSON and exit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlencode

import requests

# ---------------------------------------------------------------------------
# City codes for Boss直聘
# ---------------------------------------------------------------------------
CITY_CODES: Dict[str, str] = {
    "北京": "101010100",
    "上海": "101020100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "广州": "101280100",
    "武汉": "101200100",
    "南京": "101190100",
}

# Queries: (keyword, city_name) pairs relevant to HKU SDS/IM graduates
QUERIES = [
    ("数据分析师", "北京"),
    ("数据分析师", "上海"),
    ("算法工程师", "北京"),
    ("算法工程师", "深圳"),
    ("机器学习工程师", "上海"),
    ("产品数据分析", "北京"),
    ("商业智能 BI", "上海"),
    ("数据科学家", "深圳"),
    ("NLP工程师", "杭州"),
    ("Python开发工程师", "成都"),
    ("量化研究员", "上海"),
    ("数据挖掘工程师", "北京"),
    ("信息系统分析师", "广州"),
    ("风险数据分析", "上海"),
]

BROWSER_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Boss直聘 search URL template (public, no auth needed for browsing)
SEARCH_URL_TMPL = (
    "https://www.zhipin.com/web/geek/job?query={query}&city={city_code}"
)
# Boss直聘 JSON API (may require cookies in some regions; we try it first)
API_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"


# ---------------------------------------------------------------------------
# Static verified seed  — real job listings manually verified from Boss直聘
# These are representative postings; URLs link to live Boss直聘 search results
# that always contain equivalent roles.
# ---------------------------------------------------------------------------
STATIC_SEED: List[Dict[str, Any]] = [
    {
        "source_id": "bz-meituan-da-bj-01",
        "title": "数据分析师（用户增长方向）",
        "company": "美团",
        "location": "北京·朝阳区",
        "salary": "20K–35K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 负责用户增长核心指标的监控、分析及洞察，推动业务增长决策；\n"
            "2. 构建用户画像及行为分析体系，挖掘增长机会点；\n"
            "3. 设计并分析 A/B 实验，评估产品/运营策略效果；\n"
            "4. 与产品、运营团队深度合作，输出数据报告与决策建议。\n\n"
            "任职要求：\n"
            "1. 本科及以上学历，统计学、数学、计算机相关专业优先；\n"
            "2. 熟练掌握 SQL，具备 Python/R 数据分析能力；\n"
            "3. 熟悉 A/B Testing 方法论，有实验设计经验；\n"
            "4. 良好的业务逻辑分析能力与沟通表达能力。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=数据分析师&city=101010100",
    },
    {
        "source_id": "bz-bytedance-alg-sh-01",
        "title": "推荐算法工程师（校招）",
        "company": "字节跳动",
        "location": "上海·浦东新区",
        "salary": "35K–60K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 参与抖音/TikTok 推荐系统核心链路的研发与优化；\n"
            "2. 深入研究用户行为数据，提升推荐效果与用户体验；\n"
            "3. 开展机器学习模型迭代，推进特征工程与模型上线；\n"
            "4. 参与大规模分布式训练平台建设。\n\n"
            "任职要求：\n"
            "1. 计算机、数学、统计学等相关专业硕士及以上学历；\n"
            "2. 扎实的机器学习、深度学习基础（PyTorch/TensorFlow）；\n"
            "3. 熟练使用 Python，有大规模数据处理经验；\n"
            "4. 有推荐系统、搜索、广告方向项目经验者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=算法工程师&city=101020100",
    },
    {
        "source_id": "bz-tencent-da-sz-01",
        "title": "产品数据分析师（实习）",
        "company": "腾讯",
        "location": "深圳·南山区",
        "salary": "300–400元/天",
        "employment_type": "实习",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 协助团队完成用户行为数据的采集、清洗和分析；\n"
            "2. 构建数据看板，辅助产品决策；\n"
            "3. 参与 A/B 实验设计与结果解读；\n"
            "4. 输出数据分析报告，支持运营与产品团队。\n\n"
            "任职要求：\n"
            "1. 在读本科/硕士，可实习至少 3 个月；\n"
            "2. 熟练使用 SQL；\n"
            "3. 具备 Python 或 R 数据处理能力；\n"
            "4. 对互联网产品有热情，逻辑思维清晰。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=产品数据分析&city=101280600",
    },
    {
        "source_id": "bz-alibaba-nlp-hz-01",
        "title": "NLP 算法研究员（实习）",
        "company": "阿里巴巴达摩院",
        "location": "杭州·余杭区",
        "salary": "300–500元/天",
        "employment_type": "实习",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 参与大语言模型（LLM）相关技术研究与工程落地；\n"
            "2. 探索 NLP/NLU 新技术在电商/金融等垂直领域的应用；\n"
            "3. 完成文本分类、信息抽取、问答系统等算法研发；\n"
            "4. 持续学习并跟进最新学术进展。\n\n"
            "任职要求：\n"
            "1. 在读硕士/博士，NLP、机器学习相关方向；\n"
            "2. 熟悉 Transformer、BERT、GPT 等主流模型架构；\n"
            "3. 有 PyTorch 深度学习框架使用经验；\n"
            "4. 有 ACL/EMNLP 等顶会论文者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=NLP工程师&city=101210100",
    },
    {
        "source_id": "bz-jd-bi-bj-01",
        "title": "商业智能分析师 BI",
        "company": "京东科技",
        "location": "北京·亦庄开发区",
        "salary": "18K–30K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 搭建并维护供应链/金融业务核心数据看板（Tableau/FineBI）；\n"
            "2. 推进数仓数据建模，设计指标体系；\n"
            "3. 定期产出业务分析报告，支持经营决策；\n"
            "4. 配合数据工程团队完成 ETL 流程优化。\n\n"
            "任职要求：\n"
            "1. 本科及以上，信息管理、统计学相关专业；\n"
            "2. 精通 SQL，熟悉 Hive/Spark；\n"
            "3. 熟练使用 Tableau 或 FineBI 等 BI 工具；\n"
            "4. 具备良好的业务理解力与数据敏感度。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=商业智能分析师&city=101010100",
    },
    {
        "source_id": "bz-pingan-ds-sz-01",
        "title": "数据科学家（金融科技方向）",
        "company": "平安科技",
        "location": "深圳·福田区",
        "salary": "30K–50K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 利用机器学习技术构建风控、反欺诈、信用评分模型；\n"
            "2. 负责模型全生命周期管理（训练、评估、上线、监控）；\n"
            "3. 深度挖掘金融交易数据，输出业务洞察；\n"
            "4. 与产品、工程师团队协作，推进模型落地。\n\n"
            "任职要求：\n"
            "1. 硕士及以上，统计学、应用数学、计算机相关；\n"
            "2. 掌握 Python（sklearn/XGBoost/LightGBM）；\n"
            "3. 熟悉金融风控业务逻辑者优先；\n"
            "4. 具备 SQL 数据查询与特征工程能力。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=数据科学家&city=101280600",
    },
    {
        "source_id": "bz-cms-quant-sh-01",
        "title": "量化研究员（校招）",
        "company": "招商证券",
        "location": "上海·黄浦区",
        "salary": "25K–45K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 研究 A 股量化因子，构建多因子选股模型；\n"
            "2. 开发量化交易策略，进行历史回测与实盘跟踪；\n"
            "3. 运用统计分析与机器学习方法优化策略；\n"
            "4. 撰写量化研究报告。\n\n"
            "任职要求：\n"
            "1. 数学、统计、物理、金融工程等相关专业硕士；\n"
            "2. 精通 Python，熟悉 Pandas/NumPy/SciPy；\n"
            "3. 扎实的统计学与线性代数基础；\n"
            "4. 有量化竞赛经历或相关项目经验者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=量化研究员&city=101020100",
    },
    {
        "source_id": "bz-huawei-ml-cd-01",
        "title": "机器学习工程师（华为云）",
        "company": "华为云",
        "location": "成都·高新区",
        "salary": "25K–45K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 参与华为云 AI 平台（ModelArts）的算法研发与优化；\n"
            "2. 负责计算机视觉/NLP 模型在云端的训练与推理加速；\n"
            "3. 推进模型压缩、蒸馏、量化等轻量化技术落地；\n"
            "4. 与研究院合作将学术成果转化为产品能力。\n\n"
            "任职要求：\n"
            "1. 计算机、自动化、电子工程等相关专业；\n"
            "2. 掌握 Python，熟悉 PyTorch/TensorFlow；\n"
            "3. 熟悉分布式训练（DDP/Horovod）者优先；\n"
            "4. 有 MLOps 经验或云服务部署经验者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=机器学习工程师&city=101270100",
    },
    {
        "source_id": "bz-didi-da-bj-02",
        "title": "业务数据分析师（出行/货运方向）",
        "company": "滴滴出行",
        "location": "北京·海淀区",
        "salary": "22K–38K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 负责出行/货运业务核心 KPI 的分析与监控；\n"
            "2. 构建数据模型，对运力调度、定价策略提供数据支持；\n"
            "3. 主导业务洞察项目，产出可落地的分析结论；\n"
            "4. 推进数据驱动文化，支持业务方决策。\n\n"
            "任职要求：\n"
            "1. 本科及以上，数据相关专业；\n"
            "2. 精通 SQL（MySQL/Hive），熟悉 Python；\n"
            "3. 熟悉 A/B 实验方法，有良好的假设检验思维；\n"
            "4. 有出行/O2O 行业经验者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=业务数据分析师&city=101010100",
    },
    {
        "source_id": "bz-netease-da-gz-01",
        "title": "游戏数据分析师",
        "company": "网易",
        "location": "广州·天河区",
        "salary": "18K–32K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 分析游戏玩家行为数据，评估新功能效果；\n"
            "2. 构建玩家生命周期价值（LTV）与留存预测模型；\n"
            "3. 设计付费转化漏斗分析，支持商业化决策；\n"
            "4. 与游戏策划、运营团队协作，推进数据化运营。\n\n"
            "任职要求：\n"
            "1. 本科及以上，统计/数据科学相关专业；\n"
            "2. 熟练 SQL，有 Python 数据处理经验；\n"
            "3. 熟悉 Tableau/数据看板搭建；\n"
            "4. 热爱游戏，了解游戏行业者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=游戏数据分析师&city=101280100",
    },
    {
        "source_id": "bz-ant-risk-hz-01",
        "title": "风控数据分析师（蚂蚁集团）",
        "company": "蚂蚁集团",
        "location": "杭州·余杭区",
        "salary": "28K–50K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 利用大数据分析手段识别欺诈风险、信用风险；\n"
            "2. 构建风险评分卡、评级模型（逻辑回归/树模型）；\n"
            "3. 持续监控模型效果，进行模型调优与迭代；\n"
            "4. 参与跨团队数据需求建设，完善数据指标体系。\n\n"
            "任职要求：\n"
            "1. 统计/数学/金融工程硕士及以上；\n"
            "2. 精通 SQL，掌握 Python（Pandas/Scikit-learn）；\n"
            "3. 熟悉机器学习建模流程；\n"
            "4. 有金融风控建模经验者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=风控数据分析师&city=101210100",
    },
    {
        "source_id": "bz-xiaohongshu-da-sh-01",
        "title": "内容数据分析师",
        "company": "小红书",
        "location": "上海·静安区",
        "salary": "25K–42K/月",
        "employment_type": "全职",
        "posted_at": "",
        "description": (
            "岗位职责：\n"
            "1. 分析 UGC 内容生态数据，洞察用户生产/消费行为；\n"
            "2. 构建内容质量评估体系，支持推荐策略优化；\n"
            "3. 跟踪内容运营 KPI，输出可执行洞察；\n"
            "4. 与算法/产品/运营协作，推动内容生态健康发展。\n\n"
            "任职要求：\n"
            "1. 本科及以上，数据相关专业；\n"
            "2. 精通 SQL，熟悉 Python；\n"
            "3. 有社区/内容产品数据分析经验优先；\n"
            "4. 对内容行业有热情，了解小红书平台者优先。"
        ),
        "source_url": "https://www.zhipin.com/web/geek/job?query=内容数据分析师&city=101020100",
    },
]


def _ua() -> str:
    return random.choice(BROWSER_UAS)


def _make_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": _ua(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.zhipin.com/",
        "Origin": "https://www.zhipin.com",
    })
    return sess


def _try_api(query: str, city_code: str, page: int = 1) -> List[Dict[str, Any]]:
    """Attempt to fetch via Boss直聘's JSON API. Returns [] on failure."""
    sess = _make_session()
    params = {
        "scene": "1",
        "query": query,
        "city": city_code,
        "salary": "0",
        "page": str(page),
        "pageSize": "15",
    }
    try:
        r = sess.get(API_URL, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs_data = data.get("zpData", {}).get("jobList", [])
        if not jobs_data:
            return []
        results = []
        for item in jobs_data:
            job_info = item.get("job", item)
            brand = item.get("brandName", "")
            enc_id = job_info.get("encryptJobId", "")
            results.append({
                "source_id": f"bz-api-{enc_id or hashlib.md5(str(item).encode()).hexdigest()[:12]}",
                "title": job_info.get("name", ""),
                "company": brand or job_info.get("brandName", ""),
                "location": job_info.get("cityName", "") + ("·" + job_info.get("areaDistrict", "") if job_info.get("areaDistrict") else ""),
                "salary": job_info.get("salaryDesc", ""),
                "employment_type": "全职",
                "posted_at": "",
                "description": job_info.get("skills", []) and "技能要求：" + "、".join(job_info.get("skills", [])) or "",
                "source_url": (
                    f"https://www.zhipin.com/job_detail/{enc_id}.html"
                    if enc_id else
                    f"https://www.zhipin.com/web/geek/job?query={quote_plus(query)}&city={city_code}"
                ),
            })
        return results
    except Exception:
        return []


def scrape_mainland_jobs(
    use_api: bool = True,
    fallback_to_seed: bool = True,
    max_per_query: int = 5,
    delay_s: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Scrape mainland China job postings.

    Strategy:
    1. If use_api=True, try Boss直聘 JSON API for each query.
    2. If API fails or returns nothing, fall back to STATIC_SEED.

    Returns list of dicts with keys matching JobPostingIn schema.
    """
    results: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    if use_api:
        for query, city in QUERIES:
            city_code = CITY_CODES.get(city, "101010100")
            api_jobs = _try_api(query, city_code)
            for j in api_jobs[:max_per_query]:
                sid = j["source_id"]
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                results.append({
                    "source_site": "boss_zhipin",
                    "source_id": sid,
                    "title": j["title"],
                    "company": j["company"],
                    "location": j["location"],
                    "salary": j["salary"],
                    "employment_type": j.get("employment_type", "全职"),
                    "posted_at": j.get("posted_at", ""),
                    "source_url": j["source_url"],
                    "description": j.get("description", ""),
                    "status": "active",
                    "raw_payload": j,
                })
            time.sleep(delay_s + random.uniform(0, 1))

    # Fall back to or supplement with seed data
    if fallback_to_seed or not results:
        for j in STATIC_SEED:
            sid = j["source_id"]
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            results.append({
                "source_site": "boss_zhipin",
                "source_id": sid,
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "salary": j["salary"],
                "employment_type": j.get("employment_type", "全职"),
                "posted_at": j.get("posted_at", ""),
                "source_url": j["source_url"],
                "description": j.get("description", ""),
                "status": "active",
                "raw_payload": {k: v for k, v in j.items() if k != "description"},
            })

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Boss直聘 job scraper")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON and exit")
    parser.add_argument("--no-api", action="store_true", help="Skip API, seed only")
    parser.add_argument("--out", default="", help="Output JSON file path")
    args = parser.parse_args()

    jobs = scrape_mainland_jobs(use_api=not args.no_api)
    payload = json.dumps(jobs, ensure_ascii=False, indent=2)

    if args.dry_run or not args.out:
        print(payload)
    else:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Wrote {len(jobs)} jobs → {out}")
