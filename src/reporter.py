#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Generator for Samsung CE Intelligence
Generates professional HTML and Markdown reports with AI-powered summaries
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Any, Union
from collections import defaultdict
import openai

class ReportGenerator:
    """Generate formatted reports with AI summaries for each news item"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.topic_names = {
            1: "竞品动态 — Competitor Technology & Product Moves",
            2: "新兴技术与材料 — Emerging Tech, Materials & CMF Design",
            3: "东南亚/印度制造 — Manufacturing SEA / India",
            4: "行业展会 — Industry Events",
            5: "供应链风险 — Supply Chain Risks",
            6: "成本与大宗商品 — Cost & Commodity Trends",
            7: "AI与智能家居 — AI & Software in CE",
            8: "市场情报与政策 — Market Intelligence & Policy"
        }
        
        # Impact level mapping
        self.impact_levels = {
            'high': '🔴 HIGH',
            'medium': '🟡 MED',
            'low': '🟢 LOW'
        }
        
        # Initialize AI for summarization
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.ai_enabled = bool(self.api_key)
        if self.ai_enabled:
            openai.api_key = self.api_key
            openai.api_base = "https://api.deepseek.com/v1"
    
    def _generate_ai_summary(self, title: str, content: str, impact_level: str = "medium") -> str:
        """Generate AI-powered summary for a single news item"""
        if not self.ai_enabled or not content:
            summary = content[:150] if content else title
            return summary + "..." if len(summary) >= 150 else summary
        
        try:
            emphasis = {
                'high': '重点突出其对三星的紧迫影响和行动建议。',
                'medium': '客观总结事件内容，说明对三星的潜在影响。',
                'low': '简要记录该动态，供参考跟踪。'
            }.get(impact_level, '客观总结该新闻的主要内容。')
            
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": f"""你是一个专业的消费电子行业分析师，为三星电子撰写情报简报。
                        请用简洁专业的中文，为以下新闻生成一段总结（1-2句话，50-80字）。
                        {emphasis}
                        总结格式：直接陈述事实和影响，不要使用"总结："、"本条新闻"等开头语。
                        重点突出：技术/产品名称、公司名称、对三星的具体影响。"""
                    },
                    {
                        "role": "user",
                        "content": f"标题：{title}\n\n内容：{content[:1500]}"
                    }
                ],
                temperature=0.3,
                max_tokens=120
            )
            
            summary = response.choices[0].message.content.strip()
            return summary
            
        except Exception as e:
            print(f"⚠️ AI summary failed for '{title[:50]}': {e}")
            first_sentence = content.split('。')[0] if content else title
            return first_sentence[:120] + ("..." if len(first_sentence) > 120 else "")
    
    def _determine_impact(self, article: Dict, topic_id: int) -> str:
        """Determine impact level based on content and topic"""
        text = (article.get('title', '') + ' ' + article.get('summary', '')).lower()
        
        high_keywords = [
            '发布', '推出', '上市', '价格', '降价', '市场份额', '超越', '首次',
            '突破', '革命性', '颠覆', '关税', '制裁', '断供', '短缺',
            '越南', '印度', '工厂', '投资', '扩产', '战略合作'
        ]
        
        medium_keywords = [
            '升级', '改进', '优化', '展示', '亮相', '参展', '论坛',
            '趋势', '预测', '增长', '下降', '调整', '政策'
        ]
        
        topic_high = [1, 3, 5, 6]
        
        score = 0
        for kw in high_keywords:
            if kw in text:
                score += 2
        for kw in medium_keywords:
            if kw in text:
                score += 1
        
        if topic_id in topic_high:
            score += 1
        
        reliability = article.get('reliability_score', 0.6)
        if reliability >= 0.9:
            score += 1
        
        if score >= 3:
            return 'high'
        elif score >= 1:
            return 'medium'
        else:
            return 'low'
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                    .replace('"', '&quot;')
                    .replace("'", '&#39;'))
    
    def generate_markdown(self, articles: List[Dict], stats: Dict = None) -> str:
        """Generate Markdown report (simplified version for backup)"""
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        report = f"""# Samsung CE Intelligence Brief
**Date:** {date_str}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary
- **Total unique articles:** {len(articles)}
- **Duplicates removed:** {stats.get('duplicates_removed', 0) if stats else 0}

"""
        return report
    
    def generate_html(self, articles: Union[List[Dict], str], stats: Dict = None) -> str:
        """
        Generate professional HTML report with AI summaries
        
        Args:
            articles: List of article dictionaries OR markdown string (fallback)
            stats: Optional statistics dictionary
        """
        # Handle fallback case (when markdown string is passed)
        if isinstance(articles, str):
            print("⚠️ generate_html received markdown string, returning simple HTML")
            return self._markdown_to_html(articles)
        
        # Normal case: articles is a list
        if not articles:
            return "<html><body><h1>No articles found</h1></body></html>"
        
        date_str = datetime.now().strftime('%Y-%m-%d')
        date_display = datetime.now().strftime('%B %d, %Y')
        
        # Group articles by topic
        articles_by_topic = defaultdict(list)
        for article in articles:
            for topic_id in article.get('topics', []):
                if topic_id in self.topic_names:
                    articles_by_topic[topic_id].append(article)
        
        # Calculate statistics
        total_articles = len(articles)
        topic_stats = {tid: len(articles_by_topic[tid]) for tid in self.topic_names}
        
        # Count by impact level
        impact_counts = {'high': 0, 'medium': 0, 'low': 0}
        for topic_id, topic_articles in articles_by_topic.items():
            for article in topic_articles:
                impact = self._determine_impact(article, topic_id)
                impact_counts[impact] += 1
        
        # Generate HTML for each topic
        topic_html = []
        for topic_id in range(1, 9):
            if topic_id not in articles_by_topic or not articles_by_topic[topic_id]:
                continue
            
            topic_articles = articles_by_topic[topic_id]
            # Sort by impact (high first)
            topic_articles.sort(key=lambda x: (
                0 if self._determine_impact(x, topic_id) == 'high' 
                else 1 if self._determine_impact(x, topic_id) == 'medium' 
                else 2
            ))
            
            articles_html = []
            for idx, article in enumerate(topic_articles[:25]):
                articles_html.append(self._format_article_card(article, idx, topic_id))
            
            topic_html.append(f"""
            <div class="topic-section">
                <h2 class="topic-title">T{topic_id} — {self.topic_names[topic_id]}</h2>
                <div class="impact-summary">
                    <span>🔴 HIGH · 🟡 MED · 🟢 LOW · {len(topic_articles)} items</span>
                </div>
                <div class="articles-grid">
                    {''.join(articles_html)}
                </div>
            </div>
            """)
        
        # Generate priority alerts section
        high_impact_alerts = []
        for topic_id, topic_articles in articles_by_topic.items():
            for article in topic_articles[:3]:
                if self._determine_impact(article, topic_id) == 'high':
                    title = article.get('title', '')[:100]
                    summary = self._generate_ai_summary(
                        article.get('title', ''), 
                        article.get('summary', ''),
                        'high'
                    )[:150]
                    high_impact_alerts.append(f"""
                    <div class="alert-item">
                        <span class="alert-badge">🔴 HIGH</span>
                        <span class="alert-text">{self._escape_html(title)} — {self._escape_html(summary)}</span>
                    </div>
                    """)
        
        alerts_html = ''.join(high_impact_alerts[:8]) if high_impact_alerts else '<div class="alert-item">无高优先级警报</div>'
        
        # Complete HTML template
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Samsung CE Intelligence - {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f0f2f5;
            padding: 20px;
            line-height: 1.5;
            color: #1a1a2e;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .header {{
            background: linear-gradient(135deg, #0a0e27 0%, #1a1a3e 100%);
            color: white;
            padding: 30px 40px;
            border-radius: 16px 16px 0 0;
            margin-bottom: 0;
        }}
        
        .header h1 {{
            font-size: 1.8em;
            font-weight: 600;
            margin-bottom: 8px;
        }}
        
        .header .subtitle {{
            color: #a0a0c0;
            font-size: 0.9em;
            margin-bottom: 20px;
        }}
        
        .header .date {{
            color: #ffd700;
            font-size: 1em;
            margin-top: 10px;
        }}
        
        .stats-bar {{
            background: white;
            padding: 20px 40px;
            border-radius: 0 0 16px 16px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }}
        
        .stats-grid {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}
        
        .stat-item {{
            text-align: center;
        }}
        
        .stat-number {{
            font-size: 1.8em;
            font-weight: 700;
            color: #1a1a3e;
        }}
        
        .stat-label {{
            font-size: 0.8em;
            color: #666;
        }}
        
        .impact-stats {{
            display: flex;
            gap: 20px;
        }}
        
        .impact-stat {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9em;
        }}
        
        .alerts-section {{
            background: #fff3e0;
            border-left: 4px solid #ff6b35;
            padding: 20px 30px;
            margin-bottom: 30px;
            border-radius: 12px;
        }}
        
        .alerts-title {{
            font-weight: 700;
            font-size: 1.1em;
            margin-bottom: 15px;
            color: #c0392b;
        }}
        
        .alert-item {{
            padding: 10px 0;
            border-bottom: 1px solid #ffe0b3;
            font-size: 0.9em;
        }}
        
        .alert-item:last-child {{
            border-bottom: none;
        }}
        
        .alert-badge {{
            background: #c0392b;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.7em;
            font-weight: 600;
            margin-right: 12px;
            display: inline-block;
        }}
        
        .topic-section {{
            background: white;
            border-radius: 16px;
            margin-bottom: 30px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        
        .topic-title {{
            background: linear-gradient(135deg, #1428a0 0%, #0f1a5e 100%);
            color: white;
            padding: 18px 25px;
            font-size: 1.2em;
            font-weight: 600;
            margin: 0;
        }}
        
        .impact-summary {{
            padding: 12px 25px;
            background: #f8f9fa;
            border-bottom: 1px solid #e0e0e0;
            font-size: 0.8em;
            color: #666;
        }}
        
        .articles-grid {{
            padding: 20px 25px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        
        .article-card {{
            border: 1px solid #e8e8e8;
            border-radius: 12px;
            padding: 18px 20px;
            transition: all 0.2s ease;
            background: #fff;
        }}
        
        .article-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-color: #1428a0;
        }}
        
        .article-card.impact-high {{
            border-left: 4px solid #c0392b;
            background: #fffaf8;
        }}
        
        .article-card.impact-medium {{
            border-left: 4px solid #e67e22;
        }}
        
        .article-card.impact-low {{
            border-left: 4px solid #27ae60;
        }}
        
        .article-header {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        
        .impact-badge {{
            font-size: 0.7em;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            background: #f0f0f0;
        }}
        
        .article-card.impact-high .impact-badge {{
            background: #c0392b;
            color: white;
        }}
        
        .article-card.impact-medium .impact-badge {{
            background: #e67e22;
            color: white;
        }}
        
        .article-card.impact-low .impact-badge {{
            background: #27ae60;
            color: white;
        }}
        
        .article-date {{
            font-size: 0.7em;
            color: #999;
        }}
        
        .article-source {{
            font-size: 0.7em;
            color: #666;
            background: #f5f5f5;
            padding: 2px 8px;
            border-radius: 4px;
        }}
        
        .article-title {{
            font-size: 1em;
            font-weight: 600;
            margin-bottom: 10px;
        }}
        
        .article-title a {{
            color: #1a1a3e;
            text-decoration: none;
        }}
        
        .article-title a:hover {{
            color: #1428a0;
            text-decoration: underline;
        }}
        
        .article-summary {{
            font-size: 0.85em;
            color: #444;
            line-height: 1.5;
            margin-bottom: 12px;
        }}
        
        .article-footer {{
            text-align: right;
        }}
        
        .source-link {{
            font-size: 0.75em;
            color: #1428a0;
            text-decoration: none;
        }}
        
        .source-link:hover {{
            text-decoration: underline;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: #888;
            font-size: 0.75em;
            border-top: 1px solid #e0e0e0;
            margin-top: 20px;
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}
            .header, .stats-bar {{
                padding: 20px;
            }}
            .articles-grid {{
                padding: 15px;
            }}
            .stats-grid {{
                gap: 15px;
            }}
            .stat-number {{
                font-size: 1.2em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Samsung Electronics · CE Strategic Sourcing</h1>
            <div class="subtitle">Daily Technology &amp; Sourcing Intelligence</div>
            <div class="subtitle">Competitor · Tech · Materials · CMF · Thermal · Manufacturing · Supply Chain · AI · Market</div>
            <div class="date">{date_display}</div>
        </div>
        
        <div class="stats-bar">
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">{total_articles}</div>
                    <div class="stat-label">Articles</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{len([t for t in topic_stats if topic_stats[t] > 0])}</div>
                    <div class="stat-label">Topics</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">T1–T8</div>
                    <div class="stat-label">HIGH→MED→LOW</div>
                </div>
            </div>
            <div class="impact-stats">
                <div class="impact-stat"><span style="color:#c0392b">🔴 HIGH</span> {impact_counts.get('high', 0)}</div>
                <div class="impact-stat"><span style="color:#e67e22">🟡 MED</span> {impact_counts.get('medium', 0)}</div>
                <div class="impact-stat"><span style="color:#27ae60">🟢 LOW</span> {impact_counts.get('low', 0)}</div>
            </div>
        </div>
        
        <div class="alerts-section">
            <div class="alerts-title">🔴 ALERTS — 今日高优先级情报</div>
            {alerts_html}
        </div>
        
        {''.join(topic_html)}
        
        <div class="footer">
            <p>🤖 Generated by Samsung CE Intelligence System · AI-powered summaries</p>
            <p>📡 Multi-source aggregation with 3-layer deduplication · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>"""
    
    def _format_article_card(self, article: Dict, index: int, topic_id: int) -> str:
        """Format a single article as an HTML card"""
        title = article.get('title', '无标题')
        summary = article.get('summary', article.get('content', ''))
        link = article.get('link', '#')
        source = article.get('source', '未知来源')
        
        impact = self._determine_impact(article, topic_id)
        ai_summary = self._generate_ai_summary(title, summary, impact)
        impact_display = self.impact_levels.get(impact, '🟡 MED')
        
        pub_date = article.get('published_date')
        date_str = ""
        if pub_date:
            if isinstance(pub_date, datetime):
                date_str = pub_date.strftime('%Y-%m-%d')
            elif isinstance(pub_date, str):
                date_str = pub_date[:10]
        
        return f"""
        <div class="article-card impact-{impact}">
            <div class="article-header">
                <span class="impact-badge">{impact_display}</span>
                <span class="article-date">{date_str}</span>
                <span class="article-source">📎 {self._escape_html(source)}</span>
            </div>
            <div class="article-title">
                <a href="{link}" target="_blank" rel="noopener noreferrer">{self._escape_html(title)}</a>
            </div>
            <div class="article-summary">
                {self._escape_html(ai_summary)}
            </div>
            <div class="article-footer">
                <a href="{link}" class="source-link" target="_blank">🔗 Read Source Article</a>
            </div>
        </div>
        """
    
    def _markdown_to_html(self, md: str) -> str:
        """Convert markdown to simple HTML (fallback)"""
        md = md.replace('\n', '<br>')
        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Report</title></head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
{md}
</body>
</html>"""
