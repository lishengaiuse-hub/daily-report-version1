#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for Samsung CE Intelligence
Version: 3.0 - 严格分类规则 + 跨栏目去重
"""

import re
import hashlib
from typing import List, Dict, Any, Tuple
from collections import defaultdict


class TopicClassifier:
    """
    严格分类器 - 执行T1/T2/T3/T4严格规则
    
    T1: 必须包含竞品品牌
    T2: 只允许技术/材料，排除品牌竞争
    T3: 地点必须在东南亚/印度 + 制造相关
    T4: 展会信息
    T5: 供应链风险
    """
    
    # =============================================
    # T1: 竞品品牌（必须包含）
    # =============================================
    COMPETITOR_BRANDS = [
        "apple", "xiaomi", "mi", "huawei", "oppo", "vivo",
        "lg", "sony", "haier", "hisense", "tcl", "gree",
        "midea", "panasonic", "philips", "sharp", "lenovo"
    ]
    
    # T1: 产品类别标签
    PRODUCT_CATEGORIES = {
        '手机': ['phone', 'smartphone', 'iphone', 'xiaomi', 'pixel', 'foldable', '折叠屏', '手机'],
        '家电': ['tv', 'television', 'oled', 'qled', 'refrigerator', 'fridge', 
                'washing machine', 'washer', 'air conditioner', 'ac', 'vacuum', 
                '电视', '冰箱', '洗衣机', '空调', '扫地机器人'],
        '芯片': ['chip', 'soc', 'processor', 'cpu', 'gpu', 'tensor', '骁龙', '天玑', '芯片'],
        '显示': ['display', 'panel', 'oled', 'microled', 'miniled', 'screen', '显示', '面板']
    }
    
    # =============================================
    # T2: 技术/材料关键词
    # =============================================
    TECH_KEYWORDS = [
        'semiconductor', 'material', 'battery', 'display tech', 'sensor',
        'oled', 'microled', 'miniled', 'quantum dot', 'gan', 'silicon carbide',
        'graphene', 'perovskite', 'solid state battery', '3d printing',
        'thermal management', 'ai chip', 'npu', 'chip', '半导体', '材料', 
        '电池', '传感器', '显示技术', '散热', '封装'
    ]
    
    # T2: 排除关键词（品牌竞争类不应进入T2）
    T2_EXCLUDE = [
        'launch', 'release', 'price', 'market share', 'vs', 
        '发布', '上市', '价格', '市场份额', '竞争'
    ]
    
    # =============================================
    # T3: 东南亚/印度制造
    # =============================================
    SEA_LOCATIONS = [
        'vietnam', 'thailand', 'indonesia', 'malaysia', 'singapore', 'philippines',
        'india', 'bangladesh', 'myanmar', 'cambodia', '越南', '泰国', '印尼', 
        '印度', '新加坡', '马来西亚', '菲律宾'
    ]
    
    MANUFACTURING_KEYWORDS = [
        'factory', 'plant', 'manufacturing', 'production', 'assembly',
        'investment', 'expansion', 'capacity', 'facility', '工厂', '制造', 
        '生产', '扩建', '投资', '产能', '代工'
    ]
    
    # =============================================
    # T4: 展会关键词
    # =============================================
    EXHIBITION_KEYWORDS = [
        'ces', 'ifa', 'mwc', 'computex', 'awe', 'display week',
        'sid', 'exhibition', 'trade show', 'conference', '展会', '博览会', 
        '展览', '论坛', '消费电子展'
    ]
    
    # =============================================
    # T5: 供应链风险关键词
    # =============================================
    RISK_KEYWORDS = [
        'shortage', 'disruption', 'delay', 'bottleneck', 'recall',
        'quality issue', 'tariff', 'trade war', 'sanction', 
        'geopolitical', 'price increase', 'supply chain', 'logistics',
        '缺货', '短缺', '延迟', '关税', '供应链', '涨价', '断供'
    ]
    
    # =============================================
    # 跨栏目去重优先级 (数值越高优先级越高)
    # =============================================
    TOPIC_PRIORITY = {
        1: 5,   # 竞品动态 - 最高优先级
        2: 4,   # 技术/材料
        3: 3,   # 制造
        4: 2,   # 展会
        5: 1    # 供应链风险 - 最低优先级
    }
    
    def __init__(self, topics_config: Dict = None):
        self.config = topics_config or {}
        self.stats = {
            'classified': 0, 
            'rejected': 0,
            'by_topic': defaultdict(int)
        }
        self._last_category = '产品'
    
    def classify(self, title: str, content: str = "") -> List[int]:
        """
        严格分类 - 返回符合规则的Topic列表
        
        Args:
            title: 文章标题
            content: 文章内容/摘要
            
        Returns:
            List of topic IDs (1-5)
        """
        text = (title + " " + content).lower()
        
        topics = []
        
        # T1: 竞品动态（最严格）
        if self._check_t1(title, text):
            category = self._get_product_category(title, text)
            self._last_category = category
            topics.append(1)
            self.stats['by_topic'][1] += 1
        
        # T2: 技术/材料（排除品牌竞争）
        if self._check_t2(text):
            topics.append(2)
            self.stats['by_topic'][2] += 1
        
        # T3: 制造（SEA/India）
        if self._check_t3(text):
            topics.append(3)
            self.stats['by_topic'][3] += 1
        
        # T4: 展会
        if self._check_t4(text):
            topics.append(4)
            self.stats['by_topic'][4] += 1
        
        # T5: 供应链风险
        if self._check_t5(text):
            topics.append(5)
            self.stats['by_topic'][5] += 1
        
        if topics:
            self.stats['classified'] += 1
        else:
            self.stats['rejected'] += 1
        
        return topics
    
    def _check_t1(self, title: str, text: str) -> bool:
        """
        T1 严格检查：
        1. 必须包含竞品品牌
        2. 排除纯技术讨论
        """
        # 检查品牌
        has_brand = False
        title_lower = title.lower()
        for brand in self.COMPETITOR_BRANDS:
            if brand in title_lower or brand in text:
                has_brand = True
                break
        
        if not has_brand:
            return False
        
        # 排除纯技术内容（没有产品发布/竞争信息）
        tech_only_keywords = ['chip', 'display', 'material', 'technology', 'innovation']
        competition_keywords = ['launch', 'release', 'vs', 'against', 'competitor', '发布', '上市', '竞争']
        
        has_tech_only = all(kw in text for kw in tech_only_keywords[:3])
        has_competition = any(kw in text for kw in competition_keywords)
        
        if has_tech_only and not has_competition:
            return False
        
        return True
    
    def _get_product_category(self, title: str, text: str) -> str:
        """获取产品类别标签 [手机] / [家电] / [芯片] / [显示]"""
        combined = (title + " " + text).lower()
        
        for category, keywords in self.PRODUCT_CATEGORIES.items():
            for kw in keywords:
                if kw in combined:
                    return category
        
        return '产品'
    
    def _check_t2(self, text: str) -> bool:
        """
        T2 严格检查：
        1. 包含技术/材料关键词
        2. 排除品牌竞争内容
        """
        has_tech = any(kw in text for kw in self.TECH_KEYWORDS)
        if not has_tech:
            return False
        
        # 排除品牌竞争内容
        is_competitive = any(kw in text for kw in self.T2_EXCLUDE)
        if is_competitive:
            # 检查是否同时包含竞品品牌
            for brand in self.COMPETITOR_BRANDS:
                if brand in text:
                    return False
        
        return True
    
    def _check_t3(self, text: str) -> bool:
        """
        T3 严格检查：
        1. 地点必须在东南亚/印度
        2. 必须包含制造相关关键词
        """
        has_location = any(loc in text for loc in self.SEA_LOCATIONS)
        has_mfg = any(kw in text for kw in self.MANUFACTURING_KEYWORDS)
        
        return has_location and has_mfg
    
    def _check_t4(self, text: str) -> bool:
        """T4 展会检查"""
        return any(kw in text for kw in self.EXHIBITION_KEYWORDS)
    
    def _check_t5(self, text: str) -> bool:
        """T5 供应链风险检查"""
        return any(kw in text for kw in self.RISK_KEYWORDS)
    
    def get_category_label(self) -> str:
        """获取最近分类的类别标签"""
        return getattr(self, '_last_category', '产品')
    
    def cross_topic_deduplicate(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
        """
        跨栏目去重：同一新闻只保留在优先级最高的Topic
        
        Topic优先级: T1(竞品) > T2(技术) > T3(制造) > T4(展会) > T5(供应链)
        
        Args:
            articles_by_topic: {topic_id: [articles]}
            
        Returns:
            去重后的 {topic_id: [articles]}
        """
        # 收集所有文章的指纹
        article_fingerprints = {}  # fingerprint -> (topic_id, article, priority)
        
        for topic_id, articles in articles_by_topic.items():
            for article in articles:
                # 生成指纹：URL + 标题前50字符
                url = article.get('link', article.get('url', ''))
                title = article.get('title', '')[:50]
                fingerprint = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                
                priority = self.TOPIC_PRIORITY.get(topic_id, 0)
                
                if fingerprint not in article_fingerprints:
                    article_fingerprints[fingerprint] = (topic_id, article, priority)
                else:
                    existing_topic, existing_article, existing_priority = article_fingerprints[fingerprint]
                    # 保留优先级更高的
                    if priority > existing_priority:
                        article_fingerprints[fingerprint] = (topic_id, article, priority)
        
        # 重建按Topic分组的文章
        result = {tid: [] for tid in range(1, 6)}
        for fingerprint, (topic_id, article, _) in article_fingerprints.items():
            result[topic_id].append(article)
        
        # 统计去重效果
        before_total = sum(len(articles) for articles in articles_by_topic.values())
        after_total = sum(len(articles) for articles in result.values())
        removed = before_total - after_total
        
        print(f"   🔄 Cross-topic dedup: {before_total} → {after_total} (removed {removed} duplicates)")
        
        return result
    
    def get_stats(self) -> Dict:
        """获取分类统计"""
        return dict(self.stats)
    
    def print_stats(self):
        """打印分类统计"""
        print("\n   📊 Classification Statistics:")
        print(f"      Classified: {self.stats['classified']} articles")
        print(f"      Rejected: {self.stats['rejected']} articles")
        print("      By topic:")
        for topic_id in range(1, 6):
            count = self.stats['by_topic'][topic_id]
            topic_name = {1: 'T1-竞品', 2: 'T2-技术', 3: 'T3-制造', 4: 'T4-展会', 5: 'T5-供应链'}.get(topic_id, f'T{topic_id}')
            print(f"         {topic_name}: {count}")
