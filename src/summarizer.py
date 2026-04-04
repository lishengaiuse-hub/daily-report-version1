#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Article Summarizer for Samsung CE Intelligence
Uses DeepSeek API for generating concise summaries
"""

import os
import re
from typing import Optional
import openai

class ArticleSummarizer:
    """Generate concise summaries for articles"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            openai.api_key = self.api_key
            openai.api_base = "https://api.deepseek.com/v1"
            print("✅ Summarizer initialized with DeepSeek API")
        else:
            print("⚠️ No API key provided, summarizer disabled")
    
    def summarize(self, title: str, content: str, max_length: int = 150) -> str:
        """
        Generate a concise summary of the article
        
        Args:
            title: Article title
            content: Article content (may be truncated)
            max_length: Maximum summary length in characters
            
        Returns:
            Summarized text (3-5 lines)
        """
        if not self.enabled:
            return self._fallback_summary(title, content)
        
        # Truncate content to avoid token limits
        truncated = content[:2000] if content else title
        
        try:
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a business intelligence analyst for Samsung Consumer Electronics. 
                        Summarize the following news article in 2-3 sentences (50-80 words). 
                        Focus on: what happened, why it matters for Samsung, and key facts.
                        Be concise and factual. Do not add opinions not in the original text."""
                    },
                    {
                        "role": "user",
                        "content": f"Title: {title}\n\nContent: {truncated}"
                    }
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            summary = response.choices[0].message.content.strip()
            
            # Clean up summary
            summary = re.sub(r'\s+', ' ', summary)
            
            # Truncate if too long
            if len(summary) > max_length:
                summary = summary[:max_length - 3] + "..."
            
            return summary
            
        except Exception as e:
            print(f"⚠️ Summarization failed: {e}")
            return self._fallback_summary(title, content)
    
    def _fallback_summary(self, title: str, content: str) -> str:
        """Fallback summary generation without API"""
        # Extract first 2-3 sentences from content
        if content:
            # Split into sentences
            sentences = re.split(r'[.!?]+', content)
            summary = '. '.join(sentences[:3])
            if len(summary) > 150:
                summary = summary[:147] + "..."
            return summary.strip()
        
        return title
    
    def summarize_batch(self, articles: list, limit: int = 50) -> list:
        """
        Summarize a batch of articles
        
        Args:
            articles: List of article dictionaries
            limit: Maximum number to summarize
            
        Returns:
            Articles with added summary field
        """
        for i, article in enumerate(articles[:limit]):
            if not article.get('summary') or len(article['summary']) < 50:
                article['summary'] = self.summarize(
                    article['title'],
                    article.get('content', article.get('summary', ''))
                )
        
        return articles
