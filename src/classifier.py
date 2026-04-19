#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for Samsung CE Intelligence
Version: 4.0 - 严格分类规则 + 跨栏目去重 + 产品类别标签
"""

import re
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict


class TopicClassifier:
    """
    严格分类器 - 执行T1/T2/T3/T4/T5严格规则
    
    分类规则：
    - T1: 竞品动态 - 必须包含竞品品牌，排除纯技术讨论
    - T2: 技术/材料 - 只允许技术/材料内容，排除品牌竞争
    - T3: 制造(SEA/India) - 地点必须在东南亚/印度 + 制造相关
    - T4: 展会 - 展会名称 + 时间 + 地点
    - T5: 供应链风险 - 供应链相关风险关键词
    
    跨栏目去重优先级: T1 > T2 > T3 > T4 > T5
    """
    
    # =============================================
    # T1: 竞品品牌（必须包含）
    # =============================================
    COMPETITOR_BRANDS = [
        "apple", "苹果", "xiaomi", "小米", "mi", "huawei", "华为", 
        "oppo", "vivo", "lg", "sony", "索尼", "haier", "海尔",
        "hisense", "海信", "tcl", "gree", "格力", "midea", "美的",
        "panasonic", "松下", "philips", "飞利浦", "sharp", "夏普", 
        "lenovo", "联想", "roborock", "石头", "dreame", "追觅"
    ]
    
    # T1: 产品类别标签映射
    PRODUCT_CATEGORIES = {
        '手机': ['phone', 'smartphone', 'iphone', 'xiaomi', 'pixel', 
                'foldable', '折叠屏', '手机', '智能手机'],
        '家电': ['tv', 'television', 'oled', 'qled', 'miniled', 'microled',
                'refrigerator', 'fridge', 'washing machine', 'washer', 
                'air conditioner', 'ac', 'vacuum', 'robot vacuum',
                '电视', '冰箱', '洗衣机', '空调', '扫地机器人', '吸尘器'],
        '芯片': ['chip', 'soc', 'processor', 'cpu', 'gpu', 'tensor', 
                'snapdragon', 'dimensity', 'a系列', '骁龙', '天玑', '芯片', '处理器'],
        '显示': ['display', 'panel', 'oled', 'microled', 'miniled', 
                'qled', 'screen', '显示', '面板', '屏幕']
    }
    
    # T1: 竞争相关关键词（用于判断是否为竞争内容）
    COMPETITION_KEYWORDS = [
        'launch', 'release', 'announce', 'unveil', 'introduce',
        'vs', 'against', 'compete', 'rival', 'beat', 'overtake',
        '发布', '上市', '推出', '亮相', '宣布', '竞争', '超越', '击败'
    ]
    
    # =============================================
    # T2: 技术/材料关键词
    # =============================================
    TECH_KEYWORDS = {
        'semiconductor': ['semiconductor', 'chip', 'wafer', 'foundry', '制程', '晶圆', '半导体'],
        'material': ['material', 'graphene', 'carbon', 'polymer', 'composite', '材料', '石墨烯', '复合材料'],
        'battery': ['battery', 'cell', 'energy storage', 'solid state', '电池', '储能', '固态电池'],
        'display': ['oled', 'microled', 'miniled', 'qled', 'display', 'panel', '显示', '面板'],
        'thermal': ['thermal', 'cooling', 'heat sink', '散热', '热管理'],
        'sensor': ['sensor', 'lidar', 'tof', 'cmos', '传感器', '激光雷达'],
        'manufacturing_tech': ['3d printing', 'additive manufacturing', 'injection molding', '3d打印', '增材制造']
    }
    
    # T2: 排除关键词（品牌竞争类不应进入T2）
    T2_EXCLUDE_KEYWORDS = [
        'launch', 'release', 'price', 'market share', 'sales', 
        'vs', 'competitor', 'brand', '发布', '上市', '价格', 
        '市场份额', '销量', '竞争', '品牌'
    ]
    
    # =============================================
    # T3: 东南亚/印度地点
    # =============================================
    SEA_LOCATIONS = {
        'vietnam': ['vietnam', 'viet nam', 'vietnamese', '越南', 'hanoi', 'ho chi minh', 'haiphong'],
        'thailand': ['thailand', 'thai', 'bangkok', '泰国', '曼谷'],
        'indonesia': ['indonesia', 'indonesian', 'jakarta', '印尼', '雅加达'],
        'malaysia': ['malaysia', 'malaysian', 'kuala lumpur', 'penang', '马来西亚', '吉隆坡', '槟城'],
        'singapore': ['singapore', 'singaporean', '新加坡'],
        'philippines': ['philippines', 'filipino', 'manila', '菲律宾', '马尼拉'],
        'india': ['india', 'indian', 'new delhi', 'mumbai', 'bangalore', 'chennai', '印度', '新德里', '孟买', '班加罗尔'],
        'bangladesh': ['bangladesh', 'bangladeshi', 'dhaka', '孟加拉', '达卡']
    }
    
    MANUFACTURING_KEYWORDS = {
        'factory': ['factory', 'plant', 'facility', '工厂', '厂房'],
        'production': ['production', 'manufacturing', 'assembly', '生产', '制造', '组装'],
        'investment': ['investment', 'invest', 'funding', '投资', '注资'],
        'expansion': ['expansion', 'expand', 'capacity', '扩产', '扩建', '产能'],
        'relocation': ['relocation', 'move', 'shift', '转移', '迁移']
    }
    
    # =============================================
    # T4: 展会关键词
    # =============================================
    EXHIBITION_KEYWORDS = {
        'ces': ['ces', 'consumer electronics show', '国际消费电子展'],
        'ifa': ['ifa', '柏林消费电子展'],
        'mwc': ['mwc', 'mobile world congress', '世界移动通信大会'],
        'computex': ['computex', '台北电脑展'],
        'awe': ['awe', '中国家电博览会'],
        'display_week': ['display week', 'sid', '显示周'],
        'other': ['exhibition', 'trade show', 'conference', 'summit', 'forum', 
                  '展会', '博览会', '展览', '论坛', '会议', '峰会']
    }
    
    # =============================================
    # T5: 供应链风险关键词
    # =============================================
    RISK_KEYWORDS = {
        'shortage': ['shortage', 'short of', '缺货', '短缺', '供不应求'],
        'disruption': ['disruption', 'interrupt', '中断', ' disruption', '干扰'],
        'delay': ['delay', 'late', 'backlog', '延迟', '延误', '积压'],
        'tariff': ['tariff', 'duty', 'customs', '关税', '税率', '海关'],
        'trade_war': ['trade war', 'trade dispute', '贸易战', '贸易争端'],
        'sanction': ['sanction', 'embargo', 'restriction', '制裁', '禁运', '限制'],
        'geopolitical': ['geopolitical', 'political risk', '地缘政治', '政治风险'],
        'price': ['price increase', 'price hike', '涨价', '价格上涨'],
        'quality': ['recall', 'quality issue', 'defect', '召回', '质量问题', '缺陷']
    }
    
    # =============================================
    # 无关内容过滤关键词
    # =============================================
    IRRELEVANT_KEYWORDS = [
        'hotel', 'booking', 'travel', 'tourism', 'restaurant', 'food',
        'furniture', 'real estate', 'property', 'stock', 'crypto', 
        'bitcoin', 'blockchain', 'nft', 'sports', 'entertainment',
        'movie', 'music', 'celebrity', 'gaming', 'game',
        '酒店', '预订', '旅游', '餐厅', '美食', '家具', '房地产',
        '股票', '加密货币', '比特币', '区块链', '体育', '娱乐',
        '电影', '音乐', '明星', '游戏'
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
            'filtered_irrelevant': 0,
            'by_topic': defaultdict(int),
            'by_category': defaultdict(int)
        }
        self._last_category = '产品'
        self._last_product = ''
    
    def is_relevant(self, title: str, content: str = "") -> bool:
        """
        检查内容是否与三星业务相关（过滤无关内容）
        
        Args:
            title: 文章标题
            content: 文章内容
            
        Returns:
            True if relevant, False otherwise
        """
        text = (title + " " + content).lower()
        
        for keyword in self.IRRELEVANT_KEYWORDS:
            if keyword.lower() in text:
                return False
        
        return True
    
    def classify(self, title: str, content: str = "") -> List[int]:
        """
        严格分类 - 返回符合规则的Topic列表
        
        Args:
            title: 文章标题
            content: 文章内容/摘要
            
        Returns:
            List of topic IDs (1-5)
        """
        # 首先过滤无关内容
        if not self.is_relevant(title, content):
            self.stats['filtered_irrelevant'] += 1
            return []
        
        text = (title + " " + content).lower()
        topics = []
        
        # T1: 竞品动态（最严格）
        if self._check_t1(title, text):
            category = self._get_product_category(title, text)
            self._last_category = category
            self.stats['by_category'][category] += 1
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
        2. 必须包含产品相关关键词
        3. 排除纯技术讨论
        """
        title_lower = title.lower()
        
        # 检查是否包含竞品品牌
        has_brand = False
        matched_brand = None
        for brand in self.COMPETITOR_BRANDS:
            if brand.lower() in title_lower or brand.lower() in text:
                has_brand = True
                matched_brand = brand
                break
        
        if not has_brand:
            return False
        
        # 检查是否包含产品关键词
        has_product = False
        for category, keywords in self.PRODUCT_CATEGORIES.items():
            for kw in keywords:
                if kw.lower() in text or kw.lower() in title_lower:
                    has_product = True
                    self._last_product = category
                    break
            if has_product:
                break
        
        if not has_product:
            return False
        
        # 检查是否包含竞争相关关键词（确保是竞争动态而非纯技术）
        has_competition = any(kw.lower() in text for kw in self.COMPETITION_KEYWORDS)
        
        # 如果是纯技术内容但没有竞争动态，排除
        if not has_competition:
            # 检查是否为纯技术内容
            tech_count = sum(1 for tech_list in self.TECH_KEYWORDS.values() 
                           for kw in tech_list if kw.lower() in text)
            if tech_count > 3:  # 多个技术关键词
                return False
        
        return True
    
    def _get_product_category(self, title: str, text: str) -> str:
        """获取产品类别标签 [手机] / [家电] / [芯片] / [显示]"""
        combined = (title + " " + text).lower()
        
        for category, keywords in self.PRODUCT_CATEGORIES.items():
            for kw in keywords:
                if kw.lower() in combined:
                    return category
        
        return '产品'
    
    def get_category_label(self) -> str:
        """获取最近分类的类别标签（用于报告）"""
        return self._last_category
    
    def _check_t2(self, text: str) -> bool:
        """
        T2 严格检查：
        1. 包含技术/材料关键词
        2. 排除品牌竞争内容
        3. 排除纯商业新闻
        """
        # 检查技术关键词
        has_tech = False
        matched_tech = []
        for category, keywords in self.TECH_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    has_tech = True
                    matched_tech.append(category)
                    break
            if has_tech:
                break
        
        if not has_tech:
            return False
        
        # 排除品牌竞争内容
        for kw in self.T2_EXCLUDE_KEYWORDS:
            if kw.lower() in text:
                # 检查是否同时包含竞品品牌
                for brand in self.COMPETITOR_BRANDS:
                    if brand.lower() in text:
                        return False
        
        return True
    
    def _check_t3(self, text: str) -> bool:
        """
        T3 严格检查：
        1. 地点必须在东南亚/印度
        2. 必须包含制造相关关键词
        """
        # 检查地点
        has_location = False
        matched_location = None
        for location, keywords in self.SEA_LOCATIONS.items():
            for kw in keywords:
                if kw.lower() in text:
                    has_location = True
                    matched_location = location
                    break
            if has_location:
                break
        
        if not has_location:
            return False
        
        # 检查制造关键词
        has_mfg = False
        for category, keywords in self.MANUFACTURING_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    has_mfg = True
                    break
            if has_mfg:
                break
        
        return has_mfg
    
    def _check_t4(self, text: str) -> bool:
        """T4 展会检查"""
        for category, keywords in self.EXHIBITION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    return True
        return False
    
    def _check_t5(self, text: str) -> bool:
        """T5 供应链风险检查"""
        for category, keywords in self.RISK_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    return True
        return False
    
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
        
        before_total = sum(len(articles) for articles in articles_by_topic.values())
        
        for topic_id, articles in articles_by_topic.items():
            for article in articles:
                # 生成指纹：URL + 标题前50字符 + 内容前100字符
                url = article.get('link', article.get('url', ''))
                title = article.get('title', '')[:50]
                content = article.get('summary', article.get('content', ''))[:100]
                fingerprint = hashlib.md5(f"{url}_{title}_{content}".encode()).hexdigest()
                
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
        
        after_total = sum(len(articles) for articles in result.values())
        removed = before_total - after_total
        
        print(f"   🔄 Cross-topic dedup: {before_total} → {after_total} (removed {removed} duplicates)")
        
        return result
    
    def extract_exhibition_info(self, text: str) -> Dict[str, str]:
        """
        从文本中提取展会信息
        
        Returns:
            Dict with keys: name, date, location, website
        """
        info = {
            'name': '',
            'date': '',
            'location': '',
            'website': ''
        }
        
        # 提取展会名称
        for category, keywords in self.EXHIBITION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    info['name'] = kw.upper()
                    break
            if info['name']:
                break
        
        # 提取日期 (YYYY-MM-DD 或 MM/DD/YYYY 格式)
        date_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
            r'(\d{4})年(\d{1,2})月(\d{1,2})日'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                info['date'] = match.group(0)
                break
        
        # 提取地点
        location_keywords = ['in ', 'at ', 'held in ', 'venue:', 'location:', '地点:', '地址:']
        for kw in location_keywords:
            idx = text.lower().find(kw)
            if idx != -1:
                end_idx = text.find('.', idx)
                if end_idx == -1:
                    end_idx = text.find('\n', idx)
                if end_idx == -1:
                    end_idx = idx + 100
                info['location'] = text[idx + len(kw):end_idx].strip()[:100]
                break
        
        # 提取网站
        url_pattern = r'https?://[^\s<>"\'\)]+'
        urls = re.findall(url_pattern, text)
        if urls:
            info['website'] = urls[0]
        
        return info
    
    def get_stats(self) -> Dict:
        """获取分类统计"""
        return dict(self.stats)
    
    def print_stats(self):
        """打印分类统计"""
        print("\n   📊 Classification Statistics:")
        print(f"      ✅ Classified: {self.stats['classified']} articles")
        print(f"      ❌ Rejected: {self.stats['rejected']} articles")
        print(f"      🚫 Filtered (irrelevant): {self.stats['filtered_irrelevant']} articles")
        print("")
        print("      📂 By Topic:")
        topic_names = {1: 'T1-竞品', 2: 'T2-技术', 3: 'T3-制造', 4: 'T4-展会', 5: 'T5-供应链'}
        for topic_id in range(1, 6):
            count = self.stats['by_topic'][topic_id]
            name = topic_names.get(topic_id, f'T{topic_id}')
            bar = '█' * min(30, count // 2) if count > 0 else ''
            print(f"         {name:12}: {count:3} articles {bar}")
        
        if self.stats['by_category']:
            print("")
            print("      🏷️ By Product Category:")
            for category, count in self.stats['by_category'].items():
                print(f"         [{category}]: {count} articles")
    
    def reset_stats(self):
        """重置统计"""
        self.stats = {
            'classified': 0,
            'rejected': 0,
            'filtered_irrelevant': 0,
            'by_topic': defaultdict(int),
            'by_category': defaultdict(int)
        }
