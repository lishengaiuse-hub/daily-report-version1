#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for Samsung CE Intelligence
Version: 5.0 - T1-T4严格分类 + 三星强相关过滤 + 跨栏目去重
"""

import re
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict


class TopicClassifier:
    """
    严格分类器 - T1/T2/T3/T4

    分类规则：
    - T1: 竞品动态 — 必须包含竞品品牌 + 产品类别标签 [手机/家电/芯片/显示]
    - T2: 新技术/材料 — 半导体/显示/电池/材料/AI底层，排除品牌竞争
    - T3: 制造(SEA/India) — 东南亚/印度 + 三星供应商/潜在供应商/竞品建厂
    - T4: 展会 — 展会名称 + 与家电/手机相关

    跨栏目去重优先级: T1 > T2 > T3 > T4
    """

    # T1: 竞品品牌（必须包含其中之一）
    COMPETITOR_BRANDS = [
        "apple", "苹果", "xiaomi", "小米", "huawei", "华为",
        "oppo", "vivo", "lg", "sony", "索尼", "haier", "海尔",
        "hisense", "海信", "tcl", "gree", "格力", "midea", "美的",
        "panasonic", "松下", "philips", "飞利浦", "sharp", "夏普",
        "lenovo", "联想", "honor", "荣耀", "roborock", "石头", "dreame", "追觅",
        "transsion", "传音", "asus", "华硕", "pixel"
    ]

    # T1: 产品类别标签映射
    PRODUCT_CATEGORIES = {
        "手机": [
            "phone", "smartphone", "iphone", "foldable", "flip", "fold",
            "折叠屏", "手机", "智能手机", "mobile", "handset"
        ],
        "家电": [
            "tv", "television", "refrigerator", "fridge", "washing machine",
            "washer", "air conditioner", "vacuum", "robot vacuum", "dryer",
            "电视", "冰箱", "洗衣机", "空调", "扫地机器人", "吸尘器", "烘干机", "家电"
        ],
        "芯片": [
            "chip", "soc", "processor", "cpu", "gpu", "tensor", "snapdragon",
            "dimensity", "kirin", "骁龙", "天玑", "麒麟", "芯片", "处理器"
        ],
        "显示": [
            "display", "panel", "oled", "microled", "miniled", "qled",
            "screen", "monitor", "显示", "面板", "屏幕", "显示器"
        ]
    }

    # T1: 竞争动态关键词（必须命中至少一个）
    COMPETITION_KEYWORDS = [
        "launch", "release", "announce", "unveil", "introduce", "debut",
        "ship", "price", "compete", "rival", "beat", "overtake",
        "发布", "上市", "推出", "亮相", "宣布", "首发", "开售", "价格",
        "竞争", "超越", "击败", "降价", "涨价"
    ]

    # T2: 技术/材料关键词
    TECH_KEYWORDS = {
        "semiconductor": [
            "semiconductor", "wafer", "foundry", "lithography", "etch",
            "制程", "晶圆", "半导体", "光刻", "蚀刻"
        ],
        "display": [
            "microled", "miniled", "amoled", "quantum dot", "micro oled",
            "panel process", "量子点", "微型led", "微显示"
        ],
        "battery": [
            "solid state battery", "solid-state battery", "energy density",
            "silicon anode", "固态电池", "能量密度", "硅负极"
        ],
        "material": [
            "graphene", "carbon nanotube", "perovskite", "gallium nitride", "gan",
            "silicon carbide", "sic", "cmf", "石墨烯", "碳纳米管", "钙钛矿", "氮化镓"
        ],
        "ai_core": [
            "neural processing unit", "npu", "on-device ai", "edge ai",
            "ai chip", "foundation model", "inference engine",
            "端侧ai", "神经处理器", "大模型", "推理引擎"
        ],
        "thermal": [
            "thermal interface", "heat pipe", "vapor chamber", "graphite sheet",
            "热界面", "热管", "均热板", "石墨散热"
        ]
    }

    # T3: 东南亚/印度地点
    SEA_LOCATIONS = {
        "vietnam": ["vietnam", "viet nam", "越南", "hanoi", "ho chi minh", "haiphong", "bac ninh", "thai nguyen"],
        "thailand": ["thailand", "thai", "bangkok", "泰国", "曼谷"],
        "indonesia": ["indonesia", "jakarta", "印尼", "雅加达"],
        "malaysia": ["malaysia", "kuala lumpur", "penang", "马来西亚", "吉隆坡", "槟城"],
        "singapore": ["singapore", "新加坡"],
        "philippines": ["philippines", "manila", "菲律宾", "马尼拉"],
        "india": ["india", "new delhi", "mumbai", "bangalore", "chennai", "noida",
                  "印度", "新德里", "孟买", "班加罗尔", "钦奈"],
        "bangladesh": ["bangladesh", "dhaka", "孟加拉", "达卡"]
    }

    MANUFACTURING_KEYWORDS = [
        "factory", "plant", "facility", "production line", "assembly",
        "manufacturing", "investment", "invest", "expansion", "expand",
        "capacity", "relocation", "relocate", "setup", "establish",
        "工厂", "产线", "组装", "生产", "制造", "投资", "扩产", "建厂", "迁移", "落地"
    ]

    # T3: 必须与供应商/三星/竞品相关（防止无关制造新闻混入）
    SUPPLIER_RELEVANCE_KEYWORDS = [
        "supplier", "supply chain", "component", "partner", "vendor",
        "samsung", "三星", "apple", "xiaomi", "huawei", "oppo", "vivo",
        "供应商", "供应链", "零部件", "合作伙伴",
        "foxconn", "富士康", "boe", "京东方", "csot", "lg display", "samsung display",
        "qualcomm", "mediatek", "sk hynix", "micron", "tsmc",
        "flex", "jabil", "pegatron", "wistron", "compal"
    ]

    # T4: 展会名称
    EXHIBITION_NAMES = {
        "ces": ["ces", "consumer electronics show"],
        "ifa": ["ifa berlin", "ifa 2", " ifa "],
        "mwc": ["mwc", "mobile world congress"],
        "computex": ["computex"],
        "awe": ["awe", "中国家电博览会", "家电博览会"],
        "display_week": ["display week", "sid display"],
        "gitex": ["gitex"],
        "touch_taiwan": ["touch taiwan"],
        "hkef": ["hong kong electronics fair", "香港电子展"],
        "ces_asia": ["ces asia"]
    }

    # 三星业务强相关关键词（至少命中一个才保留）
    SAMSUNG_RELEVANCE_KEYWORDS = [
        "samsung", "三星",
        "apple", "xiaomi", "huawei", "oppo", "vivo", "lg", "sony", "tcl", "hisense",
        "苹果", "小米", "华为", "海信", "索尼", "格力", "美的", "海尔",
        "smartphone", "foldable", "tv", "television", "oled", "qled", "microled",
        "semiconductor", "memory", "dram", "nand", "display panel",
        "consumer electronics", "home appliance",
        "手机", "折叠屏", "电视", "半导体", "内存", "显示面板", "家电",
        "foundry", "wafer", "chip", "晶圆", "芯片",
        "ces", "ifa", "mwc", "awe",
        "vietnam", "thailand", "india", "越南", "泰国", "印度"
    ]

    # 强制排除（命中即丢弃）
    IRRELEVANT_KEYWORDS = [
        "hotel booking", "airbnb", "restaurant review", "food delivery",
        "furniture store", "real estate listing", "mortgage rate",
        "bitcoin price", "crypto trading", "nft mint", "defi protocol",
        "sports score", "football match", "basketball game",
        "movie premiere", "celebrity scandal",
        "clinical trial", "vaccine approval", "drug recall",
        "酒店预订", "美食餐厅", "房产中介", "加密货币行情",
        "娱乐明星", "综艺节目", "体育赛事", "药品审批"
    ]

    # 跨栏目去重优先级
    TOPIC_PRIORITY = {1: 4, 2: 3, 3: 2, 4: 1}

    def __init__(self, topics_config: Dict = None):
        self.config = topics_config or {}
        self.stats = {
            "total_input": 0,
            "classified": 0,
            "rejected": 0,
            "filtered_irrelevant": 0,
            "by_topic": defaultdict(int),
            "by_category": defaultdict(int)
        }

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def is_relevant(self, title: str, content: str = "") -> bool:
        """三星业务强相关性检查：命中排除词→丢弃；未命中相关词→丢弃"""
        text = (title + " " + content).lower()
        for kw in self.IRRELEVANT_KEYWORDS:
            if kw.lower() in text:
                return False
        return any(kw.lower() in text for kw in self.SAMSUNG_RELEVANCE_KEYWORDS)

    def classify(self, title: str, content: str = "") -> List[int]:
        """
        严格分类，返回 T1-T4 中符合规则的 topic id 列表。
        调用方应再执行 cross_topic_deduplicate 以确保每条新闻只在一个栏目出现。
        """
        self.stats["total_input"] += 1

        if not self.is_relevant(title, content):
            self.stats["filtered_irrelevant"] += 1
            return []

        text = (title + " " + content).lower()
        title_lower = title.lower()
        topics = []

        # T1: 竞品动态
        t1_ok, category = self._check_t1(title_lower, text)
        if t1_ok:
            self.stats["by_category"][category] += 1
            topics.append(1)
            self.stats["by_topic"][1] += 1

        # T2: 新技术/材料（已为T1则跳过）
        if self._check_t2(text, has_t1=1 in topics):
            topics.append(2)
            self.stats["by_topic"][2] += 1

        # T3: 制造（SEA/India）
        if self._check_t3(text):
            topics.append(3)
            self.stats["by_topic"][3] += 1

        # T4: 展会
        if self._check_t4(text):
            topics.append(4)
            self.stats["by_topic"][4] += 1

        if topics:
            self.stats["classified"] += 1
        else:
            self.stats["rejected"] += 1

        return topics

    def get_product_category(self, title: str, content: str = "") -> str:
        """获取 T1 产品类别标签"""
        combined = (title + " " + content).lower()
        for category, keywords in self.PRODUCT_CATEGORIES.items():
            if any(kw.lower() in combined for kw in keywords):
                return category
        return "产品"

    def cross_topic_deduplicate(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
        """
        跨栏目去重：同一新闻只保留优先级最高的 Topic（单一归属原则）。
        优先级: T1(4) > T2(3) > T3(2) > T4(1)
        同时将 article["topics"] 更新为单一 topic，确保单一归属。
        """
        fingerprint_map: Dict[str, Tuple] = {}
        before_total = sum(len(a) for a in articles_by_topic.values())

        for topic_id, articles in articles_by_topic.items():
            priority = self.TOPIC_PRIORITY.get(topic_id, 0)
            for article in articles:
                url   = article.get("link", article.get("url", ""))
                title = article.get("title", "")[:50]
                body  = article.get("summary", article.get("content", ""))[:100]
                fp = hashlib.md5((url + "|" + title + "|" + body).encode("utf-8")).hexdigest()
                if fp not in fingerprint_map or priority > fingerprint_map[fp][2]:
                    fingerprint_map[fp] = (topic_id, article, priority)

        result: Dict[int, List[Dict]] = {1: [], 2: [], 3: [], 4: []}
        for fp, (topic_id, article, _) in fingerprint_map.items():
            if topic_id in result:
                # 强制单一归属：覆盖 topics 字段
                article["topics"] = [topic_id]
                result[topic_id].append(article)

        after_total = sum(len(a) for a in result.values())
        print(f"   🔄 Cross-topic dedup: {before_total} → {after_total} (removed {before_total - after_total})")
        return result

    def semantic_deduplicate(self, articles: List[Dict]) -> Tuple[List[Dict], int]:
        """
        语义级去重：删除描述同一事件的重复新闻（即使表述不同）。
        使用标题关键词 Jaccard 相似度，阈值 0.55。
        返回 (去重后列表, 删除数量)
        """
        SIMILARITY_THRESHOLD = 0.55

        def tokenize(text: str) -> set:
            text = re.sub(r"[^\w\s]", " ", text.lower())
            tokens = set(text.split())
            stopwords = {"the", "a", "an", "is", "in", "of", "and", "to", "for",
                         "on", "at", "by", "with", "as", "its", "it", "are", "be",
                         "has", "will", "that", "this", "from", "was"}
            return tokens - stopwords

        def jaccard(s1: set, s2: set) -> float:
            if not s1 or not s2:
                return 0.0
            intersection = len(s1 & s2)
            union = len(s1 | s2)
            return intersection / union if union else 0.0

        kept: List[Dict] = []
        removed = 0
        token_cache: List[set] = []

        for article in articles:
            title = article.get("title", "")
            summary = article.get("summary", "")[:200]
            tokens = tokenize(title + " " + summary)

            is_duplicate = False
            for existing_tokens in token_cache:
                if jaccard(tokens, existing_tokens) >= SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    break

            if is_duplicate:
                removed += 1
            else:
                kept.append(article)
                token_cache.append(tokens)

        return kept, removed

    # ------------------------------------------------------------------
    # 内部分类逻辑
    # ------------------------------------------------------------------

    def _check_t1(self, title_lower: str, text: str) -> Tuple[bool, str]:
        """T1: 竞品品牌 AND 产品类别 AND 竞争动态"""
        if not any(b.lower() in text for b in self.COMPETITOR_BRANDS):
            return False, ""
        category = ""
        for cat, keywords in self.PRODUCT_CATEGORIES.items():
            if any(kw.lower() in text for kw in keywords):
                category = cat
                break
        if not category:
            return False, ""
        if not any(kw.lower() in text for kw in self.COMPETITION_KEYWORDS):
            return False, ""
        return True, category

    def _check_t2(self, text: str, has_t1: bool = False) -> bool:
        """T2: 技术/材料，且不是品牌竞争内容"""
        if has_t1:
            return False
        for keywords in self.TECH_KEYWORDS.values():
            if any(kw.lower() in text for kw in keywords):
                is_commercial = (
                    any(b.lower() in text for b in self.COMPETITOR_BRANDS) and
                    any(kw.lower() in text for kw in self.COMPETITION_KEYWORDS)
                )
                if not is_commercial:
                    return True
        return False

    def _check_t3(self, text: str) -> bool:
        """T3: 东南亚/印度地点 AND 制造关键词 AND 供应商相关"""
        has_location = any(kw.lower() in text for locs in self.SEA_LOCATIONS.values() for kw in locs)
        if not has_location:
            return False
        if not any(kw.lower() in text for kw in self.MANUFACTURING_KEYWORDS):
            return False
        return any(kw.lower() in text for kw in self.SUPPLIER_RELEVANCE_KEYWORDS)

    def _check_t4(self, text: str) -> bool:
        """T4: 包含已知展会名称"""
        return any(kw.lower() in text for names in self.EXHIBITION_NAMES.values() for kw in names)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def extract_exhibition_info(self, text: str) -> Dict[str, str]:
        """从文本提取展会信息（名称/时间/地点/链接）"""
        info = {"name": "", "date": "", "location": "", "website": ""}
        for cat, keywords in self.EXHIBITION_NAMES.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    info["name"] = kw.strip().upper()
                    break
            if info["name"]:
                break
        for pattern in [r"\d{4}-\d{1,2}-\d{1,2}", r"\d{4}年\d{1,2}月\d{1,2}日", r"\d{1,2}/\d{1,2}/\d{4}"]:
            m = re.search(pattern, text)
            if m:
                info["date"] = m.group(0)
                break
        for kw in ["in ", "at ", "held in ", "地点：", "举办地："]:
            idx = text.lower().find(kw.lower())
            if idx != -1:
                end = text.find(".", idx)
                if end == -1:
                    end = text.find("\n", idx)
                if end == -1:
                    end = idx + 80
                info["location"] = text[idx + len(kw):end].strip()[:80]
                break
        urls = re.findall(r"https?://[^\s<>\"\'\\)]+", text)
        if urls:
            info["website"] = urls[0]
        return info

    def get_stats(self) -> Dict:
        return dict(self.stats)

    def print_stats(self):
        print("\n   📊 Classification Statistics:")
        print(f"      Input          : {self.stats['total_input']}")
        print(f"      ✅ Classified  : {self.stats['classified']}")
        print(f"      ❌ Rejected    : {self.stats['rejected']}")
        print(f"      🚫 Irrelevant  : {self.stats['filtered_irrelevant']}")
        topic_names = {1: "T1-竞品", 2: "T2-技术", 3: "T3-制造", 4: "T4-展会"}
        for tid in range(1, 5):
            count = self.stats["by_topic"][tid]
            print(f"      {topic_names[tid]:10}: {count:3} articles")
        if self.stats["by_category"]:
            for cat, cnt in self.stats["by_category"].items():
                print(f"      [{cat}]: {cnt}")

    def reset_stats(self):
        self.stats = {
            "total_input": 0, "classified": 0, "rejected": 0,
            "filtered_irrelevant": 0,
            "by_topic": defaultdict(int),
            "by_category": defaultdict(int)
        }
