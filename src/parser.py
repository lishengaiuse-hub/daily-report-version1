#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Article Parser for Samsung CE Intelligence
Handles date parsing, content extraction, and normalization
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dateutil import parser
from dateutil.parser import ParserError

class ArticleParser:
    """Parse and normalize article data"""
    
    def __init__(self):
        self.date_formats = [
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%a, %d %b %Y %H:%M:%S %Z',
            '%a, %d %b %Y %H:%M:%S %z',
            '%d %b %Y %H:%M:%S %Z',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d/%m/%Y',
            '%m/%d/%Y',
        ]
    
    def parse_date(self, date_string: Any) -> Optional[datetime]:
        """
        Parse date string to datetime object
        
        Args:
            date_string: Date string from RSS/API
            
        Returns:
            datetime object or None if parsing fails
        """
        if not date_string:
            return None
        
        if isinstance(date_string, datetime):
            return date_string
        
        if isinstance(date_string, (int, float)):
            try:
                return datetime.fromtimestamp(date_string)
            except:
                return None
        
        date_string = str(date_string).strip()
        
        # Try common formats first
        for fmt in self.date_formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue
        
        # Try dateutil parser as fallback
        try:
            dt = parser.parse(date_string)
            if dt.year < 2000 or dt.year > datetime.now().year + 1:
                return None
            return dt
        except (ParserError, ValueError, OverflowError):
            pass
        
        # Try relative dates (e.g., "2 days ago")
        relative = self._parse_relative_date(date_string)
        if relative:
            return relative
        
        return None
    
    def _parse_relative_date(self, date_string: str) -> Optional[datetime]:
        """Parse relative date strings like '2 days ago'"""
        date_string = date_string.lower()
        now = datetime.now()
        
        patterns = [
            (r'(\d+)\s+minute[s]?\s+ago', lambda m: now - timedelta(minutes=int(m.group(1)))),
            (r'(\d+)\s+hour[s]?\s+ago', lambda m: now - timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s+day[s]?\s+ago', lambda m: now - timedelta(days=int(m.group(1)))),
            (r'(\d+)\s+week[s]?\s+ago', lambda m: now - timedelta(weeks=int(m.group(1)))),
            (r'yesterday', lambda m: now - timedelta(days=1)),
            (r'today', lambda m: now),
        ]
        
        for pattern, calculator in patterns:
            match = re.search(pattern, date_string)
            if match:
                return calculator(match)
        
        return None
    
    def is_from_yesterday(self, published_date: Optional[datetime]) -> bool:
        """
        Check if article is from yesterday (T-1)
        
        Args:
            published_date: Parsed datetime object
            
        Returns:
            True if article is from yesterday
        """
        if not published_date:
            return True  # Keep if date unknown (conservative)
        
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).date()
        
        return published_date.date() == yesterday
    
    def extract_content(self, article: Dict) -> str:
        """
        Extract best available content from article
        
        Priority: content > summary > description > title
        """
        content = article.get('content', '')
        if content and len(content) > 50:
            return self._clean_text(content)
        
        summary = article.get('summary', article.get('description', ''))
        if summary and len(summary) > 50:
            return self._clean_text(summary)
        
        return self._clean_text(article.get('title', ''))
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<.*?>', '', text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters (keep basic punctuation)
        text = re.sub(r'[^\w\s\u4e00-\u9fff\-\.\,\!\?\(\)\[\]\:\;\"\']', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def parse_batch(self, articles: List[Dict]) -> List[Dict]:
        """
        Parse a batch of articles
        
        Args:
            articles: List of raw article dictionaries
            
        Returns:
            List of parsed articles with standardized fields
        """
        parsed = []
        
        for article in articles:
            parsed_article = self.parse_article(article)
            if parsed_article:
                parsed.append(parsed_article)
        
        return parsed
    
    def parse_article(self, article: Dict) -> Optional[Dict]:
        """
        Parse a single article
        
        Args:
            article: Raw article dictionary
            
        Returns:
            Parsed article with standardized fields or None if invalid
        """
        if not article.get('title'):
            return None
        
        # Parse date
        published_raw = article.get('published_raw', article.get('published_date', ''))
        published_date = self.parse_date(published_raw)
        
        # Check if from yesterday (T-1)
        if published_date and not self.is_from_yesterday(published_date):
            return None  # Skip older articles
        
        # Extract content
        content = self.extract_content(article)
        
        # Build standardized article
        parsed = {
            'title': self._clean_text(article['title']),
            'summary': content[:500] if content else article.get('title', ''),
            'content': content,
            'link': article.get('link', article.get('url', '')),
            'source': article.get('source', 'unknown'),
            'published_raw': published_raw,
            'published_date': published_date,
            'fetch_method': article.get('fetch_method', 'unknown'),
            'topics': [],
            'reliability_score': article.get('reliability_score', 0.6)
        }
        
        # Validate required fields
        if not parsed['link']:
            return None
        
        return parsed
