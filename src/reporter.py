#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Generator for CE Intelligence
Version: 7.0 - 新四分类体系输出（Topic1-4 + High/Med/Low优先级）
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
        1: "Consumer Electronics Manufacturing in Southeast Asia",
        2: "New Manufacturing Plants in Southeast Asia",
        3: "Major Product Announcements",
        4: "New Technology / Materials"
    }

    TOPIC_NAMES_ZH = {
        1: "东南亚消费电子制造动态",
        2: "东南亚新建工厂",
        3: "重大产品发布",
        4: "新技术 / 新材料"
    }

    TOPIC_EMOJIS = {
        1: "🟩",
        2: "🟦",
        3: "🟥",
        4: "🟨"
    }

    IMPACT_LABELS = {
        "high": "🔴 HIGH",
        "medium": "🟡 MED",
        "low":  "🟢 LOW"
    }

    # ALERTS 四大判断维度（必须 ≥2 个维度关键词命中）
    # 每个维度通过关键词硬判断，不依赖语义理解，确保可操作
    ALERT_CRITERIA = {
        "industry_disruption": [
            "competitor", "market share", "replace", "disrupt", "overtake", "rival",
            "beats", "surpass", "dethrone",
            "市场份额", "竞争对手", "竞争", "超越", "颠覆", "取代", "领先"
        ],
        "core_technology": [
            "oled", "microled", "mini-led", "battery", "chipset", "processor",
            "display panel", "npu", "solid state", "silicon anode",
            "芯片", "面板", "电池", "处理器", "固态电池", "显示技术"
        ],
        "supply_chain_risk": [
            "shortage", "tariff", "sanction", "supply chain", "export ban",
            "supply disruption", "bottleneck",
            "短缺", "关税", "制裁", "供应链", "出口禁令", "断供", "瓶颈"
        ],
        "major_investment": [
            "investment", "billion", "capacity", "new factory", "expansion",
            "greenfield", "manufacturing plant", "facility",
            "投资", "亿", "产能", "新工厂", "扩产", "建厂", "制造基地"
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
    # 最终 QA 清洗关卡
    # ------------------------------------------------------------------

    def final_qa_gate(
        self,
        articles_by_topic: Dict[int, List[Dict]],
        deletion_log: Dict[str, int]
    ) -> Dict[int, List[Dict]]:
        """
        输出前最终清洗关卡。逐条检查，任何一项失败 → 删除。
        """
        seen_titles = set()
        result: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}

        for tid, arts in articles_by_topic.items():
            for article in arts:
                title = article.get("title", "").strip()
                failed_reason = None

                if title in seen_titles:
                    failed_reason = "final_gate_duplicate"
                elif article.get("split_failed"):
                    failed_reason = "final_gate_unsplit"
                elif not article.get("topics"):
                    failed_reason = "final_gate_irrelevant"
                elif len(article.get("topics", [])) > 1:
                    failed_reason = "final_gate_multi_topic"

                if failed_reason:
                    deletion_log["final_gate"] = deletion_log.get("final_gate", 0) + 1
                    continue

                seen_titles.add(title)
                result[tid].append(article)

        removed = sum(len(arts) for arts in articles_by_topic.values()) - sum(len(a) for a in result.values())
        print(f"   🔍 Final QA gate: removed {removed} articles")
        return result

    def _t4_has_structure(self, article: Dict) -> bool:
        """（保留向后兼容，T4不再是展会）"""
        return True

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
        生成结构化 Markdown 日报。
        格式：ALERTS / Topic1 / Topic2 / Topic3[H/M/L] / Topic4[H/M/L] / QA报告
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

        # ── Topic 1: SEA 扩产 ────────────────────────────────────────────
        lines.extend(self._render_topic_flat(1, articles_by_topic.get(1, [])))

        # ── Topic 2: SEA 新建厂 ──────────────────────────────────────────
        lines.extend(self._render_topic_flat(2, articles_by_topic.get(2, [])))

        # ── Topic 3: 产品发布（含优先级分层）───────────────────────────────
        lines.extend(self._render_topic_tiered(3, articles_by_topic.get(3, [])))

        # ── Topic 4: 新技术/材料（含优先级分层）──────────────────────────────
        lines.extend(self._render_topic_tiered(4, articles_by_topic.get(4, [])))

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
        lines.append(f"  - 半导体行业排除：{deletion_log.get('semiconductor', 0)}")
        lines.append(f"  - 重复（URL/标题/语义）：{deletion_log.get('duplicate', 0) + deletion_log.get('semantic_duplicate', 0)}")
        lines.append(f"  - 聚合无法拆分：{deletion_log.get('unsplit', 0)}")
        lines.append(f"  - 最终清洗关卡：{deletion_log.get('final_gate', 0)}")
        lines.append("")

        qa = self._perform_qa(articles_by_topic)
        dup_status = "✅ 通过" if qa["no_duplicates"] else f"❌ 发现 {qa['duplicate_count']} 条重复"
        lines.append(f"- **重复检测**：{dup_status}")
        lines.append(f"- **数据完整性**：{qa['completeness_note']}")
        if qa.get("risk_points"):
            lines.append(f"- **风险点**：")
            for risk in qa["risk_points"]:
                lines.append(f"  - {risk}")
        lines.append("")

        return "\n".join(lines)

    def generate_markdown(self, articles: List[Dict], stats: Dict = None) -> str:
        raw_count = stats.get("total_before", len(articles)) if stats else len(articles)
        return self.generate_structured_markdown(articles, stats, raw_count)

    def generate_html(self, articles: Union[List[Dict], str], stats: Dict = None) -> str:
        """生成 HTML 报告（用于邮件）"""
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

        topic_html_parts = []
        # Topic 1 & 2: flat list
        for tid in [1, 2]:
            arts = articles_by_topic.get(tid, [])
            if not arts:
                continue
            cards = "".join(self._format_article_card(a, tid) for a in arts[:20])
            topic_html_parts.append(f"""
            <div class="topic-section">
                <h2 class="topic-title">{self.TOPIC_EMOJIS[tid]} Topic {tid} — {self.TOPIC_NAMES[tid]}</h2>
                <div class="articles-grid">{cards}</div>
            </div>""")

        # Topic 3 & 4: tiered
        for tid in [3, 4]:
            arts = articles_by_topic.get(tid, [])
            if not arts:
                continue
            priority_key = "t3_priority" if tid == 3 else "t4_priority"
            tiers = {"high": [], "med": [], "low": []}
            for a in arts:
                tiers[a.get(priority_key, "low")].append(a)

            tier_html = ""
            # Topic3: Low先于Med（价格信息更具采购参考价值）
            display_order = ["high", "low", "med"] if tid == 3 else ["high", "med", "low"]
            for tier_name in display_order:
                tier_arts = tiers[tier_name]
                if not tier_arts:
                    continue
                tier_label = {"high": "🔴 High Priority", "med": "🟡 Med Priority", "low": "🟢 Low Priority"}[tier_name]
                cards = "".join(self._format_article_card(a, tid) for a in tier_arts[:15])
                tier_html += f'<div class="tier-header">{tier_label}</div><div class="articles-grid">{cards}</div>'

            topic_html_parts.append(f"""
            <div class="topic-section">
                <h2 class="topic-title">{self.TOPIC_EMOJIS[tid]} Topic {tid} — {self.TOPIC_NAMES[tid]}</h2>
                {tier_html}
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
.tier-header{{padding:10px 24px;font-weight:600;font-size:.9em;background:#f5f5f5;color:#444}}
.articles-grid{{padding:16px 24px;display:flex;flex-direction:column;gap:12px}}
.article-card{{border:1px solid #e8e8e8;border-radius:10px;padding:14px;border-left:4px solid #1428a0}}
.article-card.priority-high{{border-left-color:#c0392b;background:#fffaf8}}
.article-card.priority-med{{border-left-color:#e67e22}}
.article-card.priority-low{{border-left-color:#27ae60}}
.article-meta{{font-size:.75em;color:#888;margin-bottom:6px}}
.article-title{{font-weight:600;margin-bottom:6px}}
.article-title a{{color:#1a1a3e;text-decoration:none}}
.article-title a:hover{{color:#1428a0;text-decoration:underline}}
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
    🤖 CE Intelligence System v7.1 · 单一归属 · 强QA · 低幻觉 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  </div>
</div>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Markdown 渲染辅助
    # ------------------------------------------------------------------

    def _render_topic_flat(self, tid: int, articles: List[Dict]) -> List[str]:
        """Topic 1/2: 无优先级分层，直接列出"""
        emoji = self.TOPIC_EMOJIS[tid]
        name  = self.TOPIC_NAMES[tid]
        name_zh = self.TOPIC_NAMES_ZH[tid]
        lines = []
        lines.append(f"## {emoji} Topic {tid}. {name}")
        lines.append(f"> {name_zh}")
        lines.append("")
        if not articles:
            lines.append("_今日无相关新闻_")
        else:
            for article in articles:
                lines.extend(self._format_article_md(article, tid))
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines

    def _render_topic_tiered(self, tid: int, articles: List[Dict]) -> List[str]:
        """Topic 3/4: 按 High/Med/Low 分层输出"""
        emoji = self.TOPIC_EMOJIS[tid]
        name  = self.TOPIC_NAMES[tid]
        name_zh = self.TOPIC_NAMES_ZH[tid]
        priority_key = "t3_priority" if tid == 3 else "t4_priority"

        tiers: Dict[str, List[Dict]] = {"high": [], "med": [], "low": []}
        for article in articles:
            p = article.get(priority_key, "low")
            if p in tiers:
                tiers[p].append(article)
            else:
                tiers["low"].append(article)

        lines = []
        lines.append(f"## {emoji} Topic {tid}. {name}")
        lines.append(f"> {name_zh}")
        lines.append("")

        if not articles:
            lines.append("_今日无相关新闻_")
            lines.append("")
            lines.append("---")
            lines.append("")
            return lines

        tier_labels = {
            "high": "### [High Priority]",
            "med":  "### [Med Priority]",
            "low":  "### [Low Priority]"
        }
        # Topic3: Low(价格/传言) 先于 Med(评测) 显示，因价格信息更具采购参考价值
        display_order = ["high", "low", "med"] if tid == 3 else ["high", "med", "low"]

        for tier_name in display_order:
            tier_arts = tiers[tier_name]
            lines.append(tier_labels[tier_name])
            lines.append("")
            if not tier_arts:
                lines.append("_暂无_")
                lines.append("")
            else:
                for article in tier_arts:
                    lines.extend(self._format_article_md(article, tid))

        lines.append("---")
        lines.append("")
        return lines

    def _format_article_md(self, article: Dict, topic_id: int) -> List[str]:
        """
        格式化单条新闻（参照 Topic structure.docx 格式）：
        <Date> · <Source>
        [产品类别] <Title>
        <Summary>
        """
        title    = article.get("title", "无标题")
        source   = article.get("source", "未知来源")
        link     = article.get("link", article.get("url", "#"))
        summary  = article.get("summary", article.get("content", ""))
        pub_date = self._format_date(article.get("published_date"))
        unreliable = article.get("source_unreliable", False)

        lines = []

        # 产品类别标签 (T3)
        if topic_id == 3:
            cat = article.get("product_category", "")
            title_display = f"[{cat}] {title}" if cat else title
        else:
            title_display = title

        source_note = " ⚠️" if unreliable else ""
        lines.append(f"**{pub_date} · {source}{source_note}**")

        # 链接规则：仅当有真实 URL 时才生成超链接，无 URL → 纯文本（防止幻觉）
        has_url = link and link not in ("#", "", "unknown")
        if has_url:
            lines.append(f"[{title_display}]({link})")
        else:
            lines.append(title_display)

        if summary:
            clean = summary.strip()[:350].replace("\n", " ")
            lines.append(f"{clean}")
        lines.append("")
        return lines

    def _format_article_card(self, article: Dict, topic_id: int) -> str:
        """HTML 卡片"""
        title    = article.get("title", "无标题")
        link     = article.get("link", "#")
        source   = article.get("source", "未知来源")
        summary  = article.get("summary", "")
        pub_date = self._format_date(article.get("published_date"))

        priority_key = "t3_priority" if topic_id == 3 else "t4_priority"
        priority = article.get(priority_key, "")
        css_class = f"priority-{priority}" if priority else ""

        if topic_id == 3:
            cat = article.get("product_category", "")
            if cat:
                title = f"[{cat}] {title}"

        ai_summary = self._get_display_summary(article)

        return f"""
        <div class="article-card {css_class}">
          <div class="article-meta">{pub_date} · {self._escape_html(source)}</div>
          <div class="article-title"><a href="{link}" target="_blank">{self._escape_html(title)}</a></div>
          <div class="article-summary">{self._escape_html(ai_summary)}</div>
        </div>"""

    def _get_display_summary(self, article: Dict) -> str:
        summary = article.get("summary", article.get("content", ""))
        if not summary:
            return article.get("title", "")
        return summary[:160] + ("..." if len(summary) > 160 else "")

    # ------------------------------------------------------------------
    # ALERTS
    # ------------------------------------------------------------------

    # 传言词 / 定价词（ALERTS 前置排除）
    ALERTS_EXCLUDE_RUMORS = [
        "rumor", "rumored", "leak", "leaked", "reportedly", "sources say",
        "allegedly", "renders", "said to", "expected to", "could launch",
        "传言", "曝光", "爆料", "据传", "渲染图", "疑似", "泄露"
    ]
    ALERTS_EXCLUDE_PRICING = [
        "price", "pricing", "discount", "deal", "off,", "% off", "starts at",
        "available for", "备件价格", "售价", "定价", "优惠", "折扣"
    ]

    def _collect_alerts(self, articles_by_topic: Dict[int, List[Dict]]) -> List[str]:
        """
        收集高优先级警报。
        前置排除：传言文章 / 定价文章 / 优先级非 High 的 Topic3 文章
        正式条件：满足 ≥2 个判断维度
        """
        alerts = []
        seen = set()
        for tid in range(1, 5):
            for article in articles_by_topic.get(tid, []):
                title = article.get("title", "")
                if title in seen:
                    continue

                text = (title + " " + article.get("summary", "")).lower()

                # 前置排除1：传言文章
                if any(kw.lower() in text for kw in self.ALERTS_EXCLUDE_RUMORS):
                    continue
                # 前置排除2：定价/折扣文章
                if any(kw.lower() in text for kw in self.ALERTS_EXCLUDE_PRICING):
                    continue
                # 前置排除3：Topic3 必须是 High Priority 才能进 ALERTS
                if tid == 3 and article.get("t3_priority", "low") != "high":
                    continue

                if self._count_alert_criteria(article) >= 2:
                    seen.add(title)
                    alerts.append(f"[Topic{tid}] {title}（{article.get('source', '')}）")
        return alerts[:10]

    def _count_alert_criteria(self, article: Dict) -> int:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        return sum(
            1 for keywords in self.ALERT_CRITERIA.values()
            if any(kw.lower() in text for kw in keywords)
        )

    # ------------------------------------------------------------------
    # 格式化工具
    # ------------------------------------------------------------------

    def _group_by_topic(self, articles: List[Dict]) -> Dict[int, List[Dict]]:
        result: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}
        for article in articles:
            for tid in article.get("topics", []):
                if tid in result and article not in result[tid]:
                    result[tid].append(article)
        return result

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
<html><head><meta charset="UTF-8"><title>CE Intelligence Report</title></head>
<body style="font-family:Arial,sans-serif;padding:20px;max-width:900px;margin:auto">
{md_escaped}
</body></html>"""

    # ------------------------------------------------------------------
    # QA 验证
    # ------------------------------------------------------------------

    def _perform_qa(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict:
        all_titles = []
        missing_source = 0
        risk_points = []

        for tid, arts in articles_by_topic.items():
            for a in arts:
                all_titles.append(a.get("title", ""))
                if not a.get("source") or a.get("source") == "unknown":
                    missing_source += 1

        unique_titles = set(all_titles)
        duplicate_count = len(all_titles) - len(unique_titles)

        if duplicate_count > 0:
            risk_points.append(f"发现 {duplicate_count} 条重复标题")
        if missing_source > 0:
            risk_points.append(f"{missing_source} 条新闻来源不明")

        completeness_note = (
            f"✅ 所有新闻均有来源；共 {len(all_titles)} 条"
            if missing_source == 0
            else f"⚠️ 共 {len(all_titles)} 条，其中 {missing_source} 条来源缺失"
        )

        return {
            "no_duplicates": duplicate_count == 0,
            "duplicate_count": duplicate_count,
            "completeness_note": completeness_note,
            "risk_points": risk_points
        }
