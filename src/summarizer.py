#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Article Summarizer for CE Intelligence
Version: 5.0 - 情报导向摘要（中文输出 + 低幻觉）
"""

import os
import re
from typing import Optional
import openai


class ArticleSummarizer:
    """为消费电子情报日报生成高质量中文摘要"""

    SYSTEM_PROMPT = """你是消费电子行业资深情报分析师。
你的任务是将新闻内容提炼为2-3句简洁专业的中文情报摘要（总字数50-100字）。

输出规范：
- 直接陈述事实，不使用"总结："、"该文章表明"等开头语
- 必须包含：关键主体（公司/产品/技术名称）、核心事件、行业影响
- 若来源不确定或信息不足，请标注"（信息待核实）"
- 不添加原文中没有的信息（低幻觉原则）
- 输出中文

格式：[核心事件]. [具体数据/细节]. [行业影响/启示].
"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.enabled = bool(self.api_key)

        if self.enabled:
            openai.api_key = self.api_key
            openai.api_base = "https://api.deepseek.com/v1"
            print("✅ Summarizer: DeepSeek API ready")
        else:
            print("⚠️ Summarizer: No API key, using fallback")

    def summarize(self, title: str, content: str, max_length: int = 200) -> str:
        """
        生成新闻摘要

        Args:
            title: 文章标题
            content: 文章内容
            max_length: 最大摘要字符数

        Returns:
            中文摘要字符串（2-3句，50-100字）
        """
        if not self.enabled:
            return self._fallback_summary(title, content, max_length)

        truncated = content[:2000] if content else title

        try:
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"标题：{title}\n\n内容：{truncated}"}
                ],
                temperature=0.25,
                max_tokens=180
            )
            summary = response.choices[0].message.content.strip()
            summary = re.sub(r"\s+", " ", summary)
            if len(summary) > max_length:
                summary = summary[:max_length - 3] + "..."
            return summary

        except Exception as e:
            print(f"⚠️ Summarization failed for '{title[:40]}': {e}")
            return self._fallback_summary(title, content, max_length)

    def _fallback_summary(self, title: str, content: str, max_length: int) -> str:
        """API不可用时的降级摘要"""
        if content:
            sentences = re.split(r"[。！？.!?]+", content)
            summary = "。".join(s.strip() for s in sentences[:2] if s.strip())
            if not summary:
                summary = content
        else:
            summary = title

        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        return summary.strip()

    def summarize_batch(self, articles: list, limit: int = 60) -> list:
        """批量生成摘要"""
        for article in articles[:limit]:
            current_summary = article.get("summary", "")
            if not current_summary or len(current_summary) < 60:
                article["summary"] = self.summarize(
                    article.get("title", ""),
                    article.get("content", current_summary)
                )
        return articles
