#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-method web crawler supporting RSS, HTTP, and optional Firecrawl/Playwright
"""

import re  # ← 关键修复
import feedparser
import requests
import time
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


class ArticleFetcher:
    """Fetch articles from multiple source types"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.results = []
    
    def fetch_rss(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed"""
        articles = []
        try:
            response = self.session.get(url, timeout=15)
            feed = feedparser.parse(response.content)
            
            for entry in feed.entries[:15]:  # Limit per feed
                article = {
                    'title': self._clean_text(entry.get('title', '')),
                    'summary': self._clean_text(entry.get('summary', entry.get('description', ''))),
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
            soup = BeautifulSoup(response.text, 'html.parser')
            
            container = source_config.get('container', 'article')
            items = soup.select(container)[:source_config.get('limit', 10)]
            
            for item in items:
                title_elem = item.select_one(source_config.get('title_selector', ''))
                link_elem = item.select_one(source_config.get('link_selector', ''))
                
                if not title_elem or not link_elem:
                    continue
                
                article = {
                    'title': self._clean_text(title_elem.get_text(strip=True)),
                    'summary': '',  # Will be filled from content or left as title
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
    
    def fetch_api(self, source_config: Dict) -> List[Dict]:
        """Fetch from REST API endpoint"""
        articles = []
        url = source_config.get('url', '')
        
        if not url:
            return articles
        
        try:
            method = source_config.get('method', 'GET')
            params = source_config.get('params', {})
            
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=15)
            else:
                response = self.session.post(url, json=params, timeout=15)
            
            data = response.json()
            
            # Handle different API response structures
            items = data.get('data', data.get('posts', data.get('articles', [])))
            if not items and isinstance(data, list):
                items = data
            
            for item in items[:source_config.get('limit', 15)]:
                # Map common fields
                article = {
                    'title': self._extract_field(item, ['title', 'headline', 'name']),
                    'summary': self._extract_field(item, ['summary', 'description', 'excerpt', 'content']),
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
        # Remove HTML tags using re (now available)
        text = re.sub(r'<.*?>', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
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
                time.sleep(0.5)  # Rate limiting
        
        # Web Scraping (priority 2)
        print("🕸️  Fetching web pages...")
        web_sources = sources.get('web_scraping', {})
        for name, config in web_sources.items():
            print(f"  🌐 {name}: {config.get('url', '')[:60]}...")
            articles = self.fetch_webpage(config)
            all_articles.extend(articles)
            time.sleep(1)
        
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
