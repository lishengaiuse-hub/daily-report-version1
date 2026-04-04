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
        self.start_time = datetime.now()
        self.results = {
            'articles': [],
            'deduplicated': [],
            'stats': {},
            'report': None
        }
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        full_path = self.base_dir / config_path
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            print(f"⚠️ Config file not found: {full_path}, using default config")
            return self._default_config()
    
    def _default_config(self) -> Dict:
        """Default configuration if config file not found"""
        return {
            'sources': {
                'rss': {
                    'display': ['https://www.oled-info.com/rss.xml'],
                    'global_tech': ['https://techcrunch.com/feed/'],
                },
                'web_scraping': {},
                'api': {}
            },
            'topics': {
                '1': {'name': 'Competitor Technology'},
                '2': {'name': 'New Technologies'},
                '3': {'name': 'Manufacturing Expansion'},
                '4': {'name': 'Exhibitions'},
                '5': {'name': 'Supply Chain Risk'}
            },
            'email': {
                'smtp_host': 'smtp.gmail.com',
                'smtp_port': 465,
                'use_ssl': True
            }
        }
    
    def run(self, dry_run: bool = False) -> Dict:
        """Run the complete intelligence pipeline"""
        print("=" * 70)
        print("🔵 Samsung CE Intelligence System")
        print(f"📅 Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📍 Timezone: Singapore (UTC+8)")
        print("=" * 70)
        
        try:
            # Step 1: Fetch articles from all sources
            print("\n📡 Step 1: Fetching articles...")
            fetcher = ArticleFetcher(self.config)
            articles = fetcher.fetch_all(self.config.get('sources', {}))
            print(f"   ✅ Fetched {len(articles)} raw articles")
            
            if not articles:
                print("   ⚠️ No articles fetched. Check your sources.")
                return {'articles': [], 'stats': {}, 'report': None}
            
            # Step 2: Parse and normalize
            print("\n📝 Step 2: Parsing articles...")
            parser = ArticleParser()
            parsed_articles = parser.parse_batch(articles)
            print(f"   ✅ Parsed {len(parsed_articles)} articles (filtered for T-1)")
            
            if not parsed_articles:
                print("   ⚠️ No articles after parsing. Check date filtering.")
                return {'articles': [], 'stats': {}, 'report': None}
            
            # Step 3: Classify topics
            print("\n🏷️ Step 3: Classifying topics...")
            classifier = TopicClassifier(self.config.get('topics', {}))
            for article in parsed_articles:
                article['topics'] = classifier.classify(
                    article.get('title', ''), 
                    article.get('summary', '')
                )
                article['reliability_score'] = self._get_reliability_score(article.get('source', ''))
            
            # Count by topic
            topic_counts = classifier.get_counts(parsed_articles)
            print("   📊 Topic distribution:")
            for topic_id in range(1, 6):
                count = topic_counts.get(topic_id, 0)
                topic_name = self.config.get('topics', {}).get(str(topic_id), {}).get('name', f'Topic {topic_id}')
                print(f"      Topic {topic_id} ({topic_name}): {count} articles")
            
            # Step 4: Deduplication (CORE)
            print("\n🔍 Step 4: Deduplication (3-layer)...")
            deduplicator = Deduplicator(
                db_path=str(self.base_dir / "data/history.db"),
                config=self.config.get('deduplication', {})
            )
            deduped_articles, dedup_stats = deduplicator.deduplicate(parsed_articles)
            print(f"   ✅ Before: {dedup_stats['total_before']} → After: {dedup_stats['total_after']}")
            print(f"   🗑️ Removed: {dedup_stats['duplicates_removed']} duplicates")
            
            # Print dedup breakdown
            if dedup_stats.get('by_layer'):
                print("   📊 Dedup breakdown:")
                for layer, count in dedup_stats['by_layer'].items():
                    print(f"      {layer}: {count}")
            
            # Step 5: Summarize (optional, can use LLM)
            print("\n✍️ Step 5: Generating summaries...")
            summarizer = ArticleSummarizer(api_key=os.getenv("DEEPSEEK_API_KEY"))
            for article in deduped_articles[:50]:  # Limit for performance
                if len(article.get('summary', '')) < 100:
                    article['summary'] = summarizer.summarize(
                        article.get('title', ''), 
                        article.get('content', article.get('summary', ''))
                    )
            print(f"   ✅ Summarized {min(50, len(deduped_articles))} articles")
            
            # Step 6: Generate report
            print("\n📊 Step 6: Generating report...")
            reporter = ReportGenerator(self.config)
            report_md = reporter.generate_markdown(deduped_articles, dedup_stats)
            report_html = reporter.generate_html(report_md)
            
            # Save reports
            output_dir = self.base_dir / "output"
            output_dir.mkdir(exist_ok=True)
            date_str = datetime.now().strftime('%Y%m%d')
            
            md_path = output_dir / f"report_{date_str}.md"
            html_path = output_dir / f"report_{date_str}.html"
            
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(report_md)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
            
            print(f"   ✅ Report saved: {md_path}")
            print(f"   ✅ HTML saved: {html_path}")
            
            # Step 7: Send email (skip if dry run)
            if not dry_run:
                print("\n📧 Step 7: Sending email...")
                email_config = self.config.get('email', {})
                mailer = EmailSender(email_config)
                success = mailer.send(report_html, datetime.now().strftime('%Y-%m-%d'))
                if success:
                    print("   ✅ Email sent successfully!")
                else:
                    print("   ❌ Failed to send email. Check logs above.")
            else:
                print("\n📧 Step 7: Skipping email (dry run mode)")
            
            # Step 8: Cleanup
            deduplicator.close()
            
            # Print summary
            elapsed = (datetime.now() - self.start_time).total_seconds()
            print("\n" + "=" * 70)
            print(f"✅ System completed successfully in {elapsed:.1f} seconds")
            print("=" * 70)
            
            # Print deduplication report
            print("\n" + deduplicator.get_deduplication_report())
            
            return {
                'articles': deduped_articles,
                'stats': dedup_stats,
                'report': report_md
            }
            
        except Exception as e:
            print(f"\n❌ System failed with error: {e}")
            import traceback
            traceback.print_exc()
            return {'articles': [], 'stats': {}, 'report': None, 'error': str(e)}
    
    def _get_reliability_score(self, source: str) -> float:
        """Get reliability score based on source domain"""
        high_domains = [
            "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
            "semiengineering.com", "digitimes.com", "trendforce.com",
            "counterpointresearch.com", "ieee.org"
        ]
        medium_domains = [
            "techcrunch.com", "theverge.com", "engadget.com",
            "oled-info.com", "ledinside.cn", "technews.tw",
            "cnpowder.com.cn", "eetimes.com"
        ]
        low_domains = [
            "abnotebook.com", "leikeji.com", "abvr360.com",
            "aibangbots.com", "polytpe.com", "weibo.com"
        ]
        
        source_lower = source.lower()
        
        for domain in high_domains:
            if domain in source_lower:
                return 0.95
        for domain in medium_domains:
            if domain in source_lower:
                return 0.80
        for domain in low_domains:
            if domain in source_lower:
                return 0.60
        
        return 0.70  # Default medium reliability
    
    def test_email_only(self) -> bool:
        """Test email configuration only"""
        print("=" * 70)
        print("📧 Testing Email Configuration Only")
        print("=" * 70)
        
        email_config = self.config.get('email', {})
        mailer = EmailSender(email_config)
        
        test_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Test Email</title>
        </head>
        <body>
            <h1>Samsung CE Intelligence - Test Email</h1>
            <p>This is a test email to verify SMTP configuration.</p>
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>System:</strong> Samsung CE Intelligence System</p>
            <hr>
            <p>If you received this, email configuration is working correctly!</p>
        </body>
        </html>
        """
        
        return mailer.send(test_html, "TEST")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samsung CE Intelligence System")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--test-email", action="store_true", help="Test email configuration only")
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    args = parser.parse_args()
    
    system = SamsungIntelligenceSystem(config_path=args.config)
    
    if args.test_email:
        success = system.test_email_only()
        sys.exit(0 if success else 1)
    else:
        result = system.run(dry_run=args.dry_run)
        if result.get('error'):
            sys.exit(1)
        sys.exit(0)
