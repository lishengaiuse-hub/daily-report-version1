#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Samsung CE Intelligence System - Main Orchestrator
Coordinates all modules for daily intelligence briefing
"""

import os
import sys
import yaml
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from crawler import ArticleFetcher
from parser import ArticleParser
from deduplicator import Deduplicator
from classifier import TopicClassifier
from summarizer import ArticleSummarizer
from reporter import ReportGenerator
from mailer import EmailSender

class SamsungIntelligenceSystem:
    """Main orchestration class"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.base_dir = Path(__file__).parent.parent
        self.config = self._load_config(config_path)
        self.results = {
            'articles': [],
            'deduplicated': [],
            'stats': {},
            'report': None
        }
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        full_path = self.base_dir / config_path
        with open(full_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def run(self, dry_run: bool = False) -> Dict:
        """Run the complete intelligence pipeline"""
        print("=" * 70)
        print("Samsung CE Intelligence System")
        print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Step 1: Fetch articles from all sources
        print("\n📡 Step 1: Fetching articles...")
        fetcher = ArticleFetcher(self.config)
        articles = fetcher.fetch_all(self.config.get('sources', {}))
        print(f"   Fetched {len(articles)} raw articles")
        
        # Step 2: Parse and normalize
        print("\n📝 Step 2: Parsing articles...")
        parser = ArticleParser()
        parsed_articles = parser.parse_batch(articles)
        print(f"   Parsed {len(parsed_articles)} articles")
        
        # Step 3: Classify topics
        print("\n🏷️ Step 3: Classifying topics...")
        classifier = TopicClassifier(self.config.get('topics', {}))
        for article in parsed_articles:
            article['topics'] = classifier.classify(article['title'], article.get('summary', ''))
            article['reliability_score'] = self._get_reliability_score(article['source'])
        
        # Count by topic
        topic_counts = classifier.get_counts(parsed_articles)
        for topic_id, count in topic_counts.items():
            print(f"   Topic {topic_id}: {count} articles")
        
        # Step 4: Deduplication (CORE)
        print("\n🔍 Step 4: Deduplication...")
        deduplicator = Deduplicator(
            db_path=str(self.base_dir / "data/history.db"),
            config=self.config.get('deduplication', {})
        )
        deduped_articles, dedup_stats = deduplicator.deduplicate(parsed_articles)
        print(f"   Before: {dedup_stats['total_before']} → After: {dedup_stats['total_after']}")
        print(f"   Removed: {dedup_stats['duplicates_removed']} duplicates")
        
        # Step 5: Summarize (optional, can use LLM)
        print("\n✍️ Step 5: Generating summaries...")
        summarizer = ArticleSummarizer(api_key=os.getenv("DEEPSEEK_API_KEY"))
        for article in deduped_articles[:50]:  # Limit for performance
            if len(article.get('summary', '')) < 100:
                article['summary'] = summarizer.summarize(
                    article['title'], 
                    article.get('content', article.get('summary', ''))
                )
        
        # Step 6: Generate report
        print("\n📊 Step 6: Generating report...")
        reporter = ReportGenerator(self.config)
        report_md = reporter.generate_markdown(deduped_articles, dedup_stats)
        report_html = reporter.generate_html(report_md)
        
        # Save reports
        output_dir = self.base_dir / "output"
        output_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime('%Y%m%d')
        
        with open(output_dir / f"report_{date_str}.md", 'w', encoding='utf-8') as f:
            f.write(report_md)
        with open(output_dir / f"report_{date_str}.html", 'w', encoding='utf-8') as f:
            f.write(report_html)
        print(f"   Reports saved to {output_dir}")
        
        # Step 7: Send email
        if not dry_run:
            print("\n📧 Step 7: Sending email...")
            mailer = EmailSender(self.config.get('email', {}))
            success = mailer.send(report_html, date_str)
            print(f"   Email sent: {'✅' if success else '❌'}")
        
        # Step 8: Cleanup
        deduplicator.close()
        
        print("\n" + "=" * 70)
        print(f"✅ System completed in {self._get_elapsed_time()}")
        print("=" * 70)
        
        return {
            'articles': deduped_articles,
            'stats': dedup_stats,
            'report': report_md
        }
    
    def _get_reliability_score(self, source: str) -> float:
        """Get reliability score based on source domain"""
        high = self.config.get('reliability', {}).get('high', [])
        medium = self.config.get('reliability', {}).get('medium', [])
        low = self.config.get('reliability', {}).get('low', [])
        
        source_lower = source.lower()
        for pattern in high:
            if pattern in source_lower:
                return 0.95
        for pattern in medium:
            if pattern in source_lower:
                return 0.80
        for pattern in low:
            if pattern in source_lower:
                return 0.60
        return 0.70
    
    def _get_elapsed_time(self) -> str:
        """Get elapsed time string"""
        if not hasattr(self, '_start_time'):
            self._start_time = datetime.now()
        elapsed = (datetime.now() - self._start_time).total_seconds()
        return f"{elapsed:.1f} seconds"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samsung CE Intelligence System")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    args = parser.parse_args()
    
    system = SamsungIntelligenceSystem(config_path=args.config)
    system.run(dry_run=args.dry_run)
