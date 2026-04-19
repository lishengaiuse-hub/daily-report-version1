#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Origin Tracker - 追溯原始新闻来源
解决：聚合页内容无法追溯到原始来源的问题
"""

import re
import requests
from urllib.parse import urlparse, urljoin
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup


class OriginTracker:
    """追溯聚合新闻的原始来源"""
    
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.stats = {'traced': 0, 'failed': 0}
    
    def extract_original_url(self, article: Dict) -> Dict:
        """
        从文章中提取原始来源URL
        
        Returns:
            更新后的文章，包含 original_url 和 trace_status
        """
        content = article.get('summary', article.get('content', ''))
        link = article.get('link', '')
        
        # 方法1: 从内容中提取URL
        urls = self._extract_urls_from_content(content)
        
        # 方法2: 如果文章是聚合页，尝试获取真实来源
        if self._is_aggregator_page(link):
            real_url = self._fetch_real_source(link)
            if real_url:
                article['original_url'] = real_url
                article['trace_status'] = 'resolved'
                self.stats['traced'] += 1
                return article
        
        if urls:
            # 取第一个看起来像新闻的URL
            for url in urls:
                if self._is_news_url(url):
                    article['original_url'] = url
                    article['trace_status'] = 'extracted_from_content'
                    self.stats['traced'] += 1
                    return article
        
        # 无法追溯
        article['original_url'] = None
        article['trace_status'] = 'unresolved'
        article['confidence'] = 'low'
        self.stats['failed'] += 1
        
        return article
    
    def _extract_urls_from_content(self, content: str) -> List[str]:
        """从内容中提取所有URL"""
        url_pattern = r'https?://[^\s<>"\'\)]+(?:/[\w\-\.]+)*(?:/)?'
        urls = re.findall(url_pattern, content)
        return list(set(urls))
    
    def _is_news_url(self, url: str) -> bool:
        """判断URL是否为新闻文章链接"""
        news_patterns = [
            r'/news/', r'/article/', r'/story/', r'/p/', 
            r'/a/', r'/post/', r'/content/', r'/read/',
            r'/\d{4}/\d{2}/\d{2}/'
        ]
        for pattern in news_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    def _is_aggregator_page(self, url: str) -> bool:
        """判断是否为聚合页"""
        if not url:
            return False
        aggregator_domains = [
            '36kr.com', 'ithome.com', 'leiphone.com', 'pingwest.com',
            'cnbeta.com', 'technews.tw', 'news.google.com'
        ]
        for domain in aggregator_domains:
            if domain in url.lower():
                return True
        return False
    
    def _fetch_real_source(self, url: str) -> Optional[str]:
        """从聚合页抓取真实来源"""
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找原文链接（常见模式）
            patterns = [
                ('a[rel="original"]', 'href'),
                ('a[rel="source"]', 'href'),
                ('.source-link a', 'href'),
                ('.original-link a', 'href'),
                ('a[href*="reuters"]', 'href'),
                ('a[href*="bloomberg"]', 'href'),
                ('a[href*="nikkei"]', 'href'),
            ]
            
            for selector, attr in patterns:
                elem = soup.select_one(selector)
                if elem and elem.get(attr):
                    return urljoin(url, elem[attr])
            
            return None
        except Exception:
            return None
    
    def trace_batch(self, articles: List[Dict]) -> List[Dict]:
        """批量追溯来源"""
        for article in articles:
            article = self.extract_original_url(article)
        
        print(f"🔗 Origin Tracker: {self.stats['traced']} traced, {self.stats['failed']} unresolved")
        return articles
    
    def get_stats(self) -> Dict:
        return self.stats
