#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-method web crawler supporting RSS, HTTP, Firecrawl, and Google News RSS
Version: 5.1 - SSL bypass + Google News RSS as primary source
"""

import re
import time
import hashlib
import feedparser
import requests
import os
import urllib3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, urljoin, quote
from bs4 import BeautifulSoup

# Suppress SSL warnings globally — many industry sites have cert issues in CI
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Firecrawl optional
try:
    from firecrawl import Firecrawl
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False
    print("⚠️ firecrawl-py not available, Firecrawl features disabled")


class ArticleFetcher:
    """Fetch articles from RSS, web pages, APIs, and Google News RSS"""

    # Google News RSS base — always reachable from GitHub Actions
    GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"

    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self.session.verify = False          # bypass SSL cert errors (CI environment)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })

        self.firecrawl = None
        if FIRECRAWL_AVAILABLE:
            api_key = os.getenv("FIRECRAWL_API_KEY")
            if api_key:
                try:
                    self.firecrawl = Firecrawl(api_key=api_key)
                    print("✅ Firecrawl initialized")
                except Exception as e:
                    print(f"⚠️ Firecrawl init failed: {e}")

        self.results = []

    # =========================================================
    # RSS FETCHING WITH SSL-SAFE FALLBACK
    # =========================================================

    def fetch_rss_with_fallback(self, url: str, source_name: str = "") -> List[Dict]:
        """
        Fetch RSS with two-level fallback:
        1. Primary URL via requests session (SSL-safe)
        2. Backup URL variants via session
        3. Firecrawl if available
        """
        articles = []

        # Method 1: primary URL through session (verify=False)
        try:
            response = self.session.get(url, timeout=12)
            feed = feedparser.parse(response.content)
            if feed.entries:
                for entry in feed.entries[:20]:
                    article = self._entry_to_article(entry, url)
                    if article:
                        articles.append(article)
                return articles
        except Exception as e:
            print(f"     ⚠️ RSS failed for {source_name}: {e}")

        # Method 2: backup URL variants
        for backup_url in self._get_backup_urls(url):
            try:
                response = self.session.get(backup_url, timeout=10)
                feed = feedparser.parse(response.content)
                if feed.entries:
                    for entry in feed.entries[:15]:
                        article = self._entry_to_article(entry, backup_url)
                        if article:
                            articles.append(article)
                    print(f"     ✅ Fallback RSS success: {backup_url}")
                    return articles
            except Exception:
                continue

        # Method 3: Firecrawl
        if self.firecrawl:
            try:
                result = self.firecrawl.scrape(url, formats=["markdown", "links"])
                if result and result.get("markdown"):
                    articles = self._extract_articles_from_markdown(result["markdown"], url)
                    print(f"     ✅ Firecrawl fallback for {source_name}")
                    return articles
            except Exception:
                pass

        print(f"     ❌ All methods failed for {source_name}")
        return articles

    def fetch_google_news_rss(
        self, query: str, label: str = "", hl: str = "en-US", gl: str = "US", lang: str = "en"
    ) -> List[Dict]:
        """
        Fetch from Google News RSS search — always reachable from CI.
        Returns up to 20 articles per query.
        """
        articles = []
        encoded = quote(query)
        ceid = f"{gl}:{lang}"
        url = self.GOOGLE_NEWS_RSS.format(query=encoded, hl=hl, gl=gl, ceid=ceid)

        try:
            # Google News RSS doesn't need auth; feedparser can fetch directly
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                article = self._entry_to_article(entry, url)
                if article:
                    article["source"] = f"Google News / {label or query}"
                    article["fetch_method"] = "google_news_rss"
                    articles.append(article)
        except Exception as e:
            print(f"  ⚠️ Google News RSS failed for '{query}': {e}")

        return articles

    # =========================================================
    # GOOGLE NEWS RSS BULK FETCH (called from fetch_all)
    # =========================================================

    def fetch_google_news_bulk(self, queries: Dict) -> List[Dict]:
        """
        Fetch a batch of Google News RSS queries from config.
        config format:
          google_news_rss:
            en:
              - query: "apple xiaomi smartphone launch"
                label: "T1-竞品-手机"
            zh:
              - query: "小米华为手机发布"
                label: "T1-竞品-手机-中"
        """
        all_articles = []
        en_queries = queries.get("en", [])
        zh_queries = queries.get("zh", [])

        print(f"🌐 Fetching Google News RSS ({len(en_queries)} EN + {len(zh_queries)} ZH queries)...")

        for item in en_queries:
            q = item.get("query", item) if isinstance(item, dict) else item
            label = item.get("label", "") if isinstance(item, dict) else ""
            articles = self.fetch_google_news_rss(q, label=label, hl="en-US", gl="US", lang="en")
            if articles:
                print(f"  ✅ [{label or q[:30]}]: {len(articles)} articles")
            all_articles.extend(articles)
            time.sleep(0.4)

        for item in zh_queries:
            q = item.get("query", item) if isinstance(item, dict) else item
            label = item.get("label", "") if isinstance(item, dict) else ""
            articles = self.fetch_google_news_rss(
                q, label=label, hl="zh-CN", gl="CN", lang="zh-Hans"
            )
            if articles:
                print(f"  ✅ [{label or q[:30]}]: {len(articles)} articles")
            all_articles.extend(articles)
            time.sleep(0.4)

        return all_articles

    # =========================================================
    # WEB PAGE SCRAPING
    # =========================================================

    def fetch_webpage(self, source_config: Dict) -> List[Dict]:
        """Fetch articles from HTML page using CSS selectors"""
        articles = []
        url = source_config.get("url", "")
        if not url:
            return articles

        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            container = source_config.get("container", "article")
            items = soup.select(container)[: source_config.get("limit", 15)]

            for item in items:
                title_elem = item.select_one(source_config.get("title_selector", ""))
                link_elem  = item.select_one(source_config.get("link_selector", ""))
                if not title_elem or not link_elem:
                    continue

                article = {
                    "title":        self._clean_text(title_elem.get_text(strip=True)),
                    "summary":      "",
                    "content":      "",
                    "link":         urljoin(url, link_elem.get("href", "")),
                    "published_raw": "",
                    "source":       urlparse(url).netloc,
                    "fetch_method": "webpage",
                }

                date_selector = source_config.get("date_selector")
                if date_selector:
                    date_elem = item.select_one(date_selector)
                    if date_elem:
                        article["published_raw"] = self._clean_text(date_elem.get_text(strip=True))

                if article["title"] and article["link"]:
                    articles.append(article)

        except Exception as e:
            print(f"  ⚠️ Webpage fetch failed for {url}: {e}")

        return articles

    # =========================================================
    # TOPIC-SPECIFIC ACTIVE SEARCH (used by GoogleNewsFetcher)
    # =========================================================

    def fetch_by_topic(
        self,
        topic_id: int,
        topic_sources: Dict[int, List[str]],
        topic_keywords: Dict[int, List[str]],
        days_back: int = 3,
    ) -> List[Dict]:
        """Actively fetch articles for a topic using Google News RSS keyword search"""
        articles = []
        keywords = topic_keywords.get(topic_id, [])

        print(f"     🔍 Active search for Topic {topic_id} ({len(keywords)} keywords)...")

        for keyword in keywords[:8]:
            articles.extend(
                self.fetch_google_news_rss(keyword, label=f"T{topic_id}")
            )
            time.sleep(0.3)

        # Also try direct source RSS feeds
        sources = topic_sources.get(topic_id, [])
        for domain in sources[:6]:
            for feed_url in [f"https://{domain}/feed", f"https://{domain}/rss", f"https://{domain}/rss.xml"]:
                try:
                    response = self.session.get(feed_url, timeout=8)
                    feed = feedparser.parse(response.content)
                    if feed.entries:
                        for entry in feed.entries[:5]:
                            article = self._entry_to_article(entry, feed_url)
                            if article:
                                articles.append(article)
                        break
                except Exception:
                    continue
            time.sleep(0.3)

        # Deduplicate
        seen, unique = set(), []
        for a in articles:
            key = a["title"][:50].lower()
            if key not in seen:
                seen.add(key)
                unique.append(a)

        print(f"     ✅ Topic {topic_id}: {len(unique)} unique articles")
        return unique[:20]

    # =========================================================
    # API FETCHING
    # =========================================================

    def fetch_api(self, source_config: Dict) -> List[Dict]:
        """Fetch from REST API endpoint"""
        articles = []
        url = source_config.get("url", "")
        if not url:
            return articles

        try:
            params  = source_config.get("params", {})
            headers = source_config.get("headers", {})
            req_headers = {**dict(self.session.headers), **headers}

            if source_config.get("method", "GET") == "GET":
                response = self.session.get(url, params=params, timeout=12, headers=req_headers)
            else:
                response = self.session.post(url, json=params, timeout=12, headers=req_headers)

            response.raise_for_status()
            data = response.json()

            items = data.get("data", data.get("posts", data.get("articles", [])))
            if not items and isinstance(data, list):
                items = data

            for item in items[: source_config.get("limit", 15)]:
                article = {
                    "title":        self._extract_field(item, ["title", "headline", "name"]),
                    "summary":      self._extract_field(item, ["summary", "description", "excerpt"]),
                    "content":      self._extract_field(item, ["content", "body", "text"]),
                    "link":         self._extract_field(item, ["link", "url", "permalink"]),
                    "published_raw": self._extract_field(item, ["published_date", "date", "pubDate"]),
                    "source":       urlparse(url).netloc,
                    "fetch_method": "api",
                }
                if article["title"] and article["link"]:
                    articles.append(article)

        except Exception as e:
            print(f"  ⚠️ API fetch failed for {url}: {e}")

        return articles

    # =========================================================
    # MAIN FETCH ORCHESTRATOR
    # =========================================================

    def fetch_all(self, sources: Dict) -> List[Dict]:
        """Fetch from all configured sources"""
        all_articles = []

        # 1. Google News RSS (primary reliable source)
        gn_config = sources.get("google_news_rss", {})
        if gn_config:
            articles = self.fetch_google_news_bulk(gn_config)
            all_articles.extend(articles)
            print(f"   ✅ Google News RSS total: {len(articles)} articles")

        # 2. RSS Feeds
        print("📡 Fetching RSS feeds...")
        for category, urls in sources.get("rss", {}).items():
            for url in urls:
                print(f"  📰 RSS: {url[:70]}...")
                articles = self.fetch_rss_with_fallback(url, category)
                all_articles.extend(articles)
                time.sleep(0.4)

        # 3. Web Scraping
        print("🕸️  Fetching web pages...")
        for name, config in sources.get("web_scraping", {}).items():
            url = config.get("url", "")
            if url:
                print(f"  🌐 {name}: {url[:60]}...")
                all_articles.extend(self.fetch_webpage(config))
                time.sleep(0.8)

        # 4. Firecrawl
        if self.firecrawl:
            print("🔥 Fetching with Firecrawl...")
            for name, config in sources.get("firecrawl", {}).items():
                url = config.get("url", "")
                if url:
                    print(f"  🔥 {name}: {url[:60]}...")
                    all_articles.extend(self.fetch_rss_with_fallback(url, name))
                    time.sleep(2)
        else:
            print("🔥 Firecrawl not available — skipping")

        # 5. APIs (only if endpoint is valid)
        print("🔌 Fetching APIs...")
        for name, config in sources.get("api", {}).items():
            url = config.get("url", "")
            if url and not config.get("disabled"):
                print(f"  📡 {name}: {url[:60]}...")
                all_articles.extend(self.fetch_api(config))
                time.sleep(0.5)

        print(f"✅ Total fetched: {len(all_articles)} articles")
        return all_articles

    # =========================================================
    # HELPERS
    # =========================================================

    def _entry_to_article(self, entry, source_url: str) -> Optional[Dict]:
        """Convert a feedparser entry to article dict"""
        title = self._clean_text(entry.get("title", ""))
        link  = entry.get("link", "")
        if not title or not link or len(title) < 5:
            return None
        summary = self._clean_text(entry.get("summary", entry.get("description", ""))[:500])
        content_list = entry.get("content", [])
        content = self._clean_text(content_list[0].get("value", summary) if content_list else summary)
        return {
            "title":        title,
            "summary":      summary,
            "content":      content,
            "link":         link,
            "published_raw": entry.get("published", entry.get("updated", "")),
            "source":       urlparse(source_url).netloc,
            "fetch_method": "rss",
        }

    def _get_backup_urls(self, original_url: str) -> List[str]:
        """Generate backup RSS URL variants"""
        backups = []
        if original_url.endswith("/feed"):
            backups += [original_url.replace("/feed", "/rss"), original_url + ".xml"]
        elif original_url.endswith("/rss"):
            backups += [original_url.replace("/rss", "/feed"), original_url + ".xml"]

        parsed = urlparse(original_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        backups += [
            f"{base}/feed", f"{base}/rss", f"{base}/rss.xml",
            f"{base}/feed.xml", f"{base}/index.xml",
            f"{base}/news/feed", f"{base}/news/rss",
        ]
        return list(dict.fromkeys(backups))  # deduplicate, preserve order

    def _extract_articles_from_markdown(self, markdown: str, base_url: str) -> List[Dict]:
        articles = []
        for line in markdown.split("\n")[:100]:
            m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line.strip())
            if m:
                title, link = m.group(1), m.group(2)
                if 10 < len(title) < 200:
                    articles.append({
                        "title": self._clean_text(title),
                        "summary": "", "content": "",
                        "link": urljoin(base_url, link),
                        "published_raw": "",
                        "source": urlparse(base_url).netloc,
                        "fetch_method": "firecrawl_markdown",
                    })
        return articles

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<.*?>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_field(self, item: Dict, names: List[str]) -> str:
        for name in names:
            if name in item:
                v = item[name]
                if isinstance(v, str):
                    return self._clean_text(v)
                if isinstance(v, dict) and "rendered" in v:
                    return self._clean_text(v["rendered"])
        return ""
