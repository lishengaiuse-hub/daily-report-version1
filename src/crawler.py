#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-method web crawler supporting RSS, HTTP, Firecrawl, and Topic-Specific Search
Version: 3.0 - 添加 RSS Fallback 机制
"""

import re
import time
import hashlib
import feedparser
import requests
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

# Firecrawl 可选导入
try:
    from firecrawl import Firecrawl
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False
    print("⚠️ firecrawl-py not available, Firecrawl features disabled")


class ArticleFetcher:
    """Fetch articles from multiple source types with RSS fallback"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Initialize Firecrawl client
        self.firecrawl = None
        if FIRECRAWL_AVAILABLE:
            api_key = os.getenv("FIRECRAWL_API_KEY")
            if api_key:
                try:
                    self.firecrawl = Firecrawl(api_key=api_key)
                    print("✅ Firecrawl initialized successfully")
                except Exception as e:
                    print(f"⚠️ Failed to initialize Firecrawl: {e}")
            else:
                print("⚠️ FIRECRAWL_API_KEY not set, Firecrawl disabled")
        
        self.results = []
    
    # =============================================
    # RSS FETCHING WITH FALLBACK
    # =============================================
    
    def fetch_rss(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed - 原始方法"""
        articles = []
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            
            for entry in feed.entries[:30]:
                summary = entry.get('summary', entry.get('description', ''))
                content = entry.get('content', [{}])[0].get('value', summary)
                
                article = {
                    'title': self._clean_text(entry.get('title', '')),
                    'summary': self._clean_text(summary[:500]),
                    'content': self._clean_text(content[:2000]),
                    'link': entry.get('link', ''),
                    'published_raw': entry.get('published', entry.get('updated', '')),
                    'source': urlparse(url).netloc,
                    'fetch_method': 'rss'
                }
                if article['title'] and article['link']:
                    articles.append(article)
        except Exception as e:
            print(f"  ⚠️ RSS fetch failed for {url}: {e}")
        return articles
    
    def fetch_rss_with_fallback(self, url: str, source_name: str = "") -> List[Dict]:
        """
        带fallback的RSS抓取
        方法1: 直接RSS
        方法2: 尝试备用URL
        方法3: Firecrawl (如果可用)
        """
        articles = []
        
        # 方法1: 直接RSS
        try:
            response = self.session.get(url, timeout=15)
            feed = feedparser.parse(response.content)
            if feed.entries:
                for entry in feed.entries[:20]:
                    article = {
                        'title': self._clean_text(entry.get('title', '')),
                        'summary': self._clean_text(entry.get('summary', '')[:500]),
                        'content': '',
                        'link': entry.get('link', ''),
                        'published_raw': entry.get('published', ''),
                        'source': urlparse(url).netloc,
                        'fetch_method': 'rss'
                    }
                    if article['title'] and article['link']:
                        articles.append(article)
                return articles
        except Exception as e:
            print(f"     ⚠️ RSS failed for {source_name}: {e}")
        
        # 方法2: 尝试备用URL
        backup_urls = self._get_backup_urls(url)
        for backup_url in backup_urls:
            try:
                response = self.session.get(backup_url, timeout=15)
                feed = feedparser.parse(response.content)
                if feed.entries:
                    for entry in feed.entries[:20]:
                        article = {
                            'title': self._clean_text(entry.get('title', '')),
                            'summary': self._clean_text(entry.get('summary', '')[:500]),
                            'content': '',
                            'link': entry.get('link', ''),
                            'published_raw': entry.get('published', ''),
                            'source': urlparse(backup_url).netloc,
                            'fetch_method': 'rss_fallback'
                        }
                        if article['title'] and article['link']:
                            articles.append(article)
                    print(f"     ✅ Fallback RSS success: {backup_url}")
                    return articles
            except:
                continue
        
        # 方法3: Firecrawl (如果可用)
        if self.firecrawl:
            try:
                result = self.firecrawl.scrape(url, formats=['markdown', 'links'])
                if result and result.get('markdown'):
                    articles = self._extract_articles_from_markdown(result['markdown'], url)
                    print(f"     ✅ Firecrawl fallback success for {source_name}")
                    return articles
            except:
                pass
        
        print(f"     ❌ All methods failed for {source_name}")
        return articles
    
    def _get_backup_urls(self, original_url: str) -> List[str]:
        """生成备用URL"""
        backups = []
        
        # 常见RSS路径变体
        if original_url.endswith('/feed'):
            backups.append(original_url.replace('/feed', '/rss'))
            backups.append(original_url.replace('/feed', '/feed.xml'))
        elif original_url.endswith('/rss'):
            backups.append(original_url.replace('/rss', '/feed'))
            backups.append(original_url.replace('/rss', '/rss.xml'))
        
        # 添加根目录常见路径
        from urllib.parse import urlparse
        parsed = urlparse(original_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        backups.extend([
            f"{base}/feed",
            f"{base}/rss",
            f"{base}/rss.xml",
            f"{base}/feed.xml",
            f"{base}/index.xml",
            f"{base}/news/feed",
            f"{base}/news/rss"
        ])
        
        return list(set(backups))
    
    def _extract_articles_from_markdown(self, markdown: str, base_url: str) -> List[Dict]:
        """从Markdown内容中提取文章"""
        articles = []
        lines = markdown.split('\n')
        
        for line in lines[:100]:
            line = line.strip()
            # 查找Markdown链接格式
            link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
            if link_match:
                title = link_match.group(1)
                link = link_match.group(2)
                if len(title) > 10 and len(title) < 200:
                    article = {
                        'title': self._clean_text(title),
                        'summary': '',
                        'content': '',
                        'link': urljoin(base_url, link),
                        'published_raw': '',
                        'source': urlparse(base_url).netloc,
                        'fetch_method': 'firecrawl_markdown'
                    }
                    articles.append(article)
        
        return articles
    
    # =============================================
    # WEB PAGE SCRAPING
    # =============================================
    
    def fetch_webpage(self, source_config: Dict) -> List[Dict]:
        """Fetch articles from HTML webpage using CSS selectors"""
        articles = []
        url = source_config.get('url', '')
        
        if not url:
            return articles
        
        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            container = source_config.get('container', 'article')
            items = soup.select(container)[:source_config.get('limit', 15)]
            
            for item in items:
                title_elem = item.select_one(source_config.get('title_selector', ''))
                link_elem = item.select_one(source_config.get('link_selector', ''))
                
                if not title_elem or not link_elem:
                    continue
                
                article = {
                    'title': self._clean_text(title_elem.get_text(strip=True)),
                    'summary': '',
                    'content': '',
                    'link': urljoin(url, link_elem.get('href', '')),
                    'published_raw': '',
                    'source': urlparse(url).netloc,
                    'fetch_method': 'webpage'
                }
                
                date_selector = source_config.get('date_selector')
                if date_selector:
                    date_elem = item.select_one(date_selector)
                    if date_elem:
                        article['published_raw'] = self._clean_text(date_elem.get_text(strip=True))
                
                if article['title'] and article['link']:
                    articles.append(article)
                    
        except Exception as e:
            print(f"  ⚠️ Webpage fetch failed for {url}: {e}")
        
        return articles
    
    # =============================================
    # TOPIC-SPECIFIC ACTIVE SEARCH
    # =============================================
    
    def fetch_by_topic(self, topic_id: int, topic_sources: Dict[int, List[str]], 
                       topic_keywords: Dict[int, List[str]], days_back: int = 3) -> List[Dict]:
        """Actively fetch articles for a specific topic using keywords and sources"""
        articles = []
        sources = topic_sources.get(topic_id, [])
        keywords = topic_keywords.get(topic_id, [])
        
        print(f"     🔍 Active search for Topic {topic_id} with {len(keywords)} keywords...")
        
        # Method 1: Google News RSS search using keywords
        for keyword in keywords[:8]:
            encoded_keyword = requests.utils.quote(keyword)
            search_urls = [
                f"https://news.google.com/rss/search?q={encoded_keyword}&hl=en-US&gl=US&ceid=US:en",
                f"https://news.google.com/rss/search?q={encoded_keyword}+after:{days_back}+days&hl=en-US"
            ]
            
            for url in search_urls:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:5]:
                        article = {
                            'title': self._clean_text(entry.get('title', '')),
                            'summary': self._clean_text(entry.get('summary', '')[:500]),
                            'content': '',
                            'link': entry.get('link', ''),
                            'published_raw': entry.get('published', ''),
                            'source': 'google_news_search',
                            'fetch_method': 'topic_search',
                            'search_keyword': keyword,
                            'topics_hint': [topic_id]
                        }
                        if article['title'] and article['link'] and len(article['title']) > 10:
                            articles.append(article)
                except Exception as e:
                    print(f"       ⚠️ Google News search failed for '{keyword}': {e}")
            
            time.sleep(0.3)
        
        # Method 2: Direct source RSS fetching
        print(f"     📡 Checking {len(sources)} topic-specific sources...")
        for source_domain in sources[:10]:
            feed_urls = [
                f"https://{source_domain}/feed",
                f"https://{source_domain}/rss",
                f"https://{source_domain}/news/feed",
                f"https://{source_domain}/rss.xml"
            ]
            
            for feed_url in feed_urls:
                try:
                    feed = feedparser.parse(feed_url)
                    if feed.entries:
                        for entry in feed.entries[:5]:
                            article = {
                                'title': self._clean_text(entry.get('title', '')),
                                'summary': self._clean_text(entry.get('summary', '')[:500]),
                                'content': '',
                                'link': entry.get('link', ''),
                                'published_raw': entry.get('published', ''),
                                'source': source_domain,
                                'fetch_method': 'topic_source',
                                'topics_hint': [topic_id]
                            }
                            if article['title'] and article['link'] and len(article['title']) > 10:
                                articles.append(article)
                        break
                except Exception:
                    continue
            
            time.sleep(0.3)
        
        # Remove duplicates
        seen_titles = set()
        unique_articles = []
        for article in articles:
            title_key = article['title'][:50].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_articles.append(article)
        
        print(f"     ✅ Found {len(unique_articles)} unique articles for Topic {topic_id}")
        return unique_articles[:20]
    
    # =============================================
    # API FETCHING
    # =============================================
    
    def fetch_api(self, source_config: Dict) -> List[Dict]:
        """Fetch from REST API endpoint"""
        articles = []
        url = source_config.get('url', '')
        
        if not url:
            return articles
        
        try:
            method = source_config.get('method', 'GET')
            params = source_config.get('params', {})
            headers = source_config.get('headers', {})
            
            request_headers = self.session.headers.copy()
            request_headers.update(headers)
            
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=15, headers=request_headers)
            else:
                response = self.session.post(url, json=params, timeout=15, headers=request_headers)
            
            response.raise_for_status()
            data = response.json()
            
            items = data.get('data', data.get('posts', data.get('articles', [])))
            if not items and isinstance(data, list):
                items = data
            
            for item in items[:source_config.get('limit', 15)]:
                article = {
                    'title': self._extract_field(item, ['title', 'headline', 'name']),
                    'summary': self._extract_field(item, ['summary', 'description', 'excerpt', 'content']),
                    'content': self._extract_field(item, ['content', 'body', 'text']),
                    'link': self._extract_field(item, ['link', 'url', 'permalink']),
                    'published_raw': self._extract_field(item, ['published_date', 'date', 'created_at', 'pubDate']),
                    'source': urlparse(url).netloc,
                    'fetch_method': 'api'
                }
                
                if article['title'] and article['link']:
                    articles.append(article)
                    
        except Exception as e:
            print(f"  ⚠️ API fetch failed for {url}: {e}")
        
        return articles
    
    # =============================================
    # MAIN FETCH METHOD
    # =============================================
    
    def fetch_all(self, sources: Dict) -> List[Dict]:
        """Fetch from all configured sources with fallback"""
        all_articles = []
        
        # RSS Feeds (with fallback)
        print("📡 Fetching RSS feeds...")
        rss_sources = sources.get('rss', {})
        for category, urls in rss_sources.items():
            for url in urls:
                print(f"  📰 RSS: {url[:60]}...")
                articles = self.fetch_rss_with_fallback(url, category)
                all_articles.extend(articles)
                time.sleep(0.5)
        
        # Web Scraping
        print("🕸️  Fetching web pages...")
        web_sources = sources.get('web_scraping', {})
        for name, config in web_sources.items():
            url = config.get('url', '')
            if url:
                print(f"  🌐 {name}: {url[:60]}...")
                articles = self.fetch_webpage(config)
                all_articles.extend(articles)
                time.sleep(1)
        
        # Firecrawl Sources
        if self.firecrawl:
            print("🔥 Fetching with Firecrawl...")
            firecrawl_sources = sources.get('firecrawl', {})
            for name, config in firecrawl_sources.items():
                url = config.get('url', '')
                if url:
                    print(f"  🔥 {name}: {url[:60]}...")
                    # 使用带fallback的RSS方法，但传入Firecrawl作为备用
                    articles = self.fetch_rss_with_fallback(url, name)
                    all_articles.extend(articles)
                    time.sleep(2)
        else:
            print("🔥 Firecrawl not available - skipping dynamic sites")
        
        # API Sources
        print("🔌 Fetching APIs...")
        api_sources = sources.get('api', {})
        for name, config in api_sources.items():
            url = config.get('url', '')
            if url:
                print(f"  📡 {name}: {url[:60]}...")
                articles = self.fetch_api(config)
                all_articles.extend(articles)
                time.sleep(0.5)
        
        print(f"✅ Total fetched: {len(all_articles)} articles")
        return all_articles
    
    # =============================================
    # HELPER METHODS
    # =============================================
    
    def _clean_text(self, text: str) -> str:
        """Clean HTML and normalize text"""
        if not text:
            return ""
        text = re.sub(r'<.*?>', '', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s\u4e00-\u9fff\-\.\,\!\?\(\)\[\]\:\;\"\']', ' ', text)
        return text.strip()
    
    def _extract_field(self, item: Dict, possible_names: List[str]) -> str:
        """Extract field from dict by trying multiple possible names"""
        for name in possible_names:
            if name in item:
                value = item[name]
                if isinstance(value, str):
                    return self._clean_text(value)
                elif isinstance(value, dict) and 'rendered' in value:
                    return self._clean_text(value['rendered'])
        return ""
