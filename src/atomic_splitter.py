#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atomic News Splitter - 将聚合新闻强制拆分为独立原子新闻
Version: 5.0 - 更激进的拆分策略 + 内容级别分段
"""

import re
from typing import List, Dict, Any, Optional


class AtomicSplitter:
    """
    强制将聚合新闻拆分为独立原子新闻。

    处理场景：
    1. 标题即聚合标志（晚报/早报/合集）
    2. 内容包含多个独立事件（按序号/分隔符分段）
    3. 单条新闻含多家公司或多个产品的并列报道
    """

    # 聚合新闻标题模式
    AGGREGATE_TITLE_PATTERNS = [
        r"早报|晚报|日报|周报|月报|速递|快讯|要闻",
        r"8点1氪|晚报|合集|汇总|简报|一句话新闻|今日新闻",
        r"morning brief|daily brief|news digest|roundup|weekly wrap",
    ]

    # 内容分隔符（优先尝试更明确的分隔符）
    SEPARATOR_PATTERNS = [
        (r"(?:\d+[、.。）)]\s*){1}", "numbered"),       # 1. 2. 3. / 1、2、
        (r"[①②③④⑤⑥⑦⑧⑨⑩]", "circled"),              # 带圈数字
        (r"【([^】]+)】", "bracket"),                   # 【标题】
        (r"\n\s*[-•●▶]\s+", "bullet"),                  # 项目符号
        (r"\n\s*\n", "double_newline"),                  # 双换行
        (r"[；;]\s*(?=[^\s])", "semicolon"),             # 分号（后面有内容）
        (r"[丨|｜]\s*", "pipe"),                         # 中文管道符
    ]

    # 最小有效片段字数
    MIN_SEGMENT_LENGTH = 25

    # 最小独立新闻字数（太短则不拆分）
    MIN_ARTICLE_LENGTH = 50

    def __init__(self):
        self.stats = {"input": 0, "split": 0, "output": 0, "deleted_unsplit": 0}

    def is_aggregate(self, title: str, content: str = "") -> bool:
        """判断是否为聚合新闻"""
        text = (title + " " + content[:200]).lower()
        for pattern in self.AGGREGATE_TITLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def split_article(self, article: Dict) -> List[Dict]:
        """
        拆分单篇新闻。
        - 非聚合新闻：直接返回
        - 聚合新闻：拆分为多条原子新闻
        """
        self.stats["input"] += 1

        title   = article.get("title", "")
        content = article.get("summary", article.get("content", ""))

        if not self.is_aggregate(title, content):
            # 即使非聚合，也尝试内容级拆分
            segments = self._try_content_split(content)
            if len(segments) > 1:
                return self._build_atomic_articles(segments, article)
            self.stats["output"] += 1
            return [article]

        # 聚合新闻：强制拆分
        segments = self._split_content(content)
        if len(segments) <= 1:
            # 无法拆分 → 直接删除（不保留聚合原文）
            self.stats["deleted_unsplit"] += 1
            return []

        self.stats["split"] += 1
        atoms = self._build_atomic_articles(segments, article)
        self.stats["output"] += len(atoms)
        return atoms

    def _split_content(self, content: str) -> List[str]:
        """尝试多种分隔符拆分内容"""
        if not content:
            return []

        best_segments: List[str] = []
        best_count = 0

        for pattern, pattern_type in self.SEPARATOR_PATTERNS:
            try:
                segments = re.split(pattern, content)
                clean = [s.strip() for s in segments if s and len(s.strip()) >= self.MIN_SEGMENT_LENGTH]
                if len(clean) > best_count:
                    best_count = len(clean)
                    best_segments = clean
            except re.error:
                continue

        return best_segments if best_count > 1 else [content]

    def _try_content_split(self, content: str) -> List[str]:
        """对非聚合新闻尝试内容级拆分（发现明显列表结构时）"""
        if not content or len(content) < 200:
            return [content] if content else []

        # 仅对明显的编号列表进行拆分
        numbered = re.split(r"(?m)^\s*\d+[、.。）)]\s+", content)
        clean = [s.strip() for s in numbered if len(s.strip()) >= self.MIN_SEGMENT_LENGTH]
        if len(clean) > 2:
            return clean

        return [content]

    def _build_atomic_articles(self, segments: List[str], parent: Dict) -> List[Dict]:
        """将文本片段构建为独立新闻字典列表"""
        atoms = []
        for seg in segments:
            if len(seg) < self.MIN_ARTICLE_LENGTH:
                continue

            seg_title, seg_body = self._extract_title_body(seg)
            if not seg_title:
                seg_title = self._generate_title(seg)

            atom = {
                "title":        seg_title,
                "summary":      (seg_body or seg)[:500],
                "content":      seg_body or seg,
                "link":         parent.get("link", ""),
                "url":          parent.get("url", parent.get("link", "")),
                "source":       parent.get("source", "unknown"),
                "published_raw":    parent.get("published_raw", ""),
                "published_date":   parent.get("published_date"),
                "fetch_method":     "atomic_split",
                "parent_link":      parent.get("link", ""),
                "is_atomic":        True,
                "source_unreliable": parent.get("source_unreliable", False)
            }
            atoms.append(atom)

        return atoms if atoms else [parent]

    def _extract_title_body(self, segment: str) -> tuple:
        """从片段第一行尝试提取标题"""
        lines = [l.strip() for l in segment.strip().split("\n") if l.strip()]
        if not lines:
            return None, segment

        first = lines[0]
        # 第一行长度适中且不像句子结尾 → 作为标题
        if 8 <= len(first) <= 120 and not first.endswith(("。", "？", "！", ".", "?", "!")):
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""
            return first, body

        return None, segment

    def _generate_title(self, segment: str) -> str:
        """为无法提取标题的片段生成简短标题"""
        title = segment[:60].strip()
        title = re.sub(r"\s+", " ", title)
        if len(segment) > 60:
            title += "..."
        return title

    def split_batch(self, articles: List[Dict]) -> List[Dict]:
        """批量拆分"""
        result = []
        for article in articles:
            result.extend(self.split_article(article))

        print(f"✂️ Atomic Splitter: {self.stats['input']} in → {self.stats['output']} out "
              f"({self.stats['split']} aggregates split, {self.stats['deleted_unsplit']} unsplit deleted)")

        deleted = self.stats["deleted_unsplit"]
        self.stats = {"input": 0, "split": 0, "output": 0, "deleted_unsplit": 0}
        return result, deleted

    def get_stats(self) -> Dict:
        return self.stats
