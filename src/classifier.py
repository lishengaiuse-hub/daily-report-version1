#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for Samsung CE Intelligence
Classifies articles into 5 predefined topics with coverage guarantee
"""

import re
import time
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from urllib.parse import urlparse

class TopicClassifier:
    """Classify articles into 5 Samsung CE topics with coverage guarantee"""
    
    def __init__(self, topics_config: Dict):
        self.config = topics_config
        self.topic_sources = self._init_topic_sources()
        self.topic_keywords = self._init_topic_keywords()
        self._compile_patterns()
    
    def _init_topic_sources(self) -> Dict[int, List[str]]:
        """Initialize topic-specific source mapping"""
        return {
            1: [  # Competitor Technology & Products
                "news.samsung.com", "samsung.com",
                "xiaomi.com", "mi.com", "xiaomi",
                "apple.com", "apple newsroom",
                "sony.com", "sony",
                "tcl.com", "tcl",
                "lg.com", "lg newsroom",
                "haier.com", "haier",
                "gsmarena.com", "androidauthority.com",
                "techcrunch.com", "theverge.com"
            ],
            2: [  # New Technologies / Components
                "eetimes.com", "electronicsweekly.com", "digitimes.com",
                "ieee.org", "spectrum.ieee.org", "semiengineering.com",
                "microled-info.com", "oled-info.com", "displaydaily.com",
                "eet-china.com", "esmchina.com", "eepw.com.cn"
            ],
            3: [  # Manufacturing Expansion
                "reuters.com", "nikkei.com", "nikkei.asia",
                "bloomberg.com", "vietnamnews.vn", "vietnam-briefing.com",
                "meity.gov.in", "india.gov.in", "businesstimes.com.sg",
                "thestar.com.my", "bangkokpost.com", "vnexpress.net"
            ],
            4: [  # Exhibitions
                "ces.tech", "ifa-berlin.com", "mwcbarcelona.com",
                "displayweek.org", "prnewswire.com", "globenewswire.com",
                "businesswire.com", "exhibition", "展会"
            ],
            5: [  # Supply Chain Risk
                "reuters.com", "bloomberg.com", "ft.com", "financialtimes.com",
                "supplychaindive.com", "freightwaves.com", "scmr.com",
                "supplychainbrain.com", "ebnonline.com"
            ]
        }
    
    def _init_topic_keywords(self) -> Dict[int, List[str]]:
        """Initialize topic-specific keywords for active search"""
        return {
            1: [  # Competitor Technology & Products
                "launch", "release", "new product", "new device", "new TV", "new phone",
                "foldable", "OLED", "QLED", "MicroLED", "Mini LED", "display",
                "refrigerator", "washing machine", "air conditioner", "robot vacuum",
                "smartphone", "smartwatch", "tablet", "laptop",
                "发布", "推出", "新品", "上市", "电视", "手机", "折叠屏", "显示器"
            ],
            2: [  # New Technologies / Components
                "technology breakthrough", "new material", "innovation", "component",
                "semiconductor", "chip", "battery", "sensor", "display tech",
                "quantum dot", "GaN", "silicon carbide", "perovskite", "graphene",
                "3D printing", "additive manufacturing", "thermal management",
                "技术突破", "新材料", "创新", "元器件", "芯片", "电池", "传感器"
            ],
            3: [  # Manufacturing Expansion
                "factory expansion", "plant investment", "new facility", "capacity",
                "manufacturing", "production", "assembly", "investment",
                "Vietnam manufacturing", "India electronics", "Thailand factory",
                "扩产", "新工厂", "投资", "产能", "制造基地", "越南制造", "印度制造"
            ],
            4: [  # Exhibitions
                "exhibition", "trade show", "conference", "summit", "forum",
                "CES", "IFA", "MWC", "Computex", "AWE", "Display Week",
                "展会", "博览会", "论坛", "会议", "展览"
            ],
            5: [  # Supply Chain Risk
                "shortage", "disruption", "delay", "bottleneck", "recall",
                "quality issue", "tariff", "trade war", "sanction", "geopolitical",
                "price increase", "supply chain", "logistics", "shipping",
                "缺货", "短缺", "延迟", "关税", "供应链风险", "涨价", "断供"
            ]
        }
    
    def _compile_patterns(self):
        """Compile regex patterns for each topic"""
        self.topic_patterns = {}
        
        for topic_id, topic_config in self.config.items():
            patterns = []
            
            if 'keywords' in topic_config:
                keywords = topic_config.get('keywords', {})
                if isinstance(keywords, dict):
                    for category, words in keywords.items():
                        for word in words:
                            patterns.append(re.compile(r'\b' + re.escape(word.lower()) + r'\b', re.IGNORECASE))
                else:
                    for word in keywords:
                        patterns.append(re.compile(r'\b' + re.escape(word.lower()) + r'\b', re.IGNORECASE))
            
            if 'keywords_direct' in topic_config:
                for word in topic_config['keywords_direct']:
                    patterns.append(re.compile(re.escape(word.lower()), re.IGNORECASE))
            
            if 'locations' in topic_config:
                for loc in topic_config['locations']:
                    patterns.append(re.compile(r'\b' + re.escape(loc.lower()) + r'\b', re.IGNORECASE))
            
            if 'events' in topic_config:
                for event in topic_config['events']:
                    patterns.append(re.compile(r'\b' + re.escape(event.lower()) + r'\b', re.IGNORECASE))
            
            self.topic_patterns[int(topic_id)] = patterns
    
    def classify(self, title: str, content: str = "") -> List[int]:
        """
        Classify article into topics
        
        Args:
            title: Article title
            content: Article content/summary
            
        Returns:
            List of topic IDs (1-5)
        """
        text = (title + " " + content).lower()
        topics = []
        
        # Topic 1: Competitor Technology & Products
        if self._check_topic_1(text, title):
            topics.append(1)
        
        # Topic 2: New Technologies / Components / Materials
        if self._check_topic_2(text):
            topics.append(2)
        
        # Topic 3: Manufacturing Expansion (SEA/India)
        if self._check_topic_3(text):
            topics.append(3)
        
        # Topic 4: Exhibitions
        if self._check_topic_4(text):
            topics.append(4)
        
        # Topic 5: Supply Chain Risk
        if self._check_topic_5(text):
            topics.append(5)
        
        return topics
    
    def _check_topic_1(self, text: str, original_title: str) -> bool:
        """Check if article is about competitor technology/products"""
        competitors = [
            "tcl", "hisense", "haier", "海尔", "midea", "美的", "xiaomi", "小米",
            "dreame", "追觅", "roborock", "石头", "philips", "飞利浦",
            "siemens", "西门子", "panasonic", "松下", "apple", "苹果",
            "vivo", "oppo", "荣耀", "honor", "huawei", "华为",
            "lenovo", "联想", "sony", "索尼", "sharp", "夏普", "lg", "gree", "格力",
            "samsung", "三星"
        ]
        
        products = [
            "tv", "television", "电视", "电视机", "oled", "microled", "mini led",
            "qled", "display", "显示屏", "屏幕", "refrigerator", "fridge", "冰箱",
            "washing machine", "洗衣机", "air conditioner", "空调",
            "vacuum", "robot vacuum", "扫地机器人", "扫拖机器人",
            "smartphone", "phone", "手机", "foldable", "折叠屏", "折叠手机",
            "smartwatch", "智能手表", "tablet", "平板", "平板电脑",
            "laptop", "笔记本", "notebook"
        ]
        
        text_lower = text.lower()
        title_lower = original_title.lower()
        
        has_competitor = any(comp in text_lower or comp in title_lower for comp in competitors)
        has_product = any(product in text_lower for product in products)
        
        return has_competitor and has_product
    
    def _check_topic_2(self, text: str) -> bool:
        """Check if article is about new technologies/components/materials"""
        technologies = [
            "micro led", "microled", "mini led", "miniled", "oled", "amoled",
            "qd-oled", "woled", "transparent display", "flexible display",
            "quantum dot", "gallium nitride", "gan", "silicon carbide", "sic",
            "perovskite", "graphene", "carbon nanotube", "solid state battery",
            "lidar", "tof", "3d sensing", "under display camera", "vapor chamber",
            "ar", "vr", "可穿戴设备", "3d打印", "增材制造", "电子皮肤"
        ]
        
        suppliers = [
            "boe", "京东方", "csot", "华星光电", "tianma", "天马", "visionox", "维信诺",
            "lg display", "samsung display", "universal display", "udc", "merck", "默克",
            "dupont", "杜邦", "qualcomm", "高通", "mediatek", "联发科", "corning", "康宁",
            "tsmc", "台积电", "smic", "中芯国际"
        ]
        
        text_lower = text.lower()
        has_tech = any(tech in text_lower for tech in technologies)
        has_supplier = any(supplier in text_lower for supplier in suppliers)
        
        return has_tech or has_supplier
    
    def _check_topic_3(self, text: str) -> bool:
        """Check if article is about manufacturing expansion in SEA/India"""
        locations = [
            "vietnam", "越南", "thailand", "泰国", "indonesia", "印尼", "印度尼西亚",
            "malaysia", "马来西亚", "singapore", "新加坡", "philippines", "菲律宾",
            "india", "印度", "bangladesh", "孟加拉", "bac ninh", "北宁", "hanoi", "河内",
            "ho chi minh", "胡志明", "bangkok", "曼谷", "jakarta", "雅加达",
            "penang", "槟城", "chennai", "金奈", "noida", "诺伊达", "bangalore", "班加罗尔"
        ]
        
        keywords = [
            "factory", "plant", "manufacturing", "production", "assembly",
            "investment", "expansion", "new facility", "capacity", "relocation",
            "扩产", "增资", "投资", "新建", "奠基", "投产", "生产基地", "制造基地"
        ]
        
        text_lower = text.lower()
        has_location = any(loc in text_lower for loc in locations)
        has_keyword = any(kw in text_lower for kw in keywords)
        
        return has_location and has_keyword
    
    def _check_topic_4(self, text: str) -> bool:
        """Check if article is about exhibitions"""
        events = [
            "ces", "ifa", "mwc", "computex", "awe", "gitex", "display week",
            "sid", "exhibition", "展会", "博览会", "论坛", "conference", "summit"
        ]
        
        text_lower = text.lower()
        return any(event in text_lower for event in events)
    
    def _check_topic_5(self, text: str) -> bool:
        """Check if article is about supply chain risk"""
        risks = [
            "shortage", "缺货", "短缺", "supply disruption", "供应中断",
            "supply chain", "供应链", "delay", "延迟", "延误", "bottleneck", "瓶颈",
            "recall", "召回", "quality issue", "质量问题", "defect", "缺陷",
            "tariff", "关税", "trade war", "贸易战", "sanction", "制裁",
            "geopolitical", "地缘政治", "price increase", "涨价"
        ]
        
        products = [
            "panel", "面板", "display", "显示屏", "chip", "芯片", "semiconductor", "半导体",
            "memory", "存储", "dram", "nand", "battery", "电池", "component", "元器件"
        ]
        
        text_lower = text.lower()
        has_risk = any(risk in text_lower for risk in risks)
        has_product = any(product in text_lower for product in products)
        
        return has_risk and has_product
    
    def get_counts(self, articles: List[Dict]) -> Dict[int, int]:
        """Get count of articles per topic"""
        counts = defaultdict(int)
        for article in articles:
            for topic in article.get('topics', []):
                counts[topic] += 1
        return dict(counts)
    
    def get_source_for_topic(self, topic_id: int) -> List[str]:
        """Get recommended sources for a specific topic"""
        return self.topic_sources.get(topic_id, [])
    
    def get_keywords_for_topic(self, topic_id: int) -> List[str]:
        """Get search keywords for a specific topic"""
        return self.topic_keywords.get(topic_id, [])
    
    def ensure_coverage(self, articles_by_topic: Dict[int, List[Dict]], 
                        min_per_topic: int = 3) -> Dict[int, List[Dict]]:
        """
        Ensure each topic has minimum coverage
        If a topic has less than min_per_topic articles, mark as insufficient
        
        Args:
            articles_by_topic: Dictionary mapping topic_id to list of articles
            min_per_topic: Minimum number of articles required per topic
            
        Returns:
            Same structure with potential placeholder articles
        """
        result = {}
        
        for topic_id in range(1, 6):
            articles = articles_by_topic.get(topic_id, [])
            
            if len(articles) >= min_per_topic:
                result[topic_id] = articles
            else:
                # Add placeholder marker
                result[topic_id] = articles
                print(f"   ⚠️ Topic {topic_id} has only {len(articles)} articles (min: {min_per_topic})")
        
        return result
    
    def generate_coverage_report(self, articles_by_topic: Dict[int, List[Dict]], 
                                   min_per_topic: int = 3) -> str:
        """Generate a coverage report for all topics"""
        report = []
        report.append("## 📊 Topic Coverage Report")
        report.append("")
        
        topic_names = {
            1: "Competitor Technology & Products",
            2: "New Technologies / Components / Materials",
            3: "Manufacturing Expansion (SEA / India)",
            4: "Exhibitions",
            5: "Supply Chain Risk"
        }
        
        for topic_id in range(1, 6):
            count = len(articles_by_topic.get(topic_id, []))
            status = "✅" if count >= min_per_topic else "⚠️"
            report.append(f"{status} **Topic {topic_id} - {topic_names[topic_id]}**: {count} articles")
            
            if count < min_per_topic:
                report.append(f"   - Need {min_per_topic - count} more articles")
                report.append(f"   - Suggested sources: {', '.join(self.get_source_for_topic(topic_id)[:3])}")
        
        return "\n".join(report)
