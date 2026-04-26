#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Generator for CE Intelligence
Version: 6.0 - 严格QA + 单一归属 + ALERTS双条件 + 新输出格式
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Any, Union, Optional, Tuple
from collections import defaultdict
import openai


class ReportGenerator:
    """生成符合企业情报标准的结构化 Markdown 及 HTML 报告"""

    TOPIC_NAMES = {
        1: "竞品动态",
        2: "新技术 / 材料",
        3: "制造（SEA / India）",
        4: "行业展会"
    }

    TOPIC_EMOJIS = {
        1: "🟥",
        2: "🟦",
        3: "🟩",
        4: "🟨"
    }

    # 报告输出章节顺序（按用户要求）
    # 每个 section 对应 source_topic（来自哪个T分类）
    # T3 拆分为两个子章节：CE制造 vs 新建厂/经济
    SECTIONS = [
        {
            "key":          "t3_ce",
            "emoji":        "🟩",
            "title_en":     "Consumer Electronics Manufacturing in Southeast Asia",
            "title_zh":     "东南亚消费电子制造动态",
            "source_topic": 3,
            "sub":          "ce"      # T3 CE子集
        },
        {
            "key":          "t1",
            "emoji":        "🟥",
            "title_en":     "Major Product Announcements",
            "title_zh":     "重大产品发布",
            "source_topic": 1,
            "sub":          None
        },
        {
            "key":          "t3_plant",
            "emoji":        "🟦",
            "title_en":     "New Manufacturing Plants & Southeast Asia Economy Updates",
            "title_zh":     "新建厂 / 东南亚经济动态",
            "source_topic": 3,
            "sub":          "plant"   # T3 工厂/经济子集
        },
        {
            "key":          "t2",
            "emoji":        "🟨",
            "title_en":     "New Technology / Materials",
            "title_zh":     "新技术 / 新材料",
            "source_topic": 2,
            "sub":          None
        },
        {
            "key":          "t4",
            "emoji":        "⬜",
            "title_en":     "Industry Exhibitions",
            "title_zh":     "行业展会",
            "source_topic": 4,
            "sub":          None
        },
    ]

    # T3 拆分关键词
    CE_MANUFACTURING_KEYWORDS = [
        "phone", "smartphone", "mobile", "handset", "iphone",
        "tv", "television", "oled tv", "qled", "home appliance",
        "vacuum", "washer", "refrigerator", "fridge", "air conditioner",
        "consumer electronics", "foldable", "tablet", "laptop", "wearable",
        "手机", "智能手机", "电视", "家电", "冰箱", "洗衣机", "空调",
        "折叠屏", "消费电子", "平板", "笔记本", "可穿戴", "扫地机"
    ]

    PLANT_ECONOMY_KEYWORDS = [
        "factory", "plant", "facility", "manufacturing plant", "assembly line",
        "investment", "billion", "million dollar", "gdp", "economy", "economic",
        "capacity", "expansion", "new facility", "greenfield", "construction",
        "工厂", "产线", "新建", "投资", "亿", "经济", "产能", "扩产",
        "建厂", "园区", "开工", "落地", "奠基", "试运行"
    ]

    IMPACT_LABELS = {
        "high": "🔴 HIGH",
        "medium": "🟡 MED",
        "low": "🟢 LOW"
    }

    HIGH_IMPACT_KEYWORDS = [
        "发布", "推出", "上市", "价格", "降价", "涨价", "市场份额", "超越", "首次", "首发",
        "突破", "颠覆", "关税", "制裁", "断供", "短缺",
        "越南", "印度", "工厂", "投资", "扩产", "战略合作",
        "launch", "release", "price cut", "shortage", "sanction", "investment", "expand"
    ]

    MEDIUM_IMPACT_KEYWORDS = [
        "升级", "改进", "优化", "展示", "亮相", "参展", "论坛",
        "趋势", "预测", "增长", "下降", "调整", "政策",
        "upgrade", "improve", "exhibit", "trend", "forecast"
    ]

    # ALERTS 四大判断维度（必须满足 ≥2 个）
    ALERT_CRITERIA = {
        "impacts_industry": [
            "market share", "市场份额", "competitor", "竞争", "rival",
            "overtake", "disruption", "breakthrough", "突破", "颠覆", "超越"
        ],
        "core_tech": [
            "ai", "chip", "芯片", "oled", "microled", "semiconductor", "半导体",
            "display", "面板", "npu", "processor", "处理器", "memory", "内存"
        ],
        "supply_chain_risk": [
            "supply chain", "供应链", "shortage", "短缺", "sanction", "制裁",
            "export ban", "出口禁令", "tariff", "关税", "disruption", "断供"
        ],
        "major_investment": [
            "investment", "投资", "billion", "亿", "expansion", "扩产",
            "new factory", "新工厂", "建厂", "capacity increase", "产能"
        ]
    }

    def __init__(self, config: Dict):
        self.config = config
        api_key = os.getenv("DEEPSEEK_API_KEY")
        self.ai_enabled = bool(api_key)
        if self.ai_enabled:
            openai.api_key = api_key
            openai.api_base = "https://api.deepseek.com/v1"

    # ------------------------------------------------------------------
    # 最终 QA 清洗关卡（输出前逐条检查）
    # ------------------------------------------------------------------

    def final_qa_gate(
        self,
        articles_by_topic: Dict[int, List[Dict]],
        deletion_log: Dict[str, int]
    ) -> Dict[int, List[Dict]]:
        """
        输出前最终清洗关卡。逐条检查5个条件，任何一项失败 → 删除。
        检查项：
        1. 无重复（标题唯一）
        2. 单一事件（非聚合或已拆分）
        3. 强相关（已由 classifier 过滤，此处为 fallback）
        4. 分类唯一（topics 列表长度 == 1）
        5. 结构完整（T4 必须有时间 + 地点）
        """
        seen_titles = set()
        result: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}

        for tid, arts in articles_by_topic.items():
            for article in arts:
                title = article.get("title", "").strip()
                failed_reason = None

                # 检查1: 重复
                if title in seen_titles:
                    failed_reason = "final_gate_duplicate"
                # 检查2: 未拆分聚合
                elif article.get("split_failed"):
                    failed_reason = "final_gate_unsplit"
                # 检查3: 强相关（topics 为空说明已被过滤，此处为保险）
                elif not article.get("topics"):
                    failed_reason = "final_gate_irrelevant"
                # 检查4: 分类唯一
                elif len(article.get("topics", [])) > 1:
                    failed_reason = "final_gate_multi_topic"
                # 检查5: T4 结构完整
                elif tid == 4 and not self._t4_has_structure(article):
                    failed_reason = "final_gate_t4_incomplete"

                if failed_reason:
                    deletion_log["final_gate"] = deletion_log.get("final_gate", 0) + 1
                    continue

                seen_titles.add(title)
                result[tid].append(article)

        removed = sum(len(arts) for arts in articles_by_topic.values()) - sum(len(a) for a in result.values())
        print(f"   🔍 Final QA gate: removed {removed} articles")
        return result

    def _split_t3(self, t3_articles: List[Dict]) -> Dict[str, List[Dict]]:
        """
        将 T3 文章拆分为两个子章节：
        - "ce"   : Consumer electronics manufacturing (含CE产品关键词)
        - "plant": New factories / SEA economy (工厂投资/经济动态)
        一篇文章只归入一个子章节（CE优先）。
        """
        ce_articles: List[Dict] = []
        plant_articles: List[Dict] = []

        for article in t3_articles:
            text = (article.get("title", "") + " " + article.get("summary", "")).lower()
            if any(kw.lower() in text for kw in self.CE_MANUFACTURING_KEYWORDS):
                ce_articles.append(article)
            else:
                plant_articles.append(article)

        # 若 CE 组为空则全部放入 plant 组（避免空章节）
        if not ce_articles:
            plant_articles = t3_articles

        return {"ce": ce_articles, "plant": plant_articles}

    def _t4_has_structure(self, article: Dict) -> bool:
        """T4 必须有时间和地点信息"""
        has_date = bool(
            article.get("exhibition_date") or
            article.get("published_date") or
            re.search(r"\d{4}[-/年]\d{1,2}", article.get("title", "") + article.get("summary", ""))
        )
        has_location = bool(
            article.get("exhibition_location") or
            re.search(r"(las vegas|berlin|barcelona|shanghai|shenzhen|beijing|上海|深圳|北京|广州|拉斯维加斯|柏林|巴塞罗那)",
                      (article.get("title", "") + article.get("summary", "")).lower())
        )
        return has_date and has_location

    # ------------------------------------------------------------------
    # 主输出方法
    # ------------------------------------------------------------------

    def generate_structured_markdown(
        self,
        articles: List[Dict],
        dedup_stats: Dict = None,
        raw_count: int = 0,
        deletion_log: Dict[str, int] = None
    ) -> str:
        """
        生成符合企业标准的结构化 Markdown 日报。
        包含：ALERTS / T1-T4各节 / 去重统计 / QA报告
        """
        deletion_log = deletion_log or {}
        date_str = datetime.now().strftime("%Y-%m-%d")
        articles_by_topic = self._group_by_topic(articles)

        lines = []
        lines.append(f"# 📰 消费电子产业情报日报（{date_str}）")
        lines.append("")

        # ── ALERTS ──────────────────────────────────────────────────────
        lines.append("## 🚨 ALERTS（高优先级）")
        lines.append("> 入选条件：必须满足以下 ≥2 项：影响行业格局 / 核心技术 / 供应链风险 / 重大投资扩产")
        lines.append("")
        alerts = self._collect_alerts(articles_by_topic)
        if alerts:
            for alert in alerts:
                lines.append(f"- {alert}")
        else:
            lines.append("- 今日无符合双条件的高优先级警报")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── 报告章节（按用户指定顺序）────────────────────────────────────
        t3_split = self._split_t3(articles_by_topic.get(3, []))

        for sec_idx, section in enumerate(self.SECTIONS, start=1):
            emoji     = section["emoji"]
            title_en  = section["title_en"]
            title_zh  = section["title_zh"]
            src_topic = section["source_topic"]
            sub       = section["sub"]

            if sub:
                sec_articles = t3_split.get(sub, [])
            else:
                sec_articles = articles_by_topic.get(src_topic, [])

            lines.append(f"## {emoji} Section {sec_idx} — {title_en}")
            lines.append(f"> {title_zh}")
            lines.append("")

            if not sec_articles:
                lines.append("_今日无相关新闻_")
                lines.append("")
                lines.append("---")
                lines.append("")
                continue

            for article in sec_articles:
                lines.extend(self._format_article_md(article, src_topic))

            lines.append("---")
            lines.append("")

        # ── 去重统计 ────────────────────────────────────────────────────
        lines.append("## 🧹 去重统计")
        after_count = len(articles)
        removed = raw_count - after_count if raw_count > after_count else (dedup_stats or {}).get("duplicates_removed", 0)
        lines.append(f"- 原始新闻数：{raw_count if raw_count else '未记录'}")
        lines.append(f"- 去重后：{after_count}")
        lines.append(f"- 删除：{removed}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── QA报告 ──────────────────────────────────────────────────────
        lines.append("## 🔍 QA报告")
        lines.append("")
        total_deleted = sum(deletion_log.values())
        lines.append(f"- **删除新闻总数**：{total_deleted}")
        lines.append(f"- **删除原因分布**：")
        lines.append(f"  - 不相关（过滤）：{deletion_log.get('irrelevant', 0)}")
        lines.append(f"  - 重复（URL/标题/语义）：{deletion_log.get('duplicate', 0) + deletion_log.get('semantic_duplicate', 0)}")
        lines.append(f"  - 聚合无法拆分：{deletion_log.get('unsplit', 0)}")
        lines.append(f"  - T4结构不完整：{deletion_log.get('t4_incomplete', 0)}")
        lines.append(f"  - 最终清洗关卡：{deletion_log.get('final_gate', 0)}")
        lines.append("")

        # QA验证
        qa = self._perform_qa(articles_by_topic)
        dup_status = "✅ 通过" if qa["no_duplicates"] else f"❌ 未通过（发现 {qa['duplicate_count']} 条重复）"
        lines.append(f"- **重复检测**：{dup_status}")
        lines.append(f"- **分类准确性**：{qa['classification_note']}")
        lines.append(f"- **数据完整性**：{qa['completeness_note']}")

        if qa.get("risk_points"):
            lines.append(f"- **风险点**：")
            for risk in qa["risk_points"]:
                lines.append(f"  - {risk}")
        lines.append("")

        return "\n".join(lines)

    def generate_markdown(self, articles: List[Dict], stats: Dict = None) -> str:
        """向后兼容接口"""
        raw_count = stats.get("total_before", len(articles)) if stats else len(articles)
        return self.generate_structured_markdown(articles, stats, raw_count)

    def generate_html(self, articles: Union[List[Dict], str], stats: Dict = None) -> str:
        """生成 HTML 报告（用于邮件发送）"""
        if isinstance(articles, str):
            return self._markdown_to_html(articles)
        if not articles:
            return "<html><body><h1>No articles found</h1></body></html>"

        date_str = datetime.now().strftime("%Y-%m-%d")
        date_display = datetime.now().strftime("%B %d, %Y")
        articles_by_topic = self._group_by_topic(articles)

        alerts = self._collect_alerts(articles_by_topic)
        alerts_html = "".join(
            f'<div class="alert-item"><span class="alert-badge">🔴 HIGH</span>'
            f'<span class="alert-text">{self._escape_html(a)}</span></div>'
            for a in alerts[:8]
        ) or '<div class="alert-item">今日无符合双条件的高优先级警报</div>'

        t3_split = self._split_t3(articles_by_topic.get(3, []))
        topic_html_parts = []
        for sec_idx, section in enumerate(self.SECTIONS, start=1):
            emoji     = section["emoji"]
            title_en  = section["title_en"]
            src_topic = section["source_topic"]
            sub       = section["sub"]

            if sub:
                sec_articles = t3_split.get(sub, [])
            else:
                sec_articles = articles_by_topic.get(src_topic, [])

            if not sec_articles:
                continue
            cards = "".join(self._format_article_card(a, src_topic) for a in sec_articles[:20])
            topic_html_parts.append(f"""
            <div class="topic-section">
                <h2 class="topic-title">{emoji} {sec_idx}. {title_en}</h2>
                <div class="articles-grid">{cards}</div>
            </div>""")

        total = len(articles)
        dedup_removed = (stats or {}).get("duplicates_removed", 0)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CE Intelligence Daily Report - {date_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;background:#f0f2f5;padding:20px;color:#1a1a2e}}
.container{{max-width:1200px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#0a0e27,#1a1a3e);color:#fff;padding:30px 40px;border-radius:16px 16px 0 0}}
.header h1{{font-size:1.6em;margin-bottom:6px}}
.header .date{{color:#ffd700;margin-top:10px}}
.stats-bar{{background:#fff;padding:16px 40px;border-radius:0 0 16px 16px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,.1);display:flex;gap:30px;align-items:center}}
.stat-item{{text-align:center}}
.stat-number{{font-size:1.8em;font-weight:700;color:#1a1a3e}}
.stat-label{{font-size:.75em;color:#666}}
.alerts-section{{background:#fff3e0;border-left:4px solid #ff6b35;padding:20px 28px;margin-bottom:24px;border-radius:12px}}
.alerts-title{{font-weight:700;color:#c0392b;margin-bottom:12px}}
.alert-item{{padding:8px 0;border-bottom:1px solid #ffe0b3;font-size:.88em}}
.alert-item:last-child{{border-bottom:none}}
.alert-badge{{background:#c0392b;color:#fff;padding:2px 8px;border-radius:4px;font-size:.7em;font-weight:600;margin-right:10px}}
.topic-section{{background:#fff;border-radius:16px;margin-bottom:24px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.topic-title{{background:linear-gradient(135deg,#1428a0,#0f1a5e);color:#fff;padding:16px 24px;font-size:1.1em;font-weight:600}}
.articles-grid{{padding:16px 24px;display:flex;flex-direction:column;gap:16px}}
.article-card{{border:1px solid #e8e8e8;border-radius:10px;padding:16px;border-left:4px solid #1428a0}}
.article-card.impact-high{{border-left-color:#c0392b;background:#fffaf8}}
.article-card.impact-medium{{border-left-color:#e67e22}}
.article-card.impact-low{{border-left-color:#27ae60}}
.article-title{{font-weight:600;margin-bottom:8px}}
.article-title a{{color:#1a1a3e;text-decoration:none}}
.article-title a:hover{{color:#1428a0;text-decoration:underline}}
.article-meta{{font-size:.75em;color:#888;margin-bottom:8px}}
.article-summary{{font-size:.85em;color:#444;line-height:1.55}}
.footer{{text-align:center;padding:24px;color:#888;font-size:.75em;border-top:1px solid #e0e0e0;margin-top:16px}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📰 消费电子产业情报日报</h1>
    <div class="date">{date_display} · 严格分类 · 单一归属 · 三层去重</div>
  </div>
  <div class="stats-bar">
    <div class="stat-item"><div class="stat-number">{total}</div><div class="stat-label">今日新闻</div></div>
    <div class="stat-item"><div class="stat-number">{dedup_removed}</div><div class="stat-label">已去重</div></div>
    <div class="stat-item"><div class="stat-number">T1–T4</div><div class="stat-label">四大栏目</div></div>
  </div>
  <div class="alerts-section">
    <div class="alerts-title">🚨 ALERTS — 今日高优先级情报（满足 ≥2 个判断维度）</div>
    {alerts_html}
  </div>
  {''.join(topic_html_parts)}
  <div class="footer">
    🤖 CE Intelligence System v6.0 · 单一归属 · 强QA · 低幻觉 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  </div>
</div>
</body>
</html>"""

    # ------------------------------------------------------------------
    # 格式化辅助
    # ------------------------------------------------------------------

    def _group_by_topic(self, articles: List[Dict]) -> Dict[int, List[Dict]]:
        result: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}
        for article in articles:
            for tid in article.get("topics", []):
                if tid in result and article not in result[tid]:
                    result[tid].append(article)
        return result

    def _collect_alerts(self, articles_by_topic: Dict[int, List[Dict]]) -> List[str]:
        """
        收集高优先级警报。
        必须满足 ≥2 个维度：影响行业格局 / 核心技术 / 供应链风险 / 重大投资扩产
        """
        alerts = []
        seen = set()
        for tid in range(1, 5):
            for article in articles_by_topic.get(tid, []):
                title = article.get("title", "")
                if title in seen:
                    continue
                if self._count_alert_criteria(article) >= 2:
                    seen.add(title)
                    source = article.get("source", "")
                    alerts.append(f"[T{tid}] {title}（{source}）")
        return alerts[:10]

    def _count_alert_criteria(self, article: Dict) -> int:
        """计算满足的 ALERTS 维度数量"""
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        count = 0
        for criterion, keywords in self.ALERT_CRITERIA.items():
            if any(kw.lower() in text for kw in keywords):
                count += 1
        return count

    def _format_article_md(self, article: Dict, topic_id: int) -> List[str]:
        """
        格式化单条新闻为企业标准 Markdown 块：
        【标题】
        - 来源：
        - 时间：
        - 分类：
        - 摘要（只包含一个事件）
        """
        title       = article.get("title", "无标题")
        source      = article.get("source", "未知来源")
        link        = article.get("link", article.get("url", "#"))
        summary     = article.get("summary", article.get("content", ""))
        pub_date    = self._format_date(article.get("published_date"))
        unreliable  = article.get("source_unreliable", False)
        topic_name  = self.TOPIC_NAMES.get(topic_id, f"T{topic_id}")

        lines = []

        # T1 加产品类别标签
        if topic_id == 1:
            cat = article.get("product_category", "产品")
            display_title = f"[{cat}] {title}"
        else:
            display_title = title

        source_note = f" ⚠️ 来源待核实" if unreliable else ""

        lines.append(f"### 【{display_title}】")
        lines.append(f"- **来源**：[{source}{source_note}]({link})")
        lines.append(f"- **时间**：{pub_date}")
        lines.append(f"- **分类**：T{topic_id} {topic_name}")

        if summary:
            clean = summary.strip()[:400].replace("\n", " ")
            lines.append(f"- **摘要**：{clean}")

        # T4 展会附加信息
        if topic_id == 4:
            ex_time = article.get("exhibition_date", "")
            ex_loc  = article.get("exhibition_location", "")
            ex_url  = article.get("exhibition_website", "")
            if ex_time:
                lines.append(f"- **展会时间**：{ex_time}")
            if ex_loc:
                lines.append(f"- **展会地点**：{ex_loc}")
            if ex_url:
                lines.append(f"- **参展商名单**：{ex_url}")

        lines.append("")
        return lines

    def _format_article_card(self, article: Dict, topic_id: int) -> str:
        """格式化单条新闻为 HTML 卡片"""
        title    = article.get("title", "无标题")
        link     = article.get("link", "#")
        source   = article.get("source", "未知来源")
        summary  = article.get("summary", "")
        pub_date = self._format_date(article.get("published_date"))
        impact   = self._determine_impact(article, topic_id)

        if topic_id == 1:
            cat = article.get("product_category", "产品")
            title = f"[{cat}] {title}"

        ai_summary = self._get_summary(article, impact)

        return f"""
        <div class="article-card impact-{impact}">
          <div class="article-meta">{self.IMPACT_LABELS[impact]} · {pub_date} · {self._escape_html(source)}</div>
          <div class="article-title"><a href="{link}" target="_blank">{self._escape_html(title)}</a></div>
          <div class="article-summary">{self._escape_html(ai_summary)}</div>
        </div>"""

    def _get_summary(self, article: Dict, impact: str) -> str:
        summary = article.get("summary", article.get("content", ""))
        if not summary:
            return article.get("title", "")
        if not self.ai_enabled:
            return summary[:150] + ("..." if len(summary) > 150 else "")
        try:
            emphasis = {
                "high": "重点突出对行业的紧迫影响和关键行动建议。",
                "medium": "客观总结事件内容，说明对行业的潜在影响。",
                "low": "简要记录该动态。"
            }.get(impact, "客观总结主要内容。")
            resp = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"你是消费电子行业资深情报分析师。请用简洁专业的中文生成1-2句总结（不超过80字）。{emphasis}直接陈述，不使用开头语。"},
                    {"role": "user", "content": f"标题：{article.get('title', '')}\n内容：{summary[:1200]}"}
                ],
                temperature=0.3, max_tokens=120
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return summary[:150] + ("..." if len(summary) > 150 else "")

    def _determine_impact(self, article: Dict, topic_id: int) -> str:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        score = sum(2 for kw in self.HIGH_IMPACT_KEYWORDS if kw.lower() in text)
        score += sum(1 for kw in self.MEDIUM_IMPACT_KEYWORDS if kw.lower() in text)
        if topic_id == 1:
            score += 1
        rel = article.get("reliability_score", 0.6)
        if rel >= 0.9:
            score += 1
        if score >= 4:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def _format_date(self, pub_date) -> str:
        if pub_date is None:
            return "日期未知"
        if isinstance(pub_date, datetime):
            return pub_date.strftime("%Y-%m-%d")
        if isinstance(pub_date, str):
            return pub_date[:10]
        return str(pub_date)[:10]

    def _escape_html(self, text: str) -> str:
        if not text:
            return ""
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&#39;"))

    def _markdown_to_html(self, md: str) -> str:
        md_escaped = md.replace("\n", "<br>")
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Report</title></head>
<body style="font-family:Arial,sans-serif;padding:20px;max-width:900px;margin:auto">
{md_escaped}
</body></html>"""

    # ------------------------------------------------------------------
    # QA 验证
    # ------------------------------------------------------------------

    def _perform_qa(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict:
        all_titles = []
        missing_source = 0
        multi_topic_count = 0
        risk_points = []

        for tid, arts in articles_by_topic.items():
            for a in arts:
                all_titles.append(a.get("title", ""))
                if not a.get("source") or a.get("source") == "unknown":
                    missing_source += 1
                if len(a.get("topics", [])) > 1:
                    multi_topic_count += 1

        unique_titles = set(all_titles)
        duplicate_count = len(all_titles) - len(unique_titles)

        classification_note = "T1-T4 严格规则已执行；单一归属原则已强制"
        if duplicate_count > 0:
            classification_note += f"（⚠️ 仍有 {duplicate_count} 条标题重复）"
            risk_points.append(f"发现 {duplicate_count} 条重复标题，建议检查语义去重阈值")
        if multi_topic_count > 0:
            risk_points.append(f"{multi_topic_count} 条新闻仍有多 topic 标签，单一归属未完全生效")

        if missing_source == 0:
            completeness_note = f"✅ 所有新闻均有来源；共 {len(all_titles)} 条"
        else:
            completeness_note = f"⚠️ 共 {len(all_titles)} 条，其中 {missing_source} 条来源缺失"
            risk_points.append(f"{missing_source} 条新闻来源不明，情报可信度存疑")

        return {
            "no_duplicates": duplicate_count == 0,
            "duplicate_count": duplicate_count,
            "classification_note": classification_note,
            "completeness_note": completeness_note,
            "risk_points": risk_points
        }
