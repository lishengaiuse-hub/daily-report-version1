#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-method web crawler supporting RSS, HTTP, Firecrawl, and Topic-Specific Search
Version: 3.0 - Includes topic coverage guarantee and active keyword search
"""

import re
import time
import hashlib
import feedparser
import requests
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
    """Fetch articles from multiple source types with topic-specific search"""
    
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
    # RSS FETCHING
    # =============================================
    
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
    
    # =============================================
    # FIRECRAWL (Dynamic JavaScript Sites)
    # =============================================
    
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
            title_patterns = [
                r'^#\s+(.+)$',      # H1
                r'^##\s+(.+)$',     # H2
                r'^###\s+(.+)$',    # H3
                r'^【(.+)】$',       # Chinese bracket format
                r'^\[(.+)\]\(.+\)$' # Markdown link format
            ]
            
            lines = markdown_content.split('\n')
            potential_titles = []
            
            for line in lines[:100]:
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
                if self._is_article_link(link, url):
                    article_links.append(link)
            
            # Build articles from extracted data
            for i, title in enumerate(potential_titles[:limit]):
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
    
    # =============================================
    # TOPIC-SPECIFIC ACTIVE SEARCH (NEW)
    # =============================================
    
    def fetch_by_topic(self, topic_id: int, topic_sources: Dict[int, List[str]], 
                       topic_keywords: Dict[int, List[str]], days_back: int = 3) -> List[Dict]:
        """
        Actively fetch articles for a specific topic using keywords and sources
        
        Args:
            topic_id: Topic ID (1-5)
            topic_sources: Dictionary mapping topic_id to list of source domains
            topic_keywords: Dictionary mapping topic_id to list of search keywords
            days_back: Days to look back for news
        
        Returns:
            List of articles for this topic
        """
        articles = []
        sources = topic_sources.get(topic_id, [])
        keywords = topic_keywords.get(topic_id, [])
        
        print(f"     🔍 Active search for Topic {topic_id} with {len(keywords)} keywords...")
        
        # Method 1: Google News RSS search using keywords
        for keyword in keywords[:8]:  # Limit to top 8 keywords
            encoded_keyword = requests.utils.quote(keyword)
            
            # Search for recent news
            search_urls = [
                f"https://news.google.com/rss/search?q={encoded_keyword}&hl=en-US&gl=US&ceid=US:en",
                f"https://news.google.com/rss/search?q={encoded_keyword}+after:{days_back}+days&hl=en-US"
            ]
            
            for url in search_urls:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:5]:
                        # Check if article is recent
                        published = entry.get('published', '')
                        if published:
                            pub_date = self._parse_date(published)
                            if pub_date and (datetime.now() - pub_date).days > days_back:
                                continue
                        
                        article = {
                            'title': self._clean_text(entry.get('title', '')),
                            'summary': self._clean_text(entry.get('summary', '')[:500]),
                            'content': '',
                            'link': entry.get('link', ''),
                            'published_raw': published,
                            'source': 'google_news_search',
                            'fetch_method': 'topic_search',
                            'search_keyword': keyword,
                            'topics_hint': [topic_id]
                        }
                        if article['title'] and article['link'] and len(article['title']) > 10:
                            articles.append(article)
                except Exception as e:
                    print(f"       ⚠️ Google News search failed for '{keyword}': {e}")
            
            time.sleep(0.3)  # Rate limiting
        
        # Method 2: Direct source RSS fetching
        print(f"     📡 Checking {len(sources)} topic-specific sources...")
        for source_domain in sources[:10]:
            # Try common RSS feed paths
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
                        break  # Found working feed
                except Exception:
                    continue
            
            time.sleep(0.3)
        
        # Remove duplicates within this batch
        seen_titles = set()
        unique_articles = []
        for article in articles:
            title_key = article['title'][:50].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_articles.append(article)
        
        print(f"     ✅ Found {len(unique_articles)} unique articles for Topic {topic_id}")
        return unique_articles[:20]  # Limit per topic
    
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
    
    # =============================================
    # MAIN FETCH METHOD
    # =============================================
    
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
            url = config.get('url', '')
            if url:
                print(f"  🌐 {name}: {url[:60]}...")
                articles = self.fetch_webpage(config)
                all_articles.extend(articles)
                time.sleep(1)
        
        # Firecrawl Sources (priority 2.5 - for dynamic sites)
        if self.firecrawl:
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
                    time.sleep(2)
        else:
            print("🔥 Firecrawl not available - skipping dynamic sites")
        
        # API Sources (priority 3)
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
        title = ' '.join(words[:8])
        
        return title[:100] if title else "Article"
    
    def _parse_date(self, date_string: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_string:
            return None
        
        try:
            # Try common RSS date formats
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_string)
        except:
            pass
        
        try:
            from dateutil import parser
            return parser.parse(date_string)
        except:
            pass
        
        return None
