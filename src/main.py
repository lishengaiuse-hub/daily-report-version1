#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Samsung CE Intelligence System - Main Orchestrator
Version: 6.0 - 单一归属 + 强制原子化删除 + 语义去重 + T4结构校验 + 最终QA关卡
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
    """主调度类 - 执行完整的情报处理流水线 v6.0"""

    TOPIC_NAMES = {
        1: "T1 竞品动态",
        2: "T2 新技术/材料",
        3: "T3 制造（SEA/India）",
        4: "T4 行业展会"
    }

    def __init__(self, config_path: str = "config/config.yaml"):
        self.base_dir = Path(__file__).parent.parent
        self.config = self._load_config(config_path)
        self.start_time = datetime.now()

        self.fetcher      = ArticleFetcher(self.config)
        self.parser       = ArticleParser()
        self.deduplicator = Deduplicator(
            db_path=str(self.base_dir / "data/history.db"),
            config=self.config.get("deduplication", {})
        )
        self.splitter   = AtomicSplitter()
        self.tracker    = OriginTracker()
        self.classifier = TopicClassifier(self.config.get("topics", {}))
        self.summarizer = ArticleSummarizer(api_key=os.getenv("DEEPSEEK_API_KEY"))
        self.reporter   = ReportGenerator(self.config)
        self.mailer     = EmailSender(self.config.get("email", {}))
        self.google_fetcher = GoogleNewsFetcher(self.fetcher.session)

    def _load_config(self, config_path: str) -> Dict:
        full_path = self.base_dir / config_path
        if full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        print(f"⚠️ Config not found: {full_path}, using defaults")
        return {"sources": {}, "topics": {}, "email": {}}

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
        src = source.lower()
        if any(d in src for d in high_domains):
            return 0.95
        if any(d in src for d in medium_domains):
            return 0.80
        return 0.70

    def run(self, dry_run: bool = False) -> Dict:
        print("=" * 70)
        print("🔵 Samsung CE Intelligence System v6.0")
        print(f"📅 Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        # 删除原因追踪
        deletion_log: Dict[str, int] = {
            "irrelevant": 0,
            "duplicate": 0,
            "semantic_duplicate": 0,
            "unsplit": 0,
            "t4_incomplete": 0,
            "final_gate": 0
        }

        try:
            # ── Step 1: 抓取 ────────────────────────────────────────────
            print("\n📡 Step 1: Fetching articles...")
            articles = self.fetcher.fetch_all(self.config.get("sources", {}))
            print(f"   ✅ Fetched {len(articles)} raw articles")
            if not articles:
                print("   ⚠️ No articles fetched.")
                return {"articles": [], "stats": {}}

            raw_count = len(articles)

            # ── Step 2: 解析 ─────────────────────────────────────────────
            print("\n📝 Step 2: Parsing articles...")
            parsed = self.parser.parse_batch(articles, days_back=3)
            print(f"   ✅ Parsed {len(parsed)} articles (3-day recency filter)")

            # ── Step 3: 强制原子化（聚合无法拆分 → 直接删除）─────────────
            print("\n✂️ Step 3: Atomic splitting (unsplittable aggregates DELETED)...")
            atomic, unsplit_deleted = self.splitter.split_batch(parsed)
            deletion_log["unsplit"] += unsplit_deleted
            print(f"   ✅ After split: {len(atomic)} atomic articles ({unsplit_deleted} aggregates deleted)")

            # ── Step 4: 原始来源追溯 ─────────────────────────────────────
            print("\n🔗 Step 4: Origin tracking...")
            traced = self.tracker.trace_batch(atomic)

            # ── Step 5: 严格分类 + 强相关过滤（不相关 → 删除）─────────────
            print("\n🏷️ Step 5: Strict classification (T1-T4) + relevance filter...")
            classified = []
            for article in traced:
                topics = self.classifier.classify(
                    article.get("title", ""),
                    article.get("summary", "")
                )
                if not topics:
                    deletion_log["irrelevant"] += 1
                    continue
                article["topics"] = topics
                article["reliability_score"] = self._get_reliability_score(article.get("source", ""))
                if 1 in topics:
                    article["product_category"] = self.classifier.get_product_category(
                        article.get("title", ""),
                        article.get("summary", "")
                    )
                classified.append(article)

            # 按 Topic 分组 (T1-T4)
            articles_by_topic: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}
            for article in classified:
                for tid in article.get("topics", []):
                    if 1 <= tid <= 4:
                        articles_by_topic[tid].append(article)

            print("   📊 Initial topic distribution:")
            for tid in range(1, 5):
                print(f"      {self.TOPIC_NAMES[tid]}: {len(articles_by_topic[tid])} articles")
            self.classifier.print_stats()

            # ── Step 6: Google News 补充（Topic Coverage Guarantee）────────
            print("\n🎯 Step 6: Topic Coverage Guarantee (min 3 per topic)...")
            MIN_ARTICLES = 3
            for tid in range(1, 5):
                current = len(articles_by_topic[tid])
                if current < MIN_ARTICLES:
                    needed = MIN_ARTICLES - current
                    print(f"   ⚠️ {self.TOPIC_NAMES[tid]} needs {needed} more → searching Google News...")
                    keywords = TOPIC_SEARCH_KEYWORDS.get(tid, [])
                    new_arts = self.google_fetcher.search_by_topic(tid, keywords, days_back=3)
                    for art in new_arts[:needed + 2]:
                        topics = self.classifier.classify(art["title"], art.get("summary", ""))
                        if not topics:
                            deletion_log["irrelevant"] += 1
                            continue
                        if tid not in topics:
                            topics.append(tid)
                        art["topics"] = topics
                        art["reliability_score"] = self._get_reliability_score(art.get("source", ""))
                        art["published_date"] = self.parser.parse_date(art.get("published_raw", ""))
                        if 1 in topics:
                            art["product_category"] = self.classifier.get_product_category(
                                art["title"], art.get("summary", "")
                            )
                        classified.append(art)
                        articles_by_topic[tid].append(art)
                    print(f"      ✅ {self.TOPIC_NAMES[tid]}: now {len(articles_by_topic[tid])} articles")
                else:
                    print(f"   ✅ {self.TOPIC_NAMES[tid]}: {current} articles")

            # ── Step 7: 跨栏目去重（单一归属原则）────────────────────────
            print("\n🔄 Step 7: Cross-topic dedup → single ownership (T1>T2>T3>T4)...")
            articles_by_topic = self.classifier.cross_topic_deduplicate(articles_by_topic)

            # ── Step 7.5: 语义级去重（同一事件只保留一条）─────────────────
            print("\n🧠 Step 7.5: Semantic deduplication (same-event detection)...")
            total_before_semantic = sum(len(a) for a in articles_by_topic.values())
            all_articles_flat = []
            for arts in articles_by_topic.values():
                all_articles_flat.extend(arts)

            deduped_flat, sem_removed = self.classifier.semantic_deduplicate(all_articles_flat)
            deletion_log["semantic_duplicate"] += sem_removed

            # 重建 articles_by_topic（保留语义去重后的文章）
            kept_ids = {id(a) for a in deduped_flat}
            articles_by_topic = {1: [], 2: [], 3: [], 4: []}
            for article in deduped_flat:
                for tid in article.get("topics", []):
                    if 1 <= tid <= 4:
                        articles_by_topic[tid].append(article)
            print(f"   ✅ Semantic dedup: {total_before_semantic} → {len(deduped_flat)} (removed {sem_removed})")

            # ── Step 8: 标准去重（URL / 标题相似度 / 历史比对）──────────────
            print("\n🔍 Step 8: Standard deduplication (URL + title fuzzy + history)...")
            deduped = []
            for arts in articles_by_topic.values():
                deduped.extend(arts)
            final_articles, dedup_stats = self.deduplicator.deduplicate(deduped)
            deletion_log["duplicate"] += dedup_stats.get("duplicates_removed", 0)
            print(f"   ✅ {dedup_stats.get('total_before', '?')} → {dedup_stats.get('total_after', '?')}")

            # 重建 articles_by_topic（单一归属已在Step7确保）
            articles_by_topic = {1: [], 2: [], 3: [], 4: []}
            for article in final_articles:
                for tid in article.get("topics", []):
                    if 1 <= tid <= 4:
                        articles_by_topic[tid].append(article)

            # ── Step 8.5: T4 结构校验（缺时间或地点 → 删除）────────────────
            print("\n📅 Step 8.5: T4 structural validation (time + location required)...")
            t4_before = len(articles_by_topic[4])
            valid_t4 = []
            for article in articles_by_topic[4]:
                if self.reporter._t4_has_structure(article):
                    valid_t4.append(article)
                else:
                    deletion_log["t4_incomplete"] += 1
            articles_by_topic[4] = valid_t4
            t4_removed = t4_before - len(valid_t4)
            print(f"   ✅ T4: {t4_before} → {len(valid_t4)} ({t4_removed} removed for missing time/location)")

            # ── Step 9: AI 摘要 ──────────────────────────────────────────
            print("\n✍️ Step 9: Generating AI summaries...")
            final_articles = []
            for arts in articles_by_topic.values():
                final_articles.extend(arts)

            summarized = 0
            for article in final_articles[:60]:
                if not article.get("summary") or len(article.get("summary", "")) < 80:
                    article["summary"] = self.summarizer.summarize(
                        article.get("title", ""),
                        article.get("content", article.get("summary", ""))
                    )
                    summarized += 1
            print(f"   ✅ Summarized {summarized} articles")

            # ── Step 10: 最终QA清洗关卡（输出前逐条校验）────────────────────
            print("\n🚨 Step 10: Final QA gate (5-point check, delete on failure)...")
            articles_by_topic = self.reporter.final_qa_gate(articles_by_topic, deletion_log)

            # 重建最终列表
            final_articles = []
            for arts in articles_by_topic.values():
                final_articles.extend(arts)

            # ── Step 11: 数据清洗 ─────────────────────────────────────────
            print("\n🧹 Step 11: Data cleaning...")
            cleaned = []
            for article in final_articles:
                if not article.get("source") or article.get("source") == "unknown":
                    article["source_unreliable"] = True
                if article.get("link") or article.get("url"):
                    cleaned.append(article)
            final_articles = cleaned
            print(f"   ✅ Cleaned. Final count: {len(final_articles)}")

            # 打印最终分布
            print("\n   📊 Final topic distribution:")
            for tid in range(1, 5):
                print(f"      {self.TOPIC_NAMES[tid]}: {len(articles_by_topic[tid])} articles")

            # 打印删除汇总
            print("\n   🗑️ Deletion summary:")
            for reason, count in deletion_log.items():
                if count > 0:
                    print(f"      {reason}: {count}")

            # ── Step 12: 生成报告 ─────────────────────────────────────────
            print("\n📊 Step 12: Generating reports...")
            output_dir = self.base_dir / "output"
            output_dir.mkdir(exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")

            md_report = self.reporter.generate_structured_markdown(
                final_articles, dedup_stats, raw_count, deletion_log
            )
            md_path = output_dir / f"report_{date_str}.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_report)
            print(f"   ✅ Markdown report: {md_path}")

            html_report = self.reporter.generate_html(final_articles, dedup_stats)
            html_path = output_dir / f"report_{date_str}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_report)
            print(f"   ✅ HTML report: {html_path}")

            # ── Step 13: 发送邮件 ─────────────────────────────────────────
            if not dry_run:
                print("\n📧 Step 13: Sending email...")
                success = self.mailer.send(html_report, date_str)
                print("   ✅ Email sent!" if success else "   ❌ Email failed")
            else:
                print("\n📧 Step 13: Skipped (dry-run mode)")

            self.deduplicator.close()

            elapsed = (datetime.now() - self.start_time).total_seconds()
            print("\n" + "=" * 70)
            print(f"✅ Completed in {elapsed:.1f}s")
            print("=" * 70)

            return {"articles": final_articles, "stats": dedup_stats, "deletion_log": deletion_log}

        except Exception as e:
            print(f"\n❌ System failed: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samsung CE Intelligence System v6.0")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--test-email", action="store_true", help="Test email configuration")
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    args = parser.parse_args()

    system = SamsungIntelligenceSystem(config_path=args.config)

    if args.test_email:
        sys.exit(0 if system.mailer.send_test_email() else 1)
    else:
        result = system.run(dry_run=args.dry_run)
        sys.exit(1 if result.get("error") else 0)
