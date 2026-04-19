#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Samsung CE Intelligence System - Main Orchestrator
Version: 4.1 - 集成Google News主动搜索 + RSS Fallback
"""

import os
import sys
import yaml
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from crawler import ArticleFetcher
from parser import ArticleParser
from deduplicator import Deduplicator
from atomic_splitter import AtomicSplitter
from origin_tracker import OriginTracker
from classifier import TopicClassifier
from summarizer import ArticleSummarizer
from reporter import ReportGenerator
from mailer import EmailSender
from google_news_fetcher import GoogleNewsFetcher, TOPIC_SEARCH_KEYWORDS


class SamsungIntelligenceSystem:
    """Main orchestration class with Google News fallback"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.base_dir = Path(__file__).parent.parent
        self.config = self._load_config(config_path)
        self.start_time = datetime.now()
        
        self.fetcher = ArticleFetcher(self.config)
        self.parser = ArticleParser()
        self.deduplicator = Deduplicator(
            db_path=str(self.base_dir / "data/history.db"),
            config=self.config.get('deduplication', {})
        )
        self.splitter = AtomicSplitter()
        self.tracker = OriginTracker()
        self.classifier = TopicClassifier(self.config.get('topics', {}))
        self.summarizer = ArticleSummarizer(api_key=os.getenv("DEEPSEEK_API_KEY"))
        self.reporter = ReportGenerator(self.config)
        self.mailer = EmailSender(self.config.get('email', {}))
        self.google_fetcher = GoogleNewsFetcher(self.fetcher.session)
    
    def _load_config(self, config_path: str) -> Dict:
        full_path = self.base_dir / config_path
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            print(f"⚠️ Config file not found: {full_path}, using default config")
            return self._default_config()
    
    def _default_config(self) -> Dict:
        return {
            'sources': {'rss': {}, 'web_scraping': {}, 'firecrawl': {}, 'api': {}},
            'topics': {},
            'email': {'smtp_host': 'smtp.gmail.com', 'smtp_port': 465, 'use_ssl': True}
        }
    
    def _make_naive(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    
    def _get_reliability_score(self, source: str) -> float:
        high_domains = [
            "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "nikkei.com",
            "semiengineering.com", "digitimes.com", "ieee.org", "eetimes.com",
            "samsung.com", "apple.com", "xiaomi.com"
        ]
        medium_domains = [
            "techcrunch.com", "theverge.com", "engadget.com", "gsmarena.com",
            "oled-info.com", "ithome.com", "36kr.com", "vietnam-briefing.com"
        ]
        low_domains = [
            "abnotebook.com", "leikeji.com", "abvr360.com", "aibangbots.com"
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
        
        return 0.70
    
    def run(self, dry_run: bool = False) -> Dict:
        print("=" * 70)
        print("🔵 Samsung CE Intelligence System v4.1")
        print(f"📅 Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        try:
            # Step 1: 抓取
            print("\n📡 Step 1: Fetching articles...")
            articles = self.fetcher.fetch_all(self.config.get('sources', {}))
            print(f"   ✅ Fetched {len(articles)} raw articles")
            
            if not articles:
                print("   ⚠️ No articles fetched. Check your sources.")
                return {'articles': [], 'stats': {}, 'report': None}
            
            # Step 2: 解析
            print("\n📝 Step 2: Parsing articles...")
            parsed_articles = self.parser.parse_batch(articles, days_back=3)
            print(f"   ✅ Parsed {len(parsed_articles)} articles")
            
            if not parsed_articles:
                print("   ⚠️ No articles after parsing.")
                return {'articles': [], 'stats': {}, 'report': None}
            
            # Step 3: 原子化拆分
            print("\n🔪 Step 3: Atomic splitting...")
            atomic_articles = self.splitter.split_batch(parsed_articles)
            print(f"   ✅ After split: {len(atomic_articles)} atomic articles")
            
            # Step 4: 原始来源追溯
            print("\n🔗 Step 4: Origin tracking...")
            traced_articles = self.tracker.trace_batch(atomic_articles)
            
            # Step 5: 严格分类
            print("\n🏷️ Step 5: Strict classification...")
            for article in traced_articles:
                article['topics'] = self.classifier.classify(
                    article.get('title', ''),
                    article.get('summary', '')
                )
                article['reliability_score'] = self._get_reliability_score(article.get('source', ''))
            
            # 按Topic分组
            articles_by_topic = {tid: [] for tid in range(1, 6)}
            for article in traced_articles:
                for topic_id in article.get('topics', []):
                    if 1 <= topic_id <= 5:
                        articles_by_topic[topic_id].append(article)
            
            print("   📊 Initial topic distribution:")
            for tid in range(1, 6):
                print(f"      Topic {tid}: {len(articles_by_topic[tid])} articles")
            
            self.classifier.print_stats()
            
            # Step 6: Topic Coverage Guarantee with Google News
            print("\n🎯 Step 6: Topic Coverage Guarantee (Min 3 articles per topic)...")
            
            MIN_ARTICLES_PER_TOPIC = 3
            topic_names = {
                1: "Competitor Technology & Products",
                2: "New Technologies / Components / Materials",
                3: "Manufacturing Expansion (SEA / India)",
                4: "Exhibitions",
                5: "Supply Chain Risk"
            }
            
            for topic_id in range(1, 6):
                current_count = len(articles_by_topic[topic_id])
                
                if current_count < MIN_ARTICLES_PER_TOPIC:
                    needed = MIN_ARTICLES_PER_TOPIC - current_count
                    print(f"   ⚠️ Topic {topic_id} ({topic_names[topic_id]}) needs {needed} more articles")
                    print(f"      🔍 Searching Google News for Topic {topic_id}...")
                    
                    keywords = TOPIC_SEARCH_KEYWORDS.get(topic_id, [])
                    new_articles = self.google_fetcher.search_by_topic(topic_id, keywords, days_back=3)
                    
                    for article in new_articles[:needed + 2]:
                        # 分类
                        topics = self.classifier.classify(article['title'], article.get('summary', ''))
                        if topic_id not in topics:
                            topics.append(topic_id)
                        
                        article['topics'] = topics
                        article['reliability_score'] = self._get_reliability_score(article.get('source', ''))
                        article['published_date'] = self.parser.parse_date(article.get('published_raw', ''))
                        
                        traced_articles.append(article)
                        articles_by_topic[topic_id].append(article)
                    
                    final_count = len(articles_by_topic[topic_id])
                    print(f"      ✅ Topic {topic_id} now has {final_count} articles")
                else:
                    print(f"   ✅ Topic {topic_id} ({topic_names[topic_id]}): {current_count} articles")
            
            # Step 7: 跨栏目去重
            print("\n🔄 Step 7: Cross-topic deduplication...")
            articles_by_topic = self.classifier.cross_topic_deduplicate(articles_by_topic)
            
            deduped_articles = []
            for articles in articles_by_topic.values():
                deduped_articles.extend(articles)
            
            print(f"   ✅ After cross-topic dedup: {len(deduped_articles)} unique articles")
            
            # Step 8: 标准去重
            print("\n🔍 Step 8: Standard deduplication...")
            final_articles, dedup_stats = self.deduplicator.deduplicate(deduped_articles)
            print(f"   ✅ Before: {dedup_stats['total_before']} → After: {dedup_stats['total_after']}")
            
            # Step 9: AI摘要
            print("\n✍️ Step 9: Generating AI summaries...")
            for article in final_articles[:50]:
                if len(article.get('summary', '')) < 100:
                    article['summary'] = self.summarizer.summarize(
                        article.get('title', ''),
                        article.get('content', article.get('summary', ''))
                    )
            print(f"   ✅ Summarized {min(50, len(final_articles))} articles")
            
            # Step 10: 生成报告
            print("\n📊 Step 10: Generating report...")
            
            final_counts = defaultdict(int)
            for article in final_articles:
                for t in article.get('topics', []):
                    final_counts[t] += 1
            
            print("   📊 Final topic distribution:")
            for tid in range(1, 6):
                print(f"      Topic {tid}: {final_counts[tid]} articles")
            
            report_html = self.reporter.generate_html(final_articles, dedup_stats)
            
            output_dir = self.base_dir / "output"
            output_dir.mkdir(exist_ok=True)
            date_str = datetime.now().strftime('%Y%m%d')
            html_path = output_dir / f"report_{date_str}.html"
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
            
            print(f"   ✅ Report saved: {html_path}")
            
            # Step 11: 发送邮件
            if not dry_run:
                print("\n📧 Step 11: Sending email...")
                success = self.mailer.send(report_html, date_str)
                if success:
                    print("   ✅ Email sent successfully!")
                else:
                    print("   ❌ Failed to send email")
            else:
                print("\n📧 Step 11: Skipping email (dry run mode)")
            
            self.deduplicator.close()
            
            elapsed = (datetime.now() - self.start_time).total_seconds()
            print("\n" + "=" * 70)
            print(f"✅ System completed successfully in {elapsed:.1f} seconds")
            print("=" * 70)
            print("\n" + self.deduplicator.get_deduplication_report())
            print(f"\n📊 Google News Stats: {self.google_fetcher.get_stats()}")
            
            return {'articles': final_articles, 'stats': dedup_stats}
            
        except Exception as e:
            print(f"\n❌ System failed with error: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samsung CE Intelligence System v4.1")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--test-email", action="store_true", help="Test email configuration only")
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    args = parser.parse_args()
    
    system = SamsungIntelligenceSystem(config_path=args.config)
    
    if args.test_email:
        success = system.mailer.send_test_email()
        sys.exit(0 if success else 1)
    else:
        result = system.run(dry_run=args.dry_run)
        if result.get('error'):
            sys.exit(1)
        sys.exit(0)
