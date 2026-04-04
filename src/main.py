#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Samsung CE Intelligence System - Main Orchestrator
Coordinates all modules for daily intelligence briefing
Version: 3.1 - Fixed datetime timezone compatibility
"""

import os
import sys
import yaml
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

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
    """Main orchestration class with topic coverage guarantee"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.base_dir = Path(__file__).parent.parent
        self.config = self._load_config(config_path)
        self.start_time = datetime.now()
        
        # Initialize topic-source mapping (for coverage guarantee)
        self.topic_sources = self._init_topic_sources()
        self.topic_keywords = self._init_topic_keywords()
        
        self.results = {
            'articles': [],
            'deduplicated': [],
            'stats': {},
            'report': None
        }
    
    def _init_topic_sources(self) -> Dict[int, List[str]]:
        """Initialize topic-specific source mapping for active search"""
        return {
            1: [  # Competitor Technology & Products
                "news.samsung.com", "samsung.com",
                "xiaomi.com", "mi.com",
                "apple.com", "apple.com/newsroom",
                "sony.com", "sony.net",
                "tcl.com", "tcl",
                "lg.com", "lgnewsroom.com",
                "haier.com",
                "gsmarena.com", "androidauthority.com",
                "techcrunch.com", "theverge.com", "engadget.com"
            ],
            2: [  # New Technologies / Components
                "eetimes.com", "electronicsweekly.com", "digitimes.com",
                "ieee.org", "spectrum.ieee.org", "semiengineering.com",
                "microled-info.com", "oled-info.com", "displaydaily.com",
                "eet-china.com", "esmchina.com", "eepw.com.cn",
                "semiwiki.com", "semiconductor-digest.com"
            ],
            3: [  # Manufacturing Expansion
                "reuters.com", "nikkei.com", "asia.nikkei.com",
                "bloomberg.com", "vietnamnews.vn", "vietnam-briefing.com",
                "meity.gov.in", "india.gov.in", "businesstimes.com.sg",
                "thestar.com.my", "bangkokpost.com", "vnexpress.net",
                "thelec.net", "msia.org.my"
            ],
            4: [  # Exhibitions
                "ces.tech", "ifa-berlin.com", "mwcbarcelona.com",
                "displayweek.org", "prnewswire.com", "globenewswire.com",
                "businesswire.com"
            ],
            5: [  # Supply Chain Risk
                "reuters.com", "bloomberg.com", "ft.com", "financialtimes.com",
                "supplychaindive.com", "freightwaves.com", "scmr.com",
                "supplychainbrain.com", "ebnonline.com", "globalsmt.net"
            ]
        }
    
    def _init_topic_keywords(self) -> Dict[int, List[str]]:
        """Initialize topic-specific keywords for active search"""
        return {
            1: [  # Competitor Technology & Products
                "new product launch", "TV release", "smartphone launch", "foldable phone",
                "OLED TV", "Mini LED", "QLED", "robot vacuum", "smartwatch",
                "TCL new product", "Xiaomi release", "Apple launch", "Sony TV",
                "LG display", "Haier appliance", "competitor announcement",
                "新品发布", "电视新品", "手机发布", "折叠屏", "扫地机器人", "智能手表"
            ],
            2: [  # New Technologies / Components
                "semiconductor breakthrough", "new material", "display technology",
                "battery innovation", "sensor technology", "chip design",
                "MicroLED advancement", "OLED innovation", "quantum dot",
                "GaN technology", "silicon carbide", "3D printing electronics",
                "thermal management", "electronics cooling",
                "半导体突破", "新材料", "显示技术", "电池创新", "芯片技术"
            ],
            3: [  # Manufacturing Expansion
                "factory expansion Vietnam", "plant investment India", "manufacturing capacity",
                "electronics assembly Thailand", "production relocation", "supply chain shift",
                "Southeast Asia manufacturing", "India electronics production",
                "越南工厂扩建", "印度制造投资", "产能扩张", "生产转移", "东南亚制造"
            ],
            4: [  # Exhibitions
                "CES 2026", "IFA Berlin", "MWC Barcelona", "Computex Taipei",
                "Display Week", "AWE exhibition", "electronics trade show",
                "consumer electronics exhibition", "technology conference",
                "消费电子展", "科技展会", "行业论坛", "博览会"
            ],
            5: [  # Supply Chain Risk
                "component shortage", "supply disruption", "logistics delay",
                "tariff impact", "trade policy", "geopolitical risk",
                "price increase electronics", "semiconductor supply",
                "battery supply chain", "display panel shortage",
                "元器件短缺", "供应链中断", "物流延误", "关税影响", "价格上涨"
            ]
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
                'rss': {},
                'web_scraping': {},
                'firecrawl': {},
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
    
    def _make_naive(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Convert datetime to naive (remove timezone info)"""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    
    def run(self, dry_run: bool = False) -> Dict:
        """Run the complete intelligence pipeline with topic coverage guarantee"""
        print("=" * 70)
        print("🔵 Samsung CE Intelligence System v3.1")
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
            print(f"   ✅ Parsed {len(parsed_articles)} articles (filtered for recent days)")
            
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
            print("   📊 Initial topic distribution:")
            for topic_id in range(1, 6):
                count = topic_counts.get(topic_id, 0)
                topic_name = self._get_topic_name(topic_id)
                print(f"      Topic {topic_id} ({topic_name}): {count} articles")
            
            # Step 3.5: Topic Coverage Guarantee - Ensure each topic has minimum content
            print("\n🎯 Step 3.5: Topic Coverage Guarantee (Min 3 articles per topic)...")
            
            # Group articles by topic
            articles_by_topic = defaultdict(list)
            for article in parsed_articles:
                for topic_id in article.get('topics', []):
                    if 1 <= topic_id <= 5:
                        articles_by_topic[topic_id].append(article)
            
            min_articles_per_topic = 3
            coverage_report_lines = []
            
            for topic_id in range(1, 6):
                current_count = len(articles_by_topic[topic_id])
                topic_name = self._get_topic_name(topic_id)
                
                if current_count < min_articles_per_topic:
                    needed = min_articles_per_topic - current_count
                    print(f"   ⚠️ Topic {topic_id} ({topic_name}) needs {needed} more articles")
                    print(f"      🔍 Actively searching for Topic {topic_id}...")
                    
                    # Actively fetch for this topic
                    new_articles = fetcher.fetch_by_topic(
                        topic_id=topic_id,
                        topic_sources=self.topic_sources,
                        topic_keywords=self.topic_keywords,
                        days_back=3
                    )
                    
                    # Parse and classify new articles
                    for new_article in new_articles:
                        # Parse date
                        published_raw = new_article.get('published_raw', '')
                        published_date = parser.parse_date(published_raw) if published_raw else None
                        
                        # Fix: Handle timezone compatibility
                        if published_date:
                            # Convert to naive datetime for comparison
                            published_date = self._make_naive(published_date)
                            now = datetime.now()
                            # Check if older than 3 days
                            if (now - published_date).days > 3:
                                continue
                        
                        # Classify (ensure it gets the target topic)
                        topics = classifier.classify(
                            new_article['title'], 
                            new_article.get('summary', '')
                        )
                        if topic_id not in topics:
                            topics.append(topic_id)  # Force add the target topic
                        
                        new_article['topics'] = topics
                        new_article['published_date'] = published_date
                        new_article['published_raw'] = published_raw
                        new_article['reliability_score'] = self._get_reliability_score(
                            new_article.get('source', 'active_search')
                        )
                        
                        parsed_articles.append(new_article)
                        articles_by_topic[topic_id].append(new_article)
                        
                        if len(articles_by_topic[topic_id]) >= min_articles_per_topic:
                            break
                    
                    final_count = len(articles_by_topic[topic_id])
                    print(f"      ✅ Topic {topic_id} now has {final_count} articles")
                    coverage_report_lines.append(f"   - Topic {topic_id} ({topic_name}): {final_count} articles (added {final_count - current_count})")
                else:
                    coverage_report_lines.append(f"   - Topic {topic_id} ({topic_name}): {current_count} articles ✅")
            
            # Print coverage summary
            print("\n   📊 Final topic coverage:")
            for line in coverage_report_lines:
                print(line)
            
            # Step 4: Deduplication (CORE)
            print("\n🔍 Step 4: Deduplication (3-layer)...")
            deduplicator = Deduplicator(
                db_path=str(self.base_dir / "data/history.db"),
                config=self.config.get('deduplication', {})
            )
            deduped_articles, dedup_stats = deduplicator.deduplicate(parsed_articles)
            print(f"   ✅ Before: {dedup_stats['total_before']} → After: {dedup_stats['total_after']}")
            print(f"   🗑️ Removed: {dedup_stats['duplicates_removed']} duplicates")
            
            if dedup_stats.get('by_layer'):
                print("   📊 Dedup breakdown:")
                for layer, count in dedup_stats['by_layer'].items():
                    print(f"      {layer}: {count}")
            
            # Step 5: Summarize
            print("\n✍️ Step 5: Generating AI summaries...")
            summarizer = ArticleSummarizer(api_key=os.getenv("DEEPSEEK_API_KEY"))
            for article in deduped_articles[:50]:
                if len(article.get('summary', '')) < 100:
                    article['summary'] = summarizer.summarize(
                        article.get('title', ''), 
                        article.get('content', article.get('summary', ''))
                    )
            print(f"   ✅ Summarized {min(50, len(deduped_articles))} articles")
            
            # Step 6: Generate report
            print("\n📊 Step 6: Generating report...")
            reporter = ReportGenerator(self.config)
            
            # Generate markdown report (backup)
            report_md = reporter.generate_markdown(deduped_articles, dedup_stats)
            
            # Generate HTML report
            report_html = reporter.generate_html(deduped_articles, dedup_stats)
            
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
            
            # Step 7: Send email
            if not dry_run:
                print("\n📧 Step 7: Sending email...")
                
                print("   🔍 Email debug info:")
                print(f"      SENDER_EMAIL: {os.getenv('SENDER_EMAIL', 'NOT SET')}")
                print(f"      RECEIVER_EMAIL: {os.getenv('RECEIVER_EMAIL', 'NOT SET')}")
                print(f"      SMTP_HOST: {os.getenv('SMTP_HOST', 'NOT SET')}")
                print(f"      SMTP_PORT: {os.getenv('SMTP_PORT', 'NOT SET')}")
                print(f"      SENDER_PASSWORD: {'✅ SET' if os.getenv('SENDER_PASSWORD') else '❌ NOT SET'}")
                
                email_config = self.config.get('email', {})
                mailer = EmailSender(email_config)
                
                if not report_html:
                    print("   ❌ Report HTML is empty, cannot send email")
                else:
                    print(f"   📄 Report HTML size: {len(report_html)} characters")
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
    
    def _get_topic_name(self, topic_id: int) -> str:
        """Get topic name by ID"""
        topic_names = {
            1: "Competitor Technology & Products",
            2: "New Technologies / Components / Materials",
            3: "Manufacturing Expansion (SEA / India)",
            4: "Exhibitions",
            5: "Supply Chain Risk"
        }
        return topic_names.get(topic_id, f"Topic {topic_id}")
    
    def _get_reliability_score(self, source: str) -> float:
        """Get reliability score based on source domain"""
        high_domains = [
            "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "nikkei.com",
            "semiengineering.com", "digitimes.com", "trendforce.com",
            "counterpointresearch.com", "ieee.org", "eetimes.com",
            "samsung.com", "apple.com", "xiaomi.com"
        ]
        medium_domains = [
            "techcrunch.com", "theverge.com", "engadget.com",
            "oled-info.com", "microled-info.com", "ledinside.cn", 
            "technews.tw", "cnpowder.com.cn", "ithome.com",
            "36kr.com", "leiphone.com", "pingwest.com", "thelec.net",
            "vietnam-briefing.com", "gsmarena.com", "androidauthority.com"
        ]
        low_domains = [
            "abnotebook.com", "leikeji.com", "abvr360.com",
            "aibangbots.com", "polytpe.com", "weibo.com", "zhihu.com"
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
    
    def test_email_only(self) -> bool:
        """Test email configuration only"""
        print("=" * 70)
        print("📧 Testing Email Configuration Only")
        print("=" * 70)
        
        print("\n🔍 Email configuration check:")
        print(f"   SENDER_EMAIL: {os.getenv('SENDER_EMAIL', 'NOT SET')}")
        print(f"   RECEIVER_EMAIL: {os.getenv('RECEIVER_EMAIL', 'NOT SET')}")
        print(f"   SMTP_HOST: {os.getenv('SMTP_HOST', 'NOT SET')}")
        print(f"   SMTP_PORT: {os.getenv('SMTP_PORT', 'NOT SET')}")
        print(f"   SENDER_PASSWORD: {'✅ SET' if os.getenv('SENDER_PASSWORD') else '❌ NOT SET'}")
        
        email_config = self.config.get('email', {})
        mailer = EmailSender(email_config)
        
        test_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Test Email</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 16px;
                    padding: 30px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #1428a0 0%, #0f1a5e 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 12px;
                    text-align: center;
                    margin-bottom: 20px;
                }}
                .content {{
                    line-height: 1.6;
                    color: #333;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                }}
                .success {{
                    color: #10b981;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔵 Samsung CE Intelligence</h1>
                    <p>Email Configuration Test</p>
                </div>
                <div class="content">
                    <p><span class="success">✅ Test email sent successfully!</span></p>
                    <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Sender:</strong> {os.getenv('SENDER_EMAIL', 'NOT SET')}</p>
                    <p><strong>Recipient:</strong> {os.getenv('RECEIVER_EMAIL', 'NOT SET')}</p>
                    <p>If you received this email, your SMTP configuration is working correctly.</p>
                    <hr>
                    <p><strong>Next Steps:</strong></p>
                    <ol>
                        <li>Run <code>python src/main.py --dry-run</code> to test full system</li>
                        <li>Run <code>python src/main.py</code> to send real reports</li>
                        <li>Check GitHub Actions for automated runs</li>
                    </ol>
                </div>
                <div class="footer">
                    <p>Samsung CE Intelligence System v3.1</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return mailer.send(test_html, "TEST")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samsung CE Intelligence System v3.1")
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
