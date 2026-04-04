#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-method web crawler supporting RSS, HTTP, Firecrawl, and Playwright
"""

import re
import time
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

# Firecrawl 可选导入
try:
    from firecrawl import Firecrawl
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False
    print("⚠️ firecrawl-py not available, Firecrawl features disabled")


class ArticleFetcher:
    """Fetch articles from multiple source types"""
    
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
        
        # 初始化 Firecrawl 客户端
        self.firecrawl = None
        if FIRECRAWL_AVAILABLE:
            import os
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
    
    def fetch_rss(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed"""
        articles = []
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            
            for entry in feed.entries[:30]:  # Limit per feed
                # Get content with fallbacks
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
                
                # Extract date if selector provided
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
    
    def fetch_with_firecrawl(self, url: str, source_name: str = "unknown", 
                              wait_for: int = 3000, limit: int = 20) -> List[Dict]:
        """
        Fetch articles using Firecrawl - handles dynamic JavaScript content
        
        Args:
            url: Target URL to scrape
            source_name: Name of the source for logging
            wait_for: Milliseconds to wait for page load
            limit: Maximum number of articles to extract
        
        Returns:
            List of article dictionaries
        """
        articles = []
        
        if not self.firecrawl:
            print(f"  ⚠️ Firecrawl not available for {source_name}")
            return articles
        
        try:
            print(f"  🔥 Firecrawl scraping: {source_name} - {url[:60]}...")
            
            # Scrape with markdown format for clean content
            scrape_result = self.firecrawl.scrape(
                url,
                formats=['markdown', 'links', 'html'],
                options={
                    'waitFor': wait_for,
                    'timeout': 30000,
                }
            )
            
            if not scrape_result or not scrape_result.get('success'):
                print(f"     ⚠️ Firecrawl scrape failed for {source_name}")
                return articles
            
            # Extract content
            markdown_content = scrape_result.get('markdown', '')
            links = scrape_result.get('links', [])
            
            # Try to extract article titles from markdown content
            # Look for heading patterns that might be article titles
            title_patterns = [
                r'^#\s+(.+)$',      # H1
                r'^##\s+(.+)$',     # H2
                r'^###\s+(.+)$',    # H3
                r'^【(.+)】$',       # Chinese bracket format
                r'^\[(.+)\]\(.+\)$' # Markdown link format
            ]
            
            lines = markdown_content.split('\n')
            potential_titles = []
            
            for line in lines[:100]:  # Check first 100 lines
                line = line.strip()
                if not line or len(line) < 5 or len(line) > 200:
                    continue
                
                for pattern in title_patterns:
                    match = re.match(pattern, line)
                    if match:
                        title = match.group(1).strip()
                        if len(title) > 3 and len(title) < 150:
                            potential_titles.append(title)
                            break
            
            # Also extract from links that look like articles
            article_links = []
            for link in links[:limit]:
                # Filter for article-like URLs
                if self._is_article_link(link, url):
                    article_links.append(link)
            
            # Build articles from extracted data
            # Priority 1: Use extracted titles with their context
            for i, title in enumerate(potential_titles[:limit]):
                # Try to find a link for this title
                link = url
                for article_link in article_links:
                    if title.lower().replace(' ', '') in article_link.lower():
                        link = article_link
                        break
                
                article = {
                    'title': self._clean_text(title),
                    'summary': '',
                    'content': '',
                    'link': link,
                    'published_raw': '',
                    'source': urlparse(url).netloc,
                    'fetch_method': 'firecrawl'
                }
                articles.append(article)
            
            # If no titles extracted, fall back to links
            if not articles and article_links:
                for link in article_links[:limit]:
                    article = {
                        'title': self._extract_title_from_url(link),
                        'summary': '',
                        'content': '',
                        'link': link,
                        'published_raw': '',
                        'source': urlparse(url).netloc,
                        'fetch_method': 'firecrawl'
                    }
                    articles.append(article)
            
            print(f"     ✅ Extracted {len(articles)} potential articles")
            
        except Exception as e:
            print(f"  ❌ Firecrawl failed for {source_name}: {e}")
        
        return articles
    
    def _is_article_link(self, link: str, base_url: str) -> bool:
        """Determine if a URL looks like an article link"""
        if not link or not link.startswith('http'):
            return False
        
        # Exclude common non-article paths
        exclude_patterns = [
            '/tag/', '/category/', '/author/', '/page/', 
            '/search', '/login', '/register', '/about',
            '/contact', '/privacy', '/terms', '.css', '.js',
            '.jpg', '.png', '.gif', '.pdf'
        ]
        
        for pattern in exclude_patterns:
            if pattern in link.lower():
                return False
        
        # Include patterns that suggest article content
        include_patterns = [
            '/news/', '/article/', '/post/', '/p/', 
            '/story/', '/content/', '/read/', '/detail/',
            '/a/', '/2026/', '/2025/'
        ]
        
        for pattern in include_patterns:
            if pattern in link.lower():
                return True
        
        # If link is from same domain and has reasonable length
        if base_url in link and len(link.split('/')) >= 4:
            return True
        
        return False
    
    def _extract_title_from_url(self, url: str) -> str:
        """Extract a readable title from URL"""
        # Remove protocol and domain
        path = url.replace('https://', '').replace('http://', '')
        path = path.split('/', 1)[-1] if '/' in path else path
        
        # Remove extension
        path = re.sub(r'\.[^/.]+$', '', path)
        
        # Replace separators with spaces
        title = re.sub(r'[-_/]', ' ', path)
        
        # Capitalize words
        words = title.split()
        title = ' '.join(words[:8])  # Limit to 8 words
        
        return title[:100] if title else "Article"
    
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
            
            # Merge with default headers
            request_headers = self.session.headers.copy()
            request_headers.update(headers)
            
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=15, headers=request_headers)
            else:
                response = self.session.post(url, json=params, timeout=15, headers=request_headers)
            
            response.raise_for_status()
            data = response.json()
            
            # Handle different API response structures
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
    
    def _clean_text(self, text: str) -> str:
        """Clean HTML and normalize text"""
        if not text:
            return ""
        # Remove HTML tags
        text = re.sub(r'<.*?>', '', text)
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters (keep basic punctuation)
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
    
    def fetch_all(self, sources: Dict) -> List[Dict]:
        """Fetch from all configured sources"""
        all_articles = []
        
        # RSS Feeds (priority 1)
        print("📡 Fetching RSS feeds...")
        rss_sources = sources.get('rss', {})
        for category, urls in rss_sources.items():
            for url in urls:
                print(f"  📰 RSS: {url[:60]}...")
                articles = self.fetch_rss(url)
                all_articles.extend(articles)
                time.sleep(0.5)
        
        # Web Scraping (priority 2)
        print("🕸️  Fetching web pages...")
        web_sources = sources.get('web_scraping', {})
        for name, config in web_sources.items():
            print(f"  🌐 {name}: {config.get('url', '')[:60]}...")
            articles = self.fetch_webpage(config)
            all_articles.extend(articles)
            time.sleep(1)
        
        # Firecrawl Sources (priority 2.5 - for dynamic sites)
        print("🔥 Fetching with Firecrawl...")
        firecrawl_sources = sources.get('firecrawl', {})
        for name, config in firecrawl_sources.items():
            url = config.get('url', '')
            if url:
                print(f"  🔥 {name}: {url[:60]}...")
                articles = self.fetch_with_firecrawl(
                    url=url,
                    source_name=name,
                    wait_for=config.get('wait_for', 3000),
                    limit=config.get('limit', 15)
                )
                all_articles.extend(articles)
                time.sleep(2)  # Longer delay for Firecrawl
        
        # API Sources (priority 3)
        print("🔌 Fetching APIs...")
        api_sources = sources.get('api', {})
        for name, config in api_sources.items():
            print(f"  📡 {name}: {config.get('url', '')[:60]}...")
            articles = self.fetch_api(config)
            all_articles.extend(articles)
            time.sleep(0.5)
        
        print(f"✅ Total fetched: {len(all_articles)} articles")
        return all_articles
