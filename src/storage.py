#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Storage Module for Samsung CE Intelligence
Manages SQLite database for historical deduplication and caching
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

class StorageManager:
    """Manage SQLite database operations"""
    
    def __init__(self, db_path: str = "data/history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            # Articles table
            conn.execute("""
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
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_url_hash ON articles(url_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_title_normalized ON articles(title_normalized)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fetched_date ON articles(fetched_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON articles(source)")
            
            # Cache table for API responses
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    expires_at TEXT
                )
            """)
            
            # Stats table for monitoring
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT,
                    articles_fetched INTEGER,
                    articles_deduped INTEGER,
                    duplicates_removed INTEGER,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def save_article(self, article: Dict) -> bool:
        """Save a single article to database"""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO articles 
                    (id, url_hash, title, title_normalized, content_hash, url, source, 
                     published_date, fetched_date, reliability_score, topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    article.get('id'),
                    article.get('url_hash'),
                    article.get('title', ''),
                    article.get('title_normalized', ''),
                    article.get('content_hash'),
                    article.get('url', ''),
                    article.get('source', ''),
                    article.get('published_date'),
                    datetime.now().isoformat(),
                    article.get('reliability_score', 0.6),
                    json.dumps(article.get('topics', []))
                ))
            return True
        except Exception as e:
            print(f"⚠️ Failed to save article: {e}")
            return False
    
    def save_articles_batch(self, articles: List[Dict]) -> int:
        """Save multiple articles in batch"""
        saved = 0
        for article in articles:
            if self.save_article(article):
                saved += 1
        return saved
    
    def article_exists(self, url_hash: str) -> bool:
        """Check if article with given URL hash exists"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM articles WHERE url_hash = ? LIMIT 1",
                (url_hash,)
            )
            return cursor.fetchone() is not None
    
    def get_recent_articles(self, days: int = 7) -> List[Dict]:
        """Get articles from last N days"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM articles 
                WHERE fetched_date > ?
                ORDER BY fetched_date DESC
            """, (cutoff,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_article_by_url_hash(self, url_hash: str) -> Optional[Dict]:
        """Get article by URL hash"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM articles WHERE url_hash = ?",
                (url_hash,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def save_run_stats(self, stats: Dict):
        """Save execution statistics"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO stats (run_date, articles_fetched, articles_deduped, duplicates_removed, details)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                stats.get('total_before', 0),
                stats.get('total_after', 0),
                stats.get('duplicates_removed', 0),
                json.dumps(stats)
            ))
    
    def get_run_history(self, limit: int = 30) -> List[Dict]:
        """Get recent run history"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM stats 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_cache(self, key: str, max_age_seconds: int = 3600) -> Optional[str]:
        """Get cached value if not expired"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            
            if row:
                expires_at = datetime.fromisoformat(row['expires_at'])
                if expires_at > datetime.now():
                    return row['value']
        
        return None
    
    def set_cache(self, key: str, value: str, ttl_seconds: int = 3600):
        """Set cached value with TTL"""
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cache (key, value, expires_at)
                VALUES (?, ?, ?)
            """, (key, value, expires_at.isoformat()))
    
    def cleanup_old_data(self, days: int = 30):
        """Delete old data from database"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self.get_connection() as conn:
            # Delete old articles (but keep for dedup)
            conn.execute("DELETE FROM stats WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM cache WHERE expires_at < ?", (datetime.now().isoformat(),))
            
            print(f"✅ Cleaned up data older than {days} days")
    
    def get_stats_summary(self) -> Dict:
        """Get database statistics summary"""
        with self.get_connection() as conn:
            article_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            cache_count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            run_count = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
            
            return {
                'total_articles': article_count,
                'cached_items': cache_count,
                'total_runs': run_count,
                'db_size': self.db_path.stat().st_size if self.db_path.exists() else 0
            }
