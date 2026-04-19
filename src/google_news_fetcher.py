#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google News Fetcher - 主动搜索能力
解决RSS抓取不到内容的问题
"""

import requests
import feedparser
import re
from typing import List, Dict
from datetime import datetime, timedelta
from urllib.parse import quote


class GoogleNewsFetcher:
    """使用Google News RSS进行主动搜索"""
    
    def __init__(self, session):
        self.session = session
        self.base_url = "https://news.google.com/rss/search"
        self.stats = {'searches': 0, 'articles_found': 0}
    
    def search(self, query: str, days_back: int = 3, limit: int = 10) -> List[Dict]:
        """
        搜索新闻
        
        Args:
            query: 搜索关键词 (支持布尔运算符)
            days_back: 搜索最近N天的新闻
            limit: 返回结果数量限制
        """
        articles = []
        self.stats['searches'] += 1
        
        # 构建搜索URL
        encoded_query = quote(query)
        
        # 添加时间过滤
        if days_back > 0:
            after_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            full_query = f"{query} after:{after_date}"
            encoded_query = quote(full_query)
        
        url = f"{self.base_url}?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            response = self.session.get(url, timeout=15)
            feed = feedparser.parse(response.content)
            
            for entry in feed.entries[:limit]:
                # 清理标题中的特殊字符
                title = self._clean_title(entry.get('title', ''))
                
                article = {
                    'title': title,
                    'summary': self._clean_text(entry.get('summary', '')[:500]),
                    'link': entry.get('link', ''),
                    'published_raw': entry.get('published', ''),
                    'source': 'google_news',
                    'search_query': query,
                    'fetch_method': 'google_news_search'
                }
                if article['title'] and article['link'] and len(article['title']) > 10:
                    articles.append(article)
                    self.stats['articles_found'] += 1
                    
        except Exception as e:
            print(f"     ⚠️ Google News search failed for '{query}': {e}")
        
        return articles
    
    def search_by_topic(self, topic_id: int, keywords: List[str], days_back: int = 3) -> List[Dict]:
        """按主题搜索"""
        all_articles = []
        
        for keyword in keywords[:5]:  # 限制关键词数量
            articles = self.search(keyword, days_back, limit=5)
            all_articles.extend(articles)
        
        # 去重
        seen_links = set()
        unique_articles = []
        for article in all_articles:
            if article['link'] not in seen_links:
                seen_links.add(article['link'])
                unique_articles.append(article)
        
        return unique_articles[:15]
    
    def _clean_title(self, title: str) -> str:
        """清理标题中的Google News特殊标记"""
        if not title:
            return ""
        # 移除 "Google News" 等标记
        title = re.sub(r'\s*-\s*Google\s+News$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*\|\s*Google\s+News$', '', title, flags=re.IGNORECASE)
        return title.strip()
    
    def _clean_text(self, text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        # 移除HTML标签
        text = re.sub(r'<.*?>', '', text)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats


# 主题关键词配置 - 用于主动搜索
TOPIC_SEARCH_KEYWORDS = {
    1: [  # 竞品动态
        "Samsung+competitor+product+launch",
        "Apple+new+iPhone+2026",
        "Xiaomi+TV+release",
        "LG+OLED+2026",
        "TCL+Mini+LED",
        "Hisense+TV",
        "Sony+TV+2026",
        "Huawei+smartphone+2026"
    ],
    2: [  # 技术/材料
        "semiconductor+breakthrough",
        "display+technology+2026",
        "battery+innovation+2026",
        "MicroLED+advancement",
        "GaN+technology",
        "new+electronic+material",
        "OLED+technology+2026",
        "silicon+carbide+semiconductor"
    ],
    3: [  # 制造转移
        "Vietnam+electronics+factory",
        "India+manufacturing+investment",
        "Southeast+Asia+supply+chain",
        "Thailand+assembly+plant",
        "manufacturing+relocation+Asia",
        "Foxconn+Vietnam+expansion",
        "Samsung+Vietnam+factory",
        "electronics+manufacturing+India"
    ],
    4: [  # 展会
        "CES+2026+announcement",
        "IFA+Berlin+2026",
        "MWC+2026+news",
        "Display+Week+2026",
        "AWE+2026+China",
        "Computex+2026+Taipei"
    ],
    5: [  # 供应链风险
        "semiconductor+shortage+2026",
        "supply+chain+disruption",
        "electronics+tariff+2026",
        "component+price+increase",
        "logistics+delay+electronics",
        "chip+shortage+2026",
        "display+panel+price",
        "battery+supply+chain"
    ]
}
