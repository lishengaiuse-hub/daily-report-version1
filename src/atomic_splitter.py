#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atomic News Splitter - 将聚合新闻拆分为独立的原子新闻
解决：一条新闻包含多个事件的问题
"""

import re
from typing import List, Dict, Any, Optional


class AtomicSplitter:
    """将聚合新闻拆分为独立的原子新闻"""
    
    # 聚合新闻分隔符模式
    SEPARATOR_PATTERNS = [
        r'[丨|｜]',           # 中文分隔符
        r'\d+[、.]\s*',       # 数字序号: 1. 2. 
        r'[①②③④⑤⑥⑦⑧⑨⑩]',   # 带圈数字
        r'[；;]\s*',          # 分号
        r'•\s*',              # 项目符号
        r'\n\s*\n',           # 双换行
        r'【(.+?)】',          # 【标题】
        r'\d+[\)）]\s*',      # 1) 2) 格式
    ]
    
    # 聚合新闻标题模式
    AGGREGATE_TITLE_PATTERNS = [
        r'早报|晚报|日报|周报|月报',
        r'8点1氪|36氪|晚报|合集|汇总',
        r'今日快讯|新闻简报|一句话新闻',
        r'morning brief|daily brief|news digest',
        r'快讯|速递|要闻',
    ]
    
    def __init__(self):
        self.stats = {
            'input_count': 0,
            'split_count': 0,
            'output_count': 0
        }
    
    def is_aggregate_news(self, title: str, content: str = "") -> bool:
        """判断是否为聚合新闻"""
        text = (title + " " + content).lower()
        for pattern in self.AGGREGATE_TITLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def split_article(self, article: Dict) -> List[Dict]:
        """
        将聚合新闻拆分为多个原子新闻
        
        Args:
            article: 原始文章字典
            
        Returns:
            拆分后的原子新闻列表
        """
        self.stats['input_count'] += 1
        
        title = article.get('title', '')
        content = article.get('summary', article.get('content', ''))
        
        # 如果不是聚合新闻，直接返回原文章
        if not self.is_aggregate_news(title, content):
            self.stats['output_count'] += 1
            return [article]
        
        # 尝试拆分
        atomic_articles = []
        
        # 方法1: 按分隔符拆分内容
        segments = self._split_by_separators(content)
        
        if len(segments) <= 1:
            # 无法拆分，返回原文章但标记为聚合类型
            article['is_aggregate'] = True
            self.stats['output_count'] += 1
            return [article]
        
        # 为每个片段创建独立文章
        for segment in segments:
            if not segment or len(segment) < 20:
                continue
            
            # 提取标题和正文
            seg_title, seg_content = self._extract_title_from_segment(segment)
            
            if not seg_title:
                seg_title = self._generate_title(segment)
            
            atomic_article = {
                'title': seg_title,
                'summary': seg_content[:500] if seg_content else segment[:500],
                'content': seg_content or segment,
                'link': article.get('link', ''),
                'source': article.get('source', 'unknown'),
                'published_raw': article.get('published_raw', ''),
                'published_date': article.get('published_date'),
                'fetch_method': article.get('fetch_method', 'atomic_split'),
                'parent_link': article.get('link', ''),
                'is_atomic': True
            }
            atomic_articles.append(atomic_article)
        
        self.stats['split_count'] += 1
        self.stats['output_count'] += len(atomic_articles)
        
        return atomic_articles
    
    def _split_by_separators(self, text: str) -> List[str]:
        """按分隔符拆分文本"""
        if not text:
            return []
        
        # 尝试多种分隔符
        for pattern in self.SEPARATOR_PATTERNS:
            segments = re.split(pattern, text)
            if len(segments) > 3:
                # 找到有效分隔符
                return [s.strip() for s in segments if s.strip()]
        
        return [text]
    
    def _extract_title_from_segment(self, segment: str) -> tuple:
        """从片段中提取标题"""
        lines = segment.strip().split('\n')
        if not lines:
            return None, segment
        
        # 第一行作为潜在标题
        first_line = lines[0].strip()
        
        # 检查是否像标题（长度适中，不以标点结尾）
        if 5 < len(first_line) < 100 and not first_line.endswith(('。', '？', '！')):
            content = '\n'.join(lines[1:]) if len(lines) > 1 else ''
            return first_line, content
        
        return None, segment
    
    def _generate_title(self, segment: str) -> str:
        """为无法提取标题的片段生成标题"""
        # 取前50个字符作为标题
        title = segment[:50].strip()
        if len(segment) > 50:
            title += "..."
        return title
    
    def split_batch(self, articles: List[Dict]) -> List[Dict]:
        """批量拆分聚合新闻"""
        result = []
        for article in articles:
            atomic_articles = self.split_article(article)
            result.extend(atomic_articles)
        
        print(f"📦 Atomic Splitter: {self.stats['input_count']} → {self.stats['output_count']} articles "
              f"(split {self.stats['split_count']} aggregates)")
        
        # 重置统计
        self.stats = {'input_count': 0, 'split_count': 0, 'output_count': 0}
        
        return result
    
    def get_stats(self) -> Dict:
        """获取拆分统计"""
        return self.stats
