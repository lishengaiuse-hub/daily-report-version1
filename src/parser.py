#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Article Parser for Samsung CE Intelligence
Handles date parsing, content extraction, and normalization
Version: 2.0 - Fixed timezone compatibility
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dateutil import parser
from dateutil.parser import ParserError


class ArticleParser:
    """Parse and normalize article data with timezone-safe date parsing"""
    
    def __init__(self):
        self.date_formats = [
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%a, %d %b %Y %H:%M:%S %Z',
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S',
            '%d %b %Y %H:%M:%S %Z',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%Y年%m月%d日',
            '%Y-%m-%d %H:%M',
        ]
    
    def _make_naive(self, dt: Optional[datetime]) -> Optional[datetime]:
        """
        Convert datetime to naive (remove timezone info)
        
        Args:
            dt: Datetime object (could be naive or aware)
            
        Returns:
            Naive datetime or None
        """
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    
    def parse_date(self, date_string: Any) -> Optional[datetime]:
        """
        Parse date string to datetime object (returns naive datetime)
        
        Args:
            date_string: Date string from RSS/API
            
        Returns:
            Naive datetime object or None if parsing fails
        """
        if not date_string:
            return None
        
        # If already a datetime object
        if isinstance(date_string, datetime):
            return self._make_naive(date_string)
        
        # If it's a timestamp (int/float)
        if isinstance(date_string, (int, float)):
            try:
                dt = datetime.fromtimestamp(date_string)
                return self._make_naive(dt)
            except (ValueError, OSError, OverflowError):
                return None
        
        date_string = str(date_string).strip()
        
        # Try common formats first
        for fmt in self.date_formats:
            try:
                dt = datetime.strptime(date_string, fmt)
                return self._make_naive(dt)
            except ValueError:
                continue
        
        # Try dateutil parser as fallback (handles many formats)
        try:
            dt = parser.parse(date_string)
            
            # Validate year range
            if dt.year < 2000 or dt.year > datetime.now().year + 1:
                return None
            
            # Remove timezone info
            return self._make_naive(dt)
        except (ParserError, ValueError, OverflowError, TypeError):
            pass
        
        # Try relative dates (e.g., "2 days ago")
        relative = self._parse_relative_date(date_string)
        if relative:
            return relative
        
        # Try to extract date from string using regex
        extracted = self._extract_date_from_string(date_string)
        if extracted:
            return extracted
        
        return None
    
    def _parse_relative_date(self, date_string: str) -> Optional[datetime]:
        """
        Parse relative date strings like '2 days ago'
        
        Args:
            date_string: Relative date string
            
        Returns:
            Datetime object or None
        """
        date_string = date_string.lower().strip()
        now = datetime.now()
        
        patterns = [
            (r'(\d+)\s+minute[s]?\s+ago', lambda m: now - timedelta(minutes=int(m.group(1)))),
            (r'(\d+)\s+hour[s]?\s+ago', lambda m: now - timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s+day[s]?\s+ago', lambda m: now - timedelta(days=int(m.group(1)))),
            (r'(\d+)\s+week[s]?\s+ago', lambda m: now - timedelta(weeks=int(m.group(1)))),
            (r'yesterday', lambda m: now - timedelta(days=1)),
            (r'today', lambda m: now),
            (r'just now', lambda m: now),
            (r'(\d+)\s+minute[s]?\s+前', lambda m: now - timedelta(minutes=int(m.group(1)))),
            (r'(\d+)\s+小时前', lambda m: now - timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s+天前', lambda m: now - timedelta(days=int(m.group(1)))),
            (r'昨天', lambda m: now - timedelta(days=1)),
            (r'今天', lambda m: now),
        ]
        
        for pattern, calculator in patterns:
            match = re.search(pattern, date_string)
            if match:
                result = calculator(match)
                return self._make_naive(result)
        
        return None
    
    def _extract_date_from_string(self, text: str) -> Optional[datetime]:
        """
        Extract date from text using regex patterns
        
        Args:
            text: String containing date
            
        Returns:
            Datetime object or None
        """
        # Pattern: YYYY-MM-DD
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 2000 <= year <= datetime.now().year + 1 and 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)
            except ValueError:
                pass
        
        # Pattern: YYYY/MM/DD
        match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', text)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 2000 <= year <= datetime.now().year + 1 and 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)
            except ValueError:
                pass
        
        # Pattern: DD/MM/YYYY or MM/DD/YYYY
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if match:
            try:
                a, b, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 2000 <= year <= datetime.now().year + 1:
                    # Try DD/MM/YYYY first
                    if 1 <= a <= 31 and 1 <= b <= 12:
                        return datetime(year, b, a)
                    # Try MM/DD/YYYY
                    elif 1 <= a <= 12 and 1 <= b <= 31:
                        return datetime(year, a, b)
            except ValueError:
                pass
        
        # Pattern: Month DD, YYYY
        month_names = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
            'nov': 11, 'november': 11, 'dec': 12, 'december': 12
        }
        
        for month_name, month_num in month_names.items():
            pattern = rf'{month_name}\s+(\d{{1,2}}),?\s+(\d{{4}})'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    if 2000 <= year <= datetime.now().year + 1 and 1 <= day <= 31:
                        return datetime(year, month_num, day)
                except ValueError:
                    pass
        
        return None
    
    def is_from_recent_days(self, published_date: Optional[datetime], days_back: int = 3) -> bool:
        """
        Check if article is from recent days (not older than days_back)
        
        Args:
            published_date: Parsed datetime object
            days_back: Number of days to look back (default 3)
            
        Returns:
            True if article is recent or date unknown (conservative)
        """
        if not published_date:
            return True  # Keep if date unknown (conservative)
        
        # Ensure both are naive for comparison
        published_date = self._make_naive(published_date)
        now = datetime.now()
        
        days_ago = (now - published_date).days
        return days_ago <= days_back
    
    def extract_content(self, article: Dict) -> str:
        """
        Extract best available content from article
        
        Priority: content > summary > description > title
        
        Args:
            article: Article dictionary
            
        Returns:
            Extracted content string
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
        
        # Remove special characters (keep basic punctuation and Chinese)
        text = re.sub(r'[^\w\s\u4e00-\u9fff\-\.\,\!\?\(\)\[\]\:\;\"\']', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def parse_batch(self, articles: List[Dict], days_back: int = 3) -> List[Dict]:
        """
        Parse a batch of articles and filter by recency
        
        Args:
            articles: List of raw article dictionaries
            days_back: Number of days to look back (default 3)
            
        Returns:
            List of parsed articles with standardized fields
        """
        parsed = []
        
        for article in articles:
            parsed_article = self.parse_article(article, days_back)
            if parsed_article:
                parsed.append(parsed_article)
        
        return parsed
    
    def parse_article(self, article: Dict, days_back: int = 3) -> Optional[Dict]:
        """
        Parse a single article
        
        Args:
            article: Raw article dictionary
            days_back: Number of days to look back
            
        Returns:
            Parsed article with standardized fields or None if invalid
        """
        if not article.get('title'):
            return None
        
        # Parse date
        published_raw = article.get('published_raw', article.get('published_date', ''))
        published_date = self.parse_date(published_raw)
        
        # Check if from recent days
        if not self.is_from_recent_days(published_date, days_back):
            return None  # Skip older articles
        
        # Extract content
        content = self.extract_content(article)
        
        # Build standardized article
        parsed = {
            'title': self._clean_text(article.get('title', '')),
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
    
    def normalize_title(self, title: str) -> str:
        """
        Normalize title for comparison (used in deduplication)
        
        Args:
            title: Original title
            
        Returns:
            Normalized title
        """
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

