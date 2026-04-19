#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Layer Deduplication Module for Samsung CE Intelligence
Version: 3.0 - 新增跨栏目去重功能
Implements: URL hash, title similarity, cross-topic deduplication
"""

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import json

# Try to import rapidfuzz for better similarity
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    from difflib import SequenceMatcher
    RAPIDFUZZ_AVAILABLE = False
    print("⚠️ rapidfuzz not available, falling back to difflib")


class Deduplicator:
    """
    Multi-layer deduplication engine with cross-topic support
    
    Layers:
    1. URL Hash: Exact match after normalizing URLs
    2. Title Similarity: Fuzzy matching >= 0.9 threshold
    3. Cross-Topic: Same article appears in multiple topics (保留优先级最高的)
    
    Topic优先级: T1(竞品) > T2(技术) > T3(制造) > T4(展会) > T5(供应链)
    """
    
    # 跨栏目去重优先级 (数值越高优先级越高)
    TOPIC_PRIORITY = {
        1: 5,   # 竞品动态 - 最高优先级
        2: 4,   # 技术/材料
        3: 3,   # 制造
        4: 2,   # 展会
        5: 1    # 供应链风险 - 最低优先级
    }
    
    def __init__(self, db_path: str = "data/history.db", config: Dict = None):
        self.db_path = Path(db_path)
        self.config = config or self._default_config()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        self.stats = {
            'total_before': 0,
            'total_after': 0,
            'duplicates_removed': 0,
            'cross_topic_removed': 0,
            'by_layer': defaultdict(int),
            'removed_items': []
        }
    
    def _default_config(self) -> Dict:
        return {
            'url_hash': {'enabled': True, 'ignore_params': ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'source']},
            'title': {'enabled': True, 'threshold': 0.9},
            'semantic': {'enabled': False, 'threshold': 0.85},
            'history_days': 7,
            'priority': {
                'prefer_longer_content': True,
                'prefer_earlier_date': True,
                'prefer_higher_reliability': True
            }
        }
    
    def _init_database(self):
        """Initialize SQLite database for historical deduplication"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                url_hash TEXT UNIQUE,
                title TEXT,
                title_normalized TEXT,
                url TEXT,
                source TEXT,
                published_date TEXT,
                fetched_date TEXT,
                reliability_score REAL,
                topics TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_url_hash ON articles(url_hash)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_title_normalized ON articles(title_normalized)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fetched_date ON articles(fetched_date)
        """)
        self.conn.commit()
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing query parameters and fragments"""
        from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
        
        if not url:
            return ""
        
        try:
            parsed = urlparse(url)
            
            # Remove ignored parameters
            ignore_params = self.config.get('url_hash', {}).get('ignore_params', [])
            if ignore_params:
                ignore_params_set = set(ignore_params)
                query_params = parse_qs(parsed.query)
                filtered_params = {k: v for k, v in query_params.items() if k not in ignore_params_set}
                
                # Rebuild query string
                new_query = urlencode(filtered_params, doseq=True) if filtered_params else ''
                
                # Remove trailing slash for consistency
                path = parsed.path.rstrip('/')
                
                parsed = parsed._replace(query=new_query, fragment='', path=path)
            
            return urlunparse(parsed)
        except Exception:
            return url
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison"""
        if not title:
            return ""
        # Lowercase
        title = title.lower()
        # Remove special characters
        title = re.sub(r'[^\w\s]', ' ', title)
        # Remove extra whitespace
        title = re.sub(r'\s+', ' ', title).strip()
        # Remove common noise words
        noise_words = ['the', 'a', 'an', 'and', 'or', 'of', 'to', 'for', 'in', 'on', 'at', 'with', 'by']
        words = title.split()
        words = [w for w in words if w not in noise_words]
        return ' '.join(words)
    
    def _compute_url_hash(self, url: str) -> str:
        """Compute SHA256 hash of normalized URL"""
        if not url:
            return hashlib.sha256("".encode()).hexdigest()
        normalized = self._normalize_url(url)
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _compute_title_similarity(self, title1: str, title2: str) -> float:
        """Compute similarity between two titles"""
        if not title1 or not title2:
            return 0.0
        
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)
        
        if not norm1 or not norm2:
            return 0.0
        
        if RAPIDFUZZ_AVAILABLE:
            return fuzz.ratio(norm1, norm2) / 100.0
        else:
            from difflib import SequenceMatcher
            return SequenceMatcher(None, norm1, norm2).ratio()
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of content for exact matching"""
        content = re.sub(r'\s+', ' ', content)[:1000]
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _check_history_duplicate(self, article: Dict) -> Tuple[bool, Optional[Dict], str]:
        """Check if article already exists in history database"""
        url_hash = self._compute_url_hash(article.get('link', article.get('url', '')))
        
        # Check URL hash (exact match)
        cursor = self.conn.execute(
            "SELECT id, title, url FROM articles WHERE url_hash = ?",
            (url_hash,)
        )
        existing = cursor.fetchone()
        if existing:
            return True, {'id': existing[0], 'title': existing[1]}, "URL (history)"
        
        # Check title similarity against last N days
        history_days = self.config.get('history_days', 7)
        cutoff_date = (datetime.now() - timedelta(days=history_days)).isoformat()
        cursor = self.conn.execute(
            "SELECT id, title, url FROM articles WHERE fetched_date > ?",
            (cutoff_date,)
        )
        
        article_title = article.get('title', '')
        title_threshold = self.config.get('title', {}).get('threshold', 0.9)
        
        for existing in cursor.fetchall():
            similarity = self._compute_title_similarity(article_title, existing[1])
            if similarity >= title_threshold:
                return True, {'id': existing[0], 'title': existing[1]}, f"Title (similarity: {similarity:.2f})"
        
        return False, None, ""
    
    def _deduplicate_current_batch(self, articles: List[Dict]) -> List[Dict]:
        """Deduplicate within the current batch"""
        kept = []
        
        url_hash_config = self.config.get('url_hash', {'enabled': True})
        title_config = self.config.get('title', {'enabled': True, 'threshold': 0.9})
        
        for article in articles:
            is_duplicate = False
            duplicate_reason = ""
            duplicate_with = None
            
            # Layer 1: URL hash check
            if url_hash_config.get('enabled', True):
                article_url_hash = self._compute_url_hash(article.get('link', article.get('url', '')))
                for existing in kept:
                    existing_url_hash = self._compute_url_hash(existing.get('link', existing.get('url', '')))
                    if article_url_hash == existing_url_hash:
                        is_duplicate = True
                        duplicate_reason = "URL hash match"
                        duplicate_with = existing
                        self.stats['by_layer']['url'] += 1
                        break
            
            # Layer 2: Title similarity
            if not is_duplicate and title_config.get('enabled', True):
                threshold = title_config.get('threshold', 0.9)
                article_title = article.get('title', '')
                for existing in kept:
                    similarity = self._compute_title_similarity(article_title, existing.get('title', ''))
                    if similarity >= threshold:
                        is_duplicate = True
                        duplicate_reason = f"Title similarity ({similarity:.2f} >= {threshold})"
                        duplicate_with = existing
                        self.stats['by_layer']['title'] += 1
                        break
            
            if is_duplicate:
                self.stats['duplicates_removed'] += 1
                if len(self.stats['removed_items']) < 20:
                    self.stats['removed_items'].append({
                        'title': article.get('title', 'Unknown')[:50],
                        'url': article.get('link', article.get('url', '')),
                        'reason': duplicate_reason,
                        'duplicate_of': duplicate_with.get('title', 'unknown')[:50] if duplicate_with else "unknown"
                    })
                # Apply priority rules to decide which to keep
                if duplicate_with and self._should_replace(article, duplicate_with):
                    kept.remove(duplicate_with)
                    kept.append(article)
                    self.stats['duplicates_removed'] -= 1
            else:
                kept.append(article)
        
        return kept
    
    def _should_replace(self, new: Dict, existing: Dict) -> bool:
        """Apply priority rules to decide if new article should replace existing"""
        priority = self.config.get('priority', {})
        
        # Prefer longer content
        if priority.get('prefer_longer_content'):
            new_content = new.get('summary', new.get('content', ''))
            existing_content = existing.get('summary', existing.get('content', ''))
            if len(new_content) > len(existing_content) * 1.2:
                return True
            elif len(existing_content) > len(new_content) * 1.2:
                return False
        
        # Prefer earlier publication date
        if priority.get('prefer_earlier_date'):
            new_date = new.get('published_date')
            existing_date = existing.get('published_date')
            if new_date and existing_date:
                if isinstance(new_date, str):
                    try:
                        new_date = datetime.fromisoformat(new_date)
                    except:
                        pass
                if isinstance(existing_date, str):
                    try:
                        existing_date = datetime.fromisoformat(existing_date)
                    except:
                        pass
                if new_date and existing_date and new_date < existing_date:
                    return True
                elif existing_date and new_date and existing_date < new_date:
                    return False
        
        # Prefer higher reliability
        if priority.get('prefer_higher_reliability'):
            new_score = new.get('reliability_score', 0.5)
            existing_score = existing.get('reliability_score', 0.5)
            if new_score > existing_score:
                return True
            elif existing_score > new_score:
                return False
        
        return False
    
    def save_to_history(self, articles: List[Dict]):
        """Save deduplicated articles to history database"""
        for article in articles:
            try:
                article_id = hashlib.md5(
                    f"{article.get('source', 'unknown')}_{article.get('title', '')}".encode()
                ).hexdigest()[:16]
                
                self.conn.execute("""
                    INSERT OR REPLACE INTO articles 
                    (id, url_hash, title, title_normalized, url, source, 
                     published_date, fetched_date, reliability_score, topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article_id,
                    self._compute_url_hash(article.get('link', article.get('url', ''))),
                    article.get('title', ''),
                    self._normalize_title(article.get('title', '')),
                    article.get('link', article.get('url', '')),
                    article.get('source', 'unknown'),
                    article.get('published_date').isoformat() if article.get('published_date') else None,
                    datetime.now().isoformat(),
                    article.get('reliability_score', 0.6),
                    json.dumps(article.get('topics', []))
                ))
            except Exception as e:
                print(f"⚠️ Failed to save article: {e}")
        
        self.conn.commit()
    
    def deduplicate(self, articles: List[Dict]) -> Tuple[List[Dict], Dict]:
        """Main deduplication entry point"""
        print(f"   Starting deduplication with {len(articles)} articles...")
        
        self.stats = {
            'total_before': len(articles),
            'total_after': 0,
            'duplicates_removed': 0,
            'cross_topic_removed': 0,
            'by_layer': defaultdict(int),
            'removed_items': []
        }
        
        if not articles:
            return [], self.stats
        
        # Step 1: Check against history
        unique_articles = []
        for article in articles:
            is_dup, existing, reason = self._check_history_duplicate(article)
            if is_dup:
                self.stats['duplicates_removed'] += 1
                self.stats['by_layer']['history'] += 1
                if len(self.stats['removed_items']) < 20:
                    self.stats['removed_items'].append({
                        'title': article.get('title', 'Unknown')[:50],
                        'url': article.get('link', ''),
                        'reason': f"History: {reason}",
                        'duplicate_of': existing['title'][:50] if existing else "historical"
                    })
            else:
                unique_articles.append(article)
        
        print(f"   After history check: {len(unique_articles)} unique")
        
        # Step 2: Deduplicate within current batch
        final_articles = self._deduplicate_current_batch(unique_articles)
        
        # Step 3: Save to history
        self.save_to_history(final_articles)
        
        self.stats['total_after'] = len(final_articles)
        
        print(f"   Final: {self.stats['total_after']} articles after dedup")
        
        return final_articles, dict(self.stats)
    
    def cross_topic_deduplicate(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
        """
        跨栏目去重：同一新闻只保留在优先级最高的Topic
        
        Topic优先级: T1(竞品) > T2(技术) > T3(制造) > T4(展会) > T5(供应链)
        
        Args:
            articles_by_topic: {topic_id: [articles]}
            
        Returns:
            去重后的 {topic_id: [articles]}
        """
        # 收集所有文章的指纹
        article_fingerprints = {}
        
        before_total = sum(len(articles) for articles in articles_by_topic.values())
        
        for topic_id, articles in articles_by_topic.items():
            for article in articles:
                # 生成指纹：URL + 标题前50字符 + 内容前100字符
                url = article.get('link', article.get('url', ''))
                title = article.get('title', '')[:50]
                content = article.get('summary', article.get('content', ''))[:100]
                fingerprint = hashlib.md5(f"{url}_{title}_{content}".encode()).hexdigest()
                
                priority = self.TOPIC_PRIORITY.get(topic_id, 0)
                
                if fingerprint not in article_fingerprints:
                    article_fingerprints[fingerprint] = (topic_id, article, priority)
                else:
                    existing_topic, existing_article, existing_priority = article_fingerprints[fingerprint]
                    # 保留优先级更高的
                    if priority > existing_priority:
                        article_fingerprints[fingerprint] = (topic_id, article, priority)
        
        # 重建按Topic分组的文章
        result = {tid: [] for tid in range(1, 6)}
        for fingerprint, (topic_id, article, _) in article_fingerprints.items():
            result[topic_id].append(article)
        
        after_total = sum(len(articles) for articles in result.values())
        removed = before_total - after_total
        
        self.stats['by_layer']['cross_topic'] = removed
        self.stats['duplicates_removed'] += removed
        
        print(f"   🔄 Cross-topic dedup: {before_total} → {after_total} (removed {removed} duplicates)")
        
        return result
    
    def get_deduplication_report(self) -> str:
        """Generate human-readable deduplication report"""
        report = []
        report.append("## 📊 Deduplication Report")
        report.append(f"- **Before dedup:** {self.stats['total_before']} articles")
        report.append(f"- **After dedup:** {self.stats['total_after']} articles")
        report.append(f"- **Removed:** {self.stats['duplicates_removed']} duplicates")
        report.append(f"  - Cross-topic removed: {self.stats.get('cross_topic_removed', 0)}")
        report.append("\n**By detection layer:**")
        for layer, count in self.stats['by_layer'].items():
            report.append(f"  - {layer}: {count}")
        
        if self.stats['removed_items'] and len(self.stats['removed_items']) <= 20:
            report.append("\n**Sample removed items:**")
            for item in self.stats['removed_items'][:5]:
                report.append(f"  - ❌ {item['title']}... ({item['reason']})")
        
        return "\n".join(report)
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()
