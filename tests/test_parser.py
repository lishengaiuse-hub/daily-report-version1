#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Parser module
"""

import unittest
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import ArticleParser

class TestParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = ArticleParser()
    
    def test_parse_rfc822_date(self):
        """Test parsing RFC822 date format"""
        date_str = "Mon, 15 Jan 2024 09:30:00 GMT"
        result = self.parser.parse_date(date_str)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)
    
    def test_parse_iso_date(self):
        """Test parsing ISO format date"""
        date_str = "2024-01-15T09:30:00Z"
        result = self.parser.parse_date(date_str)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
    
    def test_parse_relative_date(self):
        """Test parsing relative dates"""
        date_str = "2 days ago"
        result = self.parser.parse_date(date_str)
        
        self.assertIsNotNone(result)
        expected = datetime.now() - timedelta(days=2)
        self.assertEqual(result.date(), expected.date())
    
    def test_is_from_yesterday(self):
        """Test yesterday detection"""
        yesterday = datetime.now() - timedelta(days=1)
        today = datetime.now()
        two_days_ago = datetime.now() - timedelta(days=2)
        
        self.assertTrue(self.parser.is_from_yesterday(yesterday))
        self.assertFalse(self.parser.is_from_yesterday(today))
        self.assertFalse(self.parser.is_from_yesterday(two_days_ago))
        self.assertTrue(self.parser.is_from_yesterday(None))  # Unknown date kept
    
    def test_extract_content(self):
        """Test content extraction priority"""
        article = {
            'content': 'Full article content here',
            'summary': 'Short summary',
            'title': 'Article Title'
        }
        
        content = self.parser.extract_content(article)
        self.assertEqual(content, 'Full article content here')
    
    def test_extract_content_fallback(self):
        """Test content extraction fallback"""
        article = {
            'summary': 'Short summary only',
            'title': 'Article Title'
        }
        
        content = self.parser.extract_content(article)
        self.assertEqual(content, 'Short summary only')
    
    def test_extract_content_title_only(self):
        """Test content extraction with only title"""
        article = {
            'title': 'Only Title Available'
        }
        
        content = self.parser.extract_content(article)
        self.assertEqual(content, 'Only Title Available')
    
    def test_clean_text_html(self):
        """Test HTML removal"""
        html_text = "<p>Hello <strong>World</strong></p>"
        cleaned = self.parser._clean_text(html_text)
        
        self.assertEqual(cleaned, "Hello World")
    
    def test_clean_text_whitespace(self):
        """Test whitespace normalization"""
        messy = "This   has   many    spaces"
        cleaned = self.parser._clean_text(messy)
        
        self.assertEqual(cleaned, "This has many spaces")
    
    def test_parse_article_valid(self):
        """Test parsing a valid article"""
        article = {
            'title': 'Test Article',
            'summary': 'This is a test summary',
            'link': 'https://example.com/test',
            'source': 'example.com',
            'published_raw': '2024-01-15T10:00:00Z'
        }
        
        result = self.parser.parse_article(article)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Test Article')
        self.assertEqual(result['source'], 'example.com')
    
    def test_parse_article_missing_title(self):
        """Test parsing article with missing title"""
        article = {
            'summary': 'No title here',
            'link': 'https://example.com/test'
        }
        
        result = self.parser.parse_article(article)
        self.assertIsNone(result)
    
    def test_parse_article_missing_link(self):
        """Test parsing article with missing link"""
        article = {
            'title': 'Test Article',
            'summary': 'No link here'
        }
        
        result = self.parser.parse_article(article)
        self.assertIsNone(result)
    
    def test_parse_batch(self):
        """Test batch parsing"""
        articles = [
            {'title': 'Article 1', 'link': 'https://example.com/1'},
            {'title': 'Article 2', 'link': 'https://example.com/2'},
            {'title': '', 'link': 'https://example.com/3'},  # Invalid
        ]
        
        results = self.parser.parse_batch(articles)
        
        self.assertEqual(len(results), 2)

if __name__ == '__main__':
    unittest.main()
