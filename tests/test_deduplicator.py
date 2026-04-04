#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Deduplicator module
"""

import unittest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.deduplicator import Deduplicator, Article

class TestDeduplicator(unittest.TestCase):
    
    def setUp(self):
        """Set up test database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.dedup = Deduplicator(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up"""
        self.dedup.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_url_normalization(self):
        """Test URL normalization removes tracking parameters"""
        url1 = "https://example.com/news?id=123&utm_source=google"
        url2 = "https://example.com/news?id=123&utm_medium=email"
        
        normalized1 = self.dedup._normalize_url(url1)
        normalized2 = self.dedup._normalize_url(url2)
        
        self.assertEqual(normalized1, normalized2)
    
    def test_title_normalization(self):
        """Test title normalization"""
        title1 = "Apple Launches New iPhone!"
        title2 = "Apple launches new iPhone"
        
        norm1 = self.dedup._normalize_title(title1)
        norm2 = self.dedup._normalize_title(title2)
        
        self.assertEqual(norm1, norm2)
    
    def test_title_similarity(self):
        """Test title similarity calculation"""
        title1 = "Samsung announces new OLED TV"
        title2 = "Samsung announces new OLED television"
        
        similarity = self.dedup._compute_title_similarity(title1, title2)
        
        self.assertGreater(similarity, 0.85)
    
    def test_url_hash_duplicate_detection(self):
        """Test URL hash duplicate detection"""
        articles = [
            {
                'title': 'Test Article 1',
                'summary': 'Content 1',
                'link': 'https://example.com/news?id=1&utm_source=test',
                'source': 'test.com',
                'published_date': datetime.now()
            },
            {
                'title': 'Test Article 2',
                'summary': 'Content 2',
                'link': 'https://example.com/news?id=1&utm_medium=email',
                'source': 'test.com',
                'published_date': datetime.now()
            }
        ]
        
        result, stats = self.dedup.deduplicate(articles)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(stats['duplicates_removed'], 1)
    
    def test_title_similarity_duplicate_detection(self):
        """Test title similarity duplicate detection"""
        articles = [
            {
                'title': 'Apple releases new MacBook Pro with M3 chip',
                'summary': 'Apple announced today...',
                'link': 'https://apple.com/news/1',
                'source': 'apple.com',
                'published_date': datetime.now()
            },
            {
                'title': 'Apple releases new MacBook Pro with M3 processor',
                'summary': 'Apple has announced...',
                'link': 'https://techcrunch.com/apple-m3',
                'source': 'techcrunch.com',
                'published_date': datetime.now()
            }
        ]
        
        result, stats = self.dedup.deduplicate(articles)
        
        self.assertEqual(len(result), 1)
    
    def test_no_duplicate_different_articles(self):
        """Test different articles are not marked as duplicates"""
        articles = [
            {
                'title': 'Samsung unveils new foldable phone',
                'summary': 'Samsung announced...',
                'link': 'https://samsung.com/news/1',
                'source': 'samsung.com',
                'published_date': datetime.now()
            },
            {
                'title': 'Apple Vision Pro headset review',
                'summary': 'Apple Vision Pro...',
                'link': 'https://apple.com/news/2',
                'source': 'apple.com',
                'published_date': datetime.now()
            }
        ]
        
        result, stats = self.dedup.deduplicate(articles)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(stats['duplicates_removed'], 0)
    
    def test_history_duplicate_detection(self):
        """Test duplicate detection against historical data"""
        # First run
        articles1 = [
            {
                'title': 'Important News',
                'summary': 'Content',
                'link': 'https://example.com/news/1',
                'source': 'example.com',
                'published_date': datetime.now() - timedelta(days=1)
            }
        ]
        
        result1, _ = self.dedup.deduplicate(articles1)
        
        # Second run with same article
        articles2 = [
            {
                'title': 'Important News',
                'summary': 'Content',
                'link': 'https://example.com/news/1',
                'source': 'example.com',
                'published_date': datetime.now()
            }
        ]
        
        result2, stats2 = self.dedup.deduplicate(articles2)
        
        self.assertEqual(len(result2), 0)
        self.assertEqual(stats2['duplicates_removed'], 1)
    
    def test_priority_longer_content(self):
        """Test that longer content is preferred"""
        articles = [
            {
                'title': 'Same News',
                'summary': 'Short summary',
                'link': 'https://site1.com/news',
                'source': 'site1.com',
                'published_date': datetime.now()
            },
            {
                'title': 'Same News',
                'summary': 'Very long detailed summary with much more information about the topic',
                'link': 'https://site2.com/news',
                'source': 'site2.com',
                'published_date': datetime.now()
            }
        ]
        
        result, _ = self.dedup.deduplicate(articles)
        
        self.assertEqual(len(result), 1)
        self.assertIn('Very long', result[0]['summary'])
    
    def test_get_deduplication_report(self):
        """Test report generation"""
        articles = [
            {
                'title': 'Duplicate Title',
                'summary': 'Content 1',
                'link': 'https://example.com/1',
                'source': 'example.com',
                'published_date': datetime.now()
            },
            {
                'title': 'Duplicate Title',
                'summary': 'Content 2',
                'link': 'https://example.com/2',
                'source': 'example.com',
                'published_date': datetime.now()
            }
        ]
        
        _, _ = self.dedup.deduplicate(articles)
        report = self.dedup.get_deduplication_report()
        
        self.assertIn('Before dedup', report)
        self.assertIn('After dedup', report)
        self.assertIn('2 articles', report)

if __name__ == '__main__':
    unittest.main()
