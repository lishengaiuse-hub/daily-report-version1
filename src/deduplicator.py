#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Layer Deduplication Module for Samsung CE Intelligence
Implements URL hash, title similarity, and semantic embedding deduplication
"""

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json

# Optional imports with fallbacks
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    from difflib import SequenceMatcher
    RAPIDFUZZ_AVAILABLE = False
    print("⚠️ rapidfuzz not available, falling back to difflib")

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    print("⚠️ sentence-transformers not available, semantic dedup disabled")

@dataclass
class DuplicateRecord:
    """Record of a duplicate detection"""
    original_id: str
    duplicate_id: str
    layer: str  # 'url', 'title', 'semantic'
    similarity_score: float
    reason: str

@dataclass
class Article:
    """Article data structure"""
    id: str
    title: str
    content: str
    url: str
    source: str
    published_date: Optional[datetime]
    fetched_date: datetime
    reliability_score: float
    topics: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content[:5000],  # Truncate for storage
            'url': self.url,
            'source': self.source,
            'published_date': self.published_date.isoformat() if self.published_date else None,
            'fetched_date': self.fetched_date.isoformat(),
            'reliability_score': self.reliability_score,
            'topics': json.dumps(self.topics)
        }

class Deduplicator:
    """
    Multi-layer deduplication engine
    
    Layers:
    1. URL Hash: Exact match after normalizing URLs
    2. Title Similarity: Fuzzy matching >= 0.9 threshold
    3. Semantic Embedding: Cosine similarity >= 0.85 threshold
    """
    
    def __init__(self, db_path: str = "data/history.db", config: Dict = None):
        self.db_path = Path(db_path)
        self.config = config or self._default_config()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize embedding model if available
        self.embedding_model = None
        self.embedding_cache = {}
        if EMBEDDING_AVAILABLE and self.config.get('semantic', {}).get('enabled', True):
            try:
                model_name = self.config.get('semantic', {}).get('model', 'all-MiniLM-L6-v2')
                self.embedding_model = SentenceTransformer(model_name)
                print(f"✅ Loaded embedding model: {model_name}")
            except Exception as e:
                print(f"⚠️ Failed to load embedding model: {e}")
        
        self._init_database()
        self.stats = {
            'total_before': 0,
            'total_after': 0,
            'duplicates_removed': 0,
            'by_layer': defaultdict(int),
            'removed_items': []
        }
    
    def _default_config(self) -> Dict:
        return {
            'url_hash': {'enabled': True, 'ignore_params': ['utm_source', 'utm_medium', 'ref']},
            'title': {'enabled': True, 'threshold': 0.9},
            'semantic': {'enabled': EMBEDDING_AVAILABLE, 'threshold': 0.85},
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
                content_hash TEXT,
                url TEXT,
                source TEXT,
                published_date TEXT,
                fetched_date TEXT,
                reliability_score REAL,
                topics TEXT,
                embedding BLOB,
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
        from urllib.parse import urlparse, parse_qs, urlunparse
        
        parsed = urlparse(url)
        
        # Remove ignored parameters
        if self.config.get('url_hash', {}).get('ignore_params'):
            ignore_params = set(self.config['url_hash']['ignore_params'])
            query_params = parse_qs(parsed.query)
            filtered_params = {k: v for k, v in query_params.items() if k not in ignore_params}
            
            # Rebuild query string
            from urllib.parse import urlencode
            new_query = urlencode(filtered_params, doseq=True) if filtered_params else ''
            
            parsed = parsed._replace(query=new_query, fragment='')
        
        return urlunparse(parsed)
    
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
        noise_words = ['the', 'a', 'an', 'and', 'or', 'of', 'to', 'for', 'in', 'on', 'at']
        words = title.split()
        words = [w for w in words if w not in noise_words]
        return ' '.join(words)
    
    def _compute_url_hash(self, url: str) -> str:
        """Compute SHA256 hash of normalized URL"""
        normalized = self._normalize_url(url)
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _compute_title_similarity(self, title1: str, title2: str) -> float:
        """Compute similarity between two titles"""
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)
        
        if not norm1 or not norm2:
            return 0.0
        
        if RAPIDFUZZ_AVAILABLE:
            return fuzz.ratio(norm1, norm2) / 100.0
        else:
            return SequenceMatcher(None, norm1, norm2).ratio()
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of content for exact matching"""
        # Take first 1000 chars and normalize
        content = re.sub(r'\s+', ' ', content)[:1000]
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding vector for text"""
        if not self.embedding_model:
            return None
        
        # Check cache
        text_hash = hashlib.md5(text[:500].encode()).hexdigest()
        if text_hash in self.embedding_cache:
            return self.embedding_cache[text_hash]
        
        try:
            # Truncate long text for performance
            truncated = text[:2000]
            embedding = self.embedding_model.encode(truncated)
            self.embedding_cache[text_hash] = embedding
            return embedding
        except Exception as e:
            print(f"⚠️ Embedding failed: {e}")
            return None
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        if a is None or b is None:
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    
    def _check_history_duplicate(self, article: Article) -> Tuple[bool, Optional[Dict], str]:
        """Check if article already exists in history database"""
        url_hash = self._compute_url_hash(article.url)
        
        # Check URL hash (exact match)
        cursor = self.conn.execute(
            "SELECT id, title, published_date, reliability_score FROM articles WHERE url_hash = ?",
            (url_hash,)
        )
        existing = cursor.fetchone()
        if existing:
            return True, {'id': existing[0], 'title': existing[1]}, "URL (history)"
        
        # Check title similarity against last N days
        cutoff_date = (datetime.now() - timedelta(days=self.config.get('history_days', 7))).isoformat()
        cursor = self.conn.execute(
            "SELECT id, title, published_date, reliability_score FROM articles WHERE fetched_date > ?",
            (cutoff_date,)
        )
        
        for existing in cursor.fetchall():
            similarity = self._compute_title_similarity(article.title, existing[1])
            if similarity >= self.config.get('title', {}).get('threshold', 0.9):
                return True, {'id': existing[0], 'title': existing[1]}, f"Title (similarity: {similarity:.2f})"
        
        return False, None, ""
    
    def _deduplicate_current_batch(self, articles: List[Article]) -> List[Article]:
        """Deduplicate within the current batch"""
        kept = []
        
        for i, article in enumerate(articles):
            is_duplicate = False
            duplicate_reason = ""
            duplicate_with = None
            
            # Layer 1: URL hash check
            if self.config.get('url_hash', {}).get('enabled', True):
                for existing in kept:
                    if self._compute_url_hash(article.url) == self._compute_url_hash(existing.url):
                        is_duplicate = True
                        duplicate_reason = "URL hash match"
                        duplicate_with = existing
                        self.stats['by_layer']['url'] += 1
                        break
            
            # Layer 2: Title similarity
            if not is_duplicate and self.config.get('title', {}).get('enabled', True):
                threshold = self.config['title']['threshold']
                for existing in kept:
                    similarity = self._compute_title_similarity(article.title, existing.title)
                    if similarity >= threshold:
                        is_duplicate = True
                        duplicate_reason = f"Title similarity ({similarity:.2f} >= {threshold})"
                        duplicate_with = existing
                        self.stats['by_layer']['title'] += 1
                        break
            
            # Layer 3: Semantic similarity (if available)
            if not is_duplicate and self.config.get('semantic', {}).get('enabled', True):
                threshold = self.config['semantic']['threshold']
                article_embedding = self._get_embedding(article.title + " " + article.content[:500])
                
                for existing in kept:
                    existing_embedding = self._get_embedding(existing.title + " " + existing.content[:500])
                    similarity = self._cosine_similarity(article_embedding, existing_embedding)
                    if similarity >= threshold:
                        is_duplicate = True
                        duplicate_reason = f"Semantic similarity ({similarity:.2f} >= {threshold})"
                        duplicate_with = existing
                        self.stats['by_layer']['semantic'] += 1
                        break
            
            if is_duplicate:
                self.stats['duplicates_removed'] += 1
                self.stats['removed_items'].append({
                    'title': article.title,
                    'url': article.url,
                    'reason': duplicate_reason,
                    'duplicate_of': duplicate_with.title if duplicate_with else "unknown"
                })
                # Apply priority rules to decide which to keep
                if duplicate_with and self._should_replace(article, duplicate_with):
                    # Remove the existing and keep the new one
                    kept.remove(duplicate_with)
                    kept.append(article)
                    self.stats['duplicates_removed'] -= 1  # Adjust count
            else:
                kept.append(article)
        
        return kept
    
    def _should_replace(self, new: Article, existing: Article) -> bool:
        """Apply priority rules to decide if new article should replace existing"""
        priority = self.config.get('priority', {})
        
        # Prefer longer content
        if priority.get('prefer_longer_content'):
            if len(new.content) > len(existing.content) * 1.2:  # 20% longer
                return True
            elif len(existing.content) > len(new.content) * 1.2:
                return False
        
        # Prefer earlier publication date
        if priority.get('prefer_earlier_date') and new.published_date and existing.published_date:
            if new.published_date < existing.published_date:
                return True
            elif existing.published_date < new.published_date:
                return False
        
        # Prefer higher reliability
        if priority.get('prefer_higher_reliability'):
            if new.reliability_score > existing.reliability_score:
                return True
            elif existing.reliability_score > new.reliability_score:
                return False
        
        # Default: keep existing
        return False
    
    def save_to_history(self, articles: List[Article]):
        """Save deduplicated articles to history database"""
        for article in articles:
            try:
                self.conn.execute("""
                    INSERT OR REPLACE INTO articles 
                    (id, url_hash, title, title_normalized, content_hash, url, source, 
                     published_date, fetched_date, reliability_score, topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.id,
                    self._compute_url_hash(article.url),
                    article.title,
                    self._normalize_title(article.title),
                    self._compute_content_hash(article.content),
                    article.url,
                    article.source,
                    article.published_date.isoformat() if article.published_date else None,
                    article.fetched_date.isoformat(),
                    article.reliability_score,
                    json.dumps(article.topics)
                ))
            except Exception as e:
                print(f"⚠️ Failed to save article {article.id}: {e}")
        
        self.conn.commit()
    
    def deduplicate(self, articles: List[Dict]) -> Tuple[List[Dict], Dict]:
        """
        Main deduplication entry point
        
        Args:
            articles: List of article dictionaries
            
        Returns:
            Tuple of (deduplicated_articles, statistics)
        """
        # Reset stats
        self.stats = {
            'total_before': len(articles),
            'total_after': 0,
            'duplicates_removed': 0,
            'by_layer': defaultdict(int),
            'removed_items': []
        }
        
        # Convert dicts to Article objects
        article_objects = []
        for idx, a in enumerate(articles):
            article = Article(
                id=f"{a.get('source', 'unknown')}_{idx}_{hashlib.md5(a.get('title', '').encode()).hexdigest()[:8]}",
                title=a.get('title', ''),
                content=a.get('summary', a.get('content', '')),
                url=a.get('link', a.get('url', '')),
                source=a.get('source', 'unknown'),
                published_date=a.get('published_date'),
                fetched_date=datetime.now(),
                reliability_score=a.get('reliability_score', 0.6),
                topics=a.get('topics', [])
            )
            article_objects.append(article)
        
        # Step 1: Check against history
        history_duplicates = []
        unique_articles = []
        for article in article_objects:
            is_dup, existing, reason = self._check_history_duplicate(article)
            if is_dup:
                self.stats['duplicates_removed'] += 1
                self.stats['by_layer']['history'] += 1
                self.stats['removed_items'].append({
                    'title': article.title,
                    'url': article.url,
                    'reason': f"History: {reason}",
                    'duplicate_of': existing['title'] if existing else "historical"
                })
                history_duplicates.append(article)
            else:
                unique_articles.append(article)
        
        # Step 2: Deduplicate within current batch
        final_articles = self._deduplicate_current_batch(unique_articles)
        
        # Step 3: Save to history
        self.save_to_history(final_articles)
        
        # Convert back to dict format
        result = []
        for article in final_articles:
            result.append({
                'title': article.title,
                'summary': article.content,
                'link': article.url,
                'source': article.source,
                'published_date': article.published_date,
                'reliability_score': article.reliability_score,
                'topics': article.topics,
                'id': article.id
            })
        
        self.stats['total_after'] = len(result)
        
        return result, dict(self.stats)
    
    def get_deduplication_report(self) -> str:
        """Generate human-readable deduplication report"""
        report = []
        report.append("## 📊 Deduplication Report")
        report.append(f"- **Before dedup:** {self.stats['total_before']} articles")
        report.append(f"- **After dedup:** {self.stats['total_after']} articles")
        report.append(f"- **Removed:** {self.stats['duplicates_removed']} duplicates")
        report.append("\n**By detection layer:**")
        for layer, count in self.stats['by_layer'].items():
            report.append(f"  - {layer}: {count}")
        
        if self.stats['removed_items'] and len(self.stats['removed_items']) <= 20:
            report.append("\n**Removed items:**")
            for item in self.stats['removed_items'][:10]:
                report.append(f"  - ❌ {item['title'][:60]}... ({item['reason']})")
        
        return "\n".join(report)
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()
