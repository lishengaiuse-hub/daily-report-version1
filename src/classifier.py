#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for Samsung CE Intelligence
Classifies articles into 5 predefined topics
"""

import re
from typing import List, Dict, Any
from collections import defaultdict

class TopicClassifier:
    """Classify articles into 5 Samsung CE topics"""
    
    def __init__(self, topics_config: Dict):
        self.config = topics_config
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for each topic"""
        self.topic_patterns = {}
        
        for topic_id, topic_config in self.config.items():
            patterns = []
            
            # Company patterns
            if 'keywords' in topic_config:
                keywords = topic_config.get('keywords', {})
                if isinstance(keywords, dict):
                    for category, words in keywords.items():
                        for word in words:
                            patterns.append(re.compile(r'\b' + re.escape(word.lower()) + r'\b'))
                else:
                    for word in keywords:
                        patterns.append(re.compile(r'\b' + re.escape(word.lower()) + r'\b'))
            
            # Direct keywords
            if 'keywords_direct' in topic_config:
                for word in topic_config['keywords_direct']:
                    patterns.append(re.compile(re.escape(word.lower())))
            
            # Locations for Topic 3
            if 'locations' in topic_config:
                for loc in topic_config['locations']:
                    patterns.append(re.compile(r'\b' + re.escape(loc.lower()) + r'\b'))
            
            # Events for Topic 4
            if 'events' in topic_config:
                for event in topic_config['events']:
                    patterns.append(re.compile(r'\b' + re.escape(event.lower()) + r'\b'))
            
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
            "tcl", "hisense", "haier", "midea", "xiaomi", "dreame", "roborock",
            "philips", "siemens", "panasonic", "apple", "vivo", "oppo", "honor",
            "huawei", "transsion", "tecno", "lenovo", "sony", "sharp", "lg", "gree"
        ]
        
        products = [
            "tv", "television", "oled", "microled", "qled", "mini led", "miniled",
            "display", "screen", "refrigerator", "fridge", "washing machine", "washer",
            "air conditioner", "ac", "air purifier", "vacuum", "robot vacuum",
            "smartphone", "phone", "foldable", "smartwatch", "wearable", "tablet"
        ]
        
        has_competitor = any(comp in original_title or comp in text for comp in competitors)
        has_product = any(product in text for product in products)
        
        return has_competitor and has_product
    
    def _check_topic_2(self, text: str) -> bool:
        """Check if article is about new technologies/components/materials"""
        technologies = [
            "micro led", "microled", "mini led", "miniled", "oled", "amoled",
            "qd-oled", "woled", "foled", "micro oled", "transparent display",
            "flexible display", "foldable display", "quantum dot", "gallium nitride",
            "gan", "silicon carbide", "sic", "perovskite", "graphene", "carbon nanotube",
            "solid state battery", "silicon anode", "lithium metal", "sodium ion",
            "tof", "lidar", "3d sensing", "under display camera", "vapor chamber",
            "ar眼镜", "vr眼镜", "智能眼镜", "可穿戴设备", "3d打印", "增材制造"
        ]
        
        suppliers = [
            "boe", "csot", "tianma", "visionox", "lg display", "samsung display",
            "universal display", "udc", "merck", "dupont", "lg chem", "qualcomm",
            "mediatek", "corning", "foxconn", "goertek", "rokid", "xreal"
        ]
        
        has_tech = any(tech in text for tech in technologies)
        has_supplier = any(supplier in text for supplier in suppliers)
        
        return has_tech and has_supplier
    
    def _check_topic_3(self, text: str) -> bool:
        """Check if article is about manufacturing expansion in SEA/India"""
        locations = [
            "vietnam", "thailand", "indonesia", "malaysia", "singapore",
            "philippines", "myanmar", "cambodia", "india", "bangladesh",
            "bac ninh", "thai nguyen", "hanoi", "ho chi minh", "bangkok",
            "jakarta", "penang", "chennai", "noida", "bangalore"
        ]
        
        keywords = [
            "factory", "plant", "manufacturing", "production", "assembly",
            "investment", "expansion", "new facility", "capacity", "relocation",
            "扩产", "增资", "投资", "新建", "奠基", "投产", "生产基地", "制造基地"
        ]
        
        has_location = any(loc in text for loc in locations)
        has_keyword = any(kw in text for kw in keywords)
        
        return has_location and has_keyword
    
    def _check_topic_4(self, text: str) -> bool:
        """Check if article is about exhibitions"""
        events = [
            "ces", "ifa", "mwc", "computex", "awe", "gitex", "display week",
            "sid display week", "touch taiwan", "exhibition", "展会", "博览会", "论坛"
        ]
        
        return any(event in text for event in events)
    
    def _check_topic_5(self, text: str) -> bool:
        """Check if article is about supply chain risk"""
        risks = [
            "shortage", "supply disruption", "supply chain", "delay", "bottleneck",
            "recall", "quality issue", "defect", "fire", "flood", "earthquake",
            "strike", "lockdown", "tariff", "trade war", "sanction", "export ban",
            "geopolitical", "political risk", "currency fluctuation"
        ]
        
        products = [
            "panel", "display", "screen", "chip", "semiconductor", "memory",
            "dram", "nand", "battery", "component", "module", "pcb", "sensor"
        ]
        
        has_risk = any(risk in text for risk in risks)
        has_product = any(product in text for product in products)
        
        return has_risk and has_product
    
    def get_counts(self, articles: List[Dict]) -> Dict[int, int]:
        """Get count of articles per topic"""
        counts = defaultdict(int)
        for article in articles:
            for topic in article.get('topics', []):
                counts[topic] += 1
        return dict(counts)
