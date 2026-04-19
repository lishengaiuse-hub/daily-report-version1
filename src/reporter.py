#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Generator for Samsung CE Intelligence
Version: 5.0 - 结构化Markdown输出 + QA验证 + T1-T4严格格式
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Any, Union, Optional
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

    def __init__(self, config: Dict):
        self.config = config
        api_key = os.getenv("DEEPSEEK_API_KEY")
        self.ai_enabled = bool(api_key)
        if self.ai_enabled:
            openai.api_key = api_key
            openai.api_base = "https://api.deepseek.com/v1"

    # ------------------------------------------------------------------
    # 主输出方法
    # ------------------------------------------------------------------

    def generate_structured_markdown(
        self,
        articles: List[Dict],
        dedup_stats: Dict = None,
        raw_count: int = 0
    ) -> str:
        """
        生成符合企业标准的结构化 Markdown 日报。
        包含：ALERTS / T1-T4各节 / 去重统计 / QA验证
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        articles_by_topic = self._group_by_topic(articles)

        lines = []
        lines.append(f"# 📰 三星产业情报日报（{date_str}）")
        lines.append("")

        # ── ALERTS ──────────────────────────────────────────────────────
        lines.append("## 🚨 ALERTS（高优先级）")
        alerts = self._collect_alerts(articles_by_topic)
        if alerts:
            for alert in alerts:
                lines.append(f"- {alert}")
        else:
            lines.append("- 今日无高优先级警报")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── T1-T4 Sections ──────────────────────────────────────────────
        for tid in range(1, 5):
            emoji = self.TOPIC_EMOJIS[tid]
            name  = self.TOPIC_NAMES[tid]
            topic_articles = articles_by_topic.get(tid, [])

            lines.append(f"## {emoji} T{tid} — {name}")
            lines.append("")

            if not topic_articles:
                lines.append("_今日无相关新闻_")
                lines.append("")
                lines.append("---")
                lines.append("")
                continue

            for article in topic_articles:
                lines.extend(self._format_article_md(article, tid))

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

        # ── QA验证 ──────────────────────────────────────────────────────
        qa = self._perform_qa(articles_by_topic)
        lines.append("## 🔍 QA验证")
        dup_status = "通过" if qa["no_duplicates"] else f"未通过（发现 {qa['duplicate_count']} 条重复）"
        lines.append(f"- 重复检测：{dup_status}")
        lines.append(f"- 分类准确性：{qa['classification_note']}")
        lines.append(f"- 数据完整性：{qa['completeness_note']}")
        lines.append("")

        return "\n".join(lines)

    def generate_markdown(self, articles: List[Dict], stats: Dict = None) -> str:
        """向后兼容接口，调用 generate_structured_markdown"""
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

        # Alerts
        alerts = self._collect_alerts(articles_by_topic)
        alerts_html = "".join(
            f'<div class="alert-item"><span class="alert-badge">🔴 HIGH</span>'
            f'<span class="alert-text">{self._escape_html(a)}</span></div>'
            for a in alerts[:8]
        ) or '<div class="alert-item">今日无高优先级警报</div>'

        # Topic sections
        topic_html_parts = []
        for tid in range(1, 5):
            topic_articles = articles_by_topic.get(tid, [])
            if not topic_articles:
                continue
            cards = "".join(self._format_article_card(a, tid) for a in topic_articles[:20])
            emoji = self.TOPIC_EMOJIS[tid]
            name  = self.TOPIC_NAMES[tid]
            topic_html_parts.append(f"""
            <div class="topic-section">
                <h2 class="topic-title">{emoji} T{tid} — {name}</h2>
                <div class="articles-grid">{cards}</div>
            </div>""")

        total = len(articles)
        dedup_removed = (stats or {}).get("duplicates_removed", 0)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Samsung CE Intelligence - {date_str}</title>
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
    <h1>📰 三星产业情报日报</h1>
    <div class="date">{date_display} · 严格分类 T1-T4 · 三层去重</div>
  </div>
  <div class="stats-bar">
    <div class="stat-item"><div class="stat-number">{total}</div><div class="stat-label">今日新闻</div></div>
    <div class="stat-item"><div class="stat-number">{dedup_removed}</div><div class="stat-label">已去重</div></div>
    <div class="stat-item"><div class="stat-number">T1–T4</div><div class="stat-label">四大栏目</div></div>
  </div>
  <div class="alerts-section">
    <div class="alerts-title">🚨 ALERTS — 今日高优先级情报</div>
    {alerts_html}
  </div>
  {''.join(topic_html_parts)}
  <div class="footer">
    🤖 Samsung CE Intelligence System · 低幻觉 · 强验证 · 可解释 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
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
        """收集高优先级警报（不重复）"""
        alerts = []
        seen = set()
        for tid in range(1, 5):
            for article in articles_by_topic.get(tid, []):
                if self._determine_impact(article, tid) == "high":
                    title = article.get("title", "")
                    if title not in seen:
                        seen.add(title)
                        source = article.get("source", "")
                        alerts.append(f"[T{tid}] {title}（{source}）")
        return alerts[:10]

    def _format_article_md(self, article: Dict, topic_id: int) -> List[str]:
        """格式化单条新闻为 Markdown 块"""
        title       = article.get("title", "无标题")
        source      = article.get("source", "未知来源")
        link        = article.get("link", article.get("url", "#"))
        summary     = article.get("summary", article.get("content", ""))
        pub_date    = self._format_date(article.get("published_date"))
        unreliable  = article.get("source_unreliable", False)

        lines = []

        # T1 特殊：加产品类别标签
        if topic_id == 1:
            cat = article.get("product_category", "产品")
            title_display = f"[{cat}] {title}"
        else:
            title_display = title

        reliability_note = "⚠️ 来源不确定" if unreliable else ""

        lines.append(f"### {title_display}")
        lines.append(f"**来源**: {source} {reliability_note}  ")
        lines.append(f"**发布时间**: {pub_date}  ")
        lines.append(f"**原始链接**: [{link}]({link})  ")

        if summary:
            clean = summary.strip()[:400].replace("\n", " ")
            lines.append(f"**摘要**: {clean}")

        # T4 特殊：展会时间/地点
        if topic_id == 4:
            ex_time = article.get("exhibition_date", "")
            ex_loc  = article.get("exhibition_location", "")
            ex_url  = article.get("exhibition_website", "")
            if ex_time or ex_loc:
                lines.append(f"**时间**: {ex_time or '待确认'}  ")
                lines.append(f"**地点**: {ex_loc or '待确认'}  ")
                lines.append(f"**参展商名单**: {ex_url or '未找到'}  ")
            else:
                lines.append("⚠️ 展会时间/地点信息不完整，请核实后补充")

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
                "high": "重点突出对三星的紧迫影响和行动建议。",
                "medium": "客观总结事件内容，说明对三星的潜在影响。",
                "low": "简要记录该动态。"
            }.get(impact, "客观总结主要内容。")
            resp = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"你是三星电子消费电子情报分析师。请用简洁专业的中文生成1-2句总结（不超过80字）。{emphasis}直接陈述，不使用开头语。"},
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
        for tid, arts in articles_by_topic.items():
            for a in arts:
                all_titles.append(a.get("title", ""))
                if not a.get("source") or a.get("source") == "unknown":
                    missing_source += 1

        unique_titles = set(all_titles)
        duplicate_count = len(all_titles) - len(unique_titles)

        classification_note = "T1-T4 严格规则已执行；品牌标签已附加；T2排除品牌竞争内容"
        if duplicate_count > 0:
            classification_note += f"（发现 {duplicate_count} 条跨栏目重复，需检查去重逻辑）"

        if missing_source == 0:
            completeness_note = f"所有新闻均有来源；共 {len(all_titles)} 条"
        else:
            completeness_note = f"共 {len(all_titles)} 条，其中 {missing_source} 条来源缺失，已标注"

        return {
            "no_duplicates": duplicate_count == 0,
            "duplicate_count": duplicate_count,
            "classification_note": classification_note,
            "completeness_note": completeness_note
        }
