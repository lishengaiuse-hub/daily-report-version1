#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for CE Intelligence
Version: 7.0 - 全新四分类体系（按Topic structure.docx规范）

Topic 1: Consumer electronics manufacturing expansion in SEA (existing facility)
Topic 2: New factory/plant construction in SEA
Topic 3: Major product announcements (mobile / home appliance) — High/Med/Low
Topic 4: New technology / materials (CE-linked) — High/Med/Low
"""

import re
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict


class TopicClassifier:
    """
    四分类器 - Topic1/Topic2/Topic3/Topic4

    分类规则：
    - T1: SEA地区 + 消费电子 + 现有工厂扩产/产能增加（非新建）
    - T2: SEA地区 + 消费电子 + 新建工厂/新厂房宣布
    - T3: 手机/家电 + 产品发布（High=含型号 / Med=评测 / Low=价格）
    - T4: 新技术/新材料 + 消费电子应用（High=已确认OEM采用 / Med=已商业化 / Low=研发阶段）

    强制排除：半导体行业（非CE）/ 展会活动 / 汽车应用 / 软件生态 / 无产品主体新闻
    """

    # ──────────────────────────────────────────────
    # 地理约束 (T1/T2 强制)
    # ──────────────────────────────────────────────
    SEA_LOCATIONS = [
        "vietnam", "viet nam", "越南", "hanoi", "ho chi minh", "haiphong", "bac ninh", "thai nguyen",
        "thailand", "thai", "bangkok", "泰国", "曼谷", "rayong", "chonburi",
        "indonesia", "jakarta", "印尼", "雅加达", "batam", "karawang",
        "malaysia", "kuala lumpur", "penang", "马来西亚", "吉隆坡", "槟城", "selangor", "johor", "kulim",
        "singapore", "新加坡",
        "philippines", "manila", "菲律宾", "马尼拉",
        "india", "new delhi", "mumbai", "bangalore", "chennai", "noida", "gurugram", "hyderabad",
        "印度", "新德里", "孟买", "班加罗尔", "钦奈", "诺伊达",
        "bangladesh", "dhaka", "孟加拉", "达卡",
        "myanmar", "cambodia", "缅甸", "柬埔寨"
    ]

    # ──────────────────────────────────────────────
    # 消费电子行业 (T1/T2 强制)
    # ──────────────────────────────────────────────
    CE_INDUSTRY_KEYWORDS = [
        "consumer electronics", "消费电子", "home appliance", "家电",
        "smartphone", "手机", "mobile phone", "mobile device", "智能手机",
        "television", "tv ", " tv", "电视",
        "refrigerator", "fridge", "冰箱",
        "washing machine", "washer", "洗衣机",
        "air conditioner", "空调",
        "vacuum", "robot vacuum", "扫地机", "吸尘器",
        "laptop", "notebook", "笔记本",
        "tablet", "平板",
        "wearable", "smartwatch", "可穿戴", "智能手表",
        "earphone", "earbuds", "headphone", "耳机",
        "speaker", "soundbar", "音箱",
        "digital device", "数码产品",
        "phone assembly", "手机组装",
        "appliance manufacturing", "家电制造",
        "electronics assembly", "电子组装",
        "electronics manufacturing", "电子制造",
        "foxconn", "富士康", "pegatron", "wistron", "compal",  # 已知CE代工厂
        "boe", "lg display", "samsung display",  # 显示厂（CE关联）
        "iphone", "galaxy", "xiaomi", "huawei", "oppo", "vivo"
    ]

    # ──────────────────────────────────────────────
    # T1: 现有工厂扩产关键词（不包含新建）
    # ──────────────────────────────────────────────
    EXPANSION_KEYWORDS = [
        "expand", "expansion", "expanding", "扩产", "扩建", "扩大",
        "increase capacity", "additional capacity", "产能扩大", "产能增加",
        "boost production", "ramp up", "scale up", "产能提升",
        "invest in existing", "upgrade facility", "升级产线",
        "additional investment", "追加投资", "增资",
        "production ramp", "产能爬坡",
        "capacity increase", "capacity expansion",
        "add production line", "新增产线",
        "double capacity", "triple capacity", "产能翻倍"
    ]

    # T1 中需排除的"新建"特征词（有这些 → 应去 T2 而非 T1）
    NEW_FACTORY_INDICATORS = [
        "new factory", "new plant", "new facility", "new manufacturing",
        "groundbreaking", "break ground", "奠基", "开工", "新建", "新工厂",
        "construction of", "build a factory", "set up factory",
        "establish factory", "首个工厂", "新厂"
    ]

    # ──────────────────────────────────────────────
    # T2: 新建工厂关键词
    # ──────────────────────────────────────────────
    NEW_FACTORY_KEYWORDS = [
        "new factory", "new plant", "new facility", "新工厂", "新建工厂",
        "groundbreaking", "break ground", "奠基", "开工", "兴建",
        "construction of factory", "build factory", "建厂",
        "set up manufacturing", "establish manufacturing",
        "greenfield", "brand new factory", "first factory",
        "首个工厂", "首家工厂", "新产线", "新园区",
        "announce factory", "announce plant", "宣布建厂",
        "open factory", "开设工厂", "设立工厂"
    ]

    # ──────────────────────────────────────────────
    # T3: 产品类别（手机 + 家电）
    # ──────────────────────────────────────────────
    MOBILE_KEYWORDS = [
        "phone", "smartphone", "mobile", "handset", "iphone", "galaxy",
        "foldable", "flip phone", "flip phone", "fold",
        "手机", "智能手机", "折叠屏", "折叠手机", "旗舰机"
    ]

    HOME_APPLIANCE_KEYWORDS = [
        "tv", "television", "qled", "oled tv", "mini-led tv", "microled tv",
        "refrigerator", "fridge", "冰箱",
        "washing machine", "washer", "dryer", "洗衣机", "烘干机",
        "air conditioner", "air purifier", "空调", "净化器",
        "vacuum", "robot vacuum", "扫地机器人", "吸尘器",
        "dishwasher", "洗碗机",
        "home appliance", "家电",
        "soundbar", "speaker", "音箱", "回音壁",
        "smartwatch", "smart watch", "智能手表",
        "earbuds", "earphone", "headphone", "耳机",
        "tablet", "平板电脑",
        "laptop", "notebook", "笔记本电脑",
        "monitor", "显示器"
    ]

    # T3 产品发布关键词
    LAUNCH_KEYWORDS = [
        "launch", "announce", "release", "unveil", "debut", "introduce",
        "goes on sale", "available", "ships", "shipping", "officially",
        "发布", "推出", "上市", "发售", "亮相", "首发", "宣布",
        "开售", "正式发布", "曝光", "渲染图", "renders", "leaked", "泄露",
        "confirmed", "specs confirmed", "规格确认", "确认搭载"
    ]

    # T3 评测关键词 (→ Med Priority)
    REVIEW_KEYWORDS = [
        "review", "hands-on", "tested", "testing", "benchmark", "comparison",
        "评测", "体验", "测试", "对比", "实测", "拆解", "深度评测"
    ]

    # T3 价格关键词 (→ Low Priority)
    PRICING_KEYWORDS = [
        "price", "pricing", "cost", "starting at", "starts at", "available for",
        "discount", "deal", "sale", "msrp",
        "价格", "售价", "定价", "元起", "美元起", "降价", "优惠", "补贴", "到手价"
    ]

    # 产品型号正则（T3 High 判断依据）
    PRODUCT_MODEL_PATTERNS = [
        r'\b[A-Z]\d+\s*[A-Za-z]*\b',         # S25, A16, X9, K90
        r'\b\w+\s+\d+[A-Za-z]*\s*(Pro|Ultra|Plus|Max|SE|Lite|Mini)\b',  # Galaxy S25 Ultra
        r'\b(iPhone|iPad|Xperia|REDMI|Redmi|MagicPad|Razr|ZenBook|ROG)\s+[\w\s]+\b',
        r'[A-Z][a-z]+\s+\d{1,4}[A-Za-z]*',  # Mate 70, Nova 13
        r'[一-鿿]{2,4}\s*\d+[A-Za-z]*',  # 麒麟9030S, 天玑9400
        r'\b\w+\s+[\w]+\s+(2025|2026|2027)\b'  # Model Year
    ]

    # ──────────────────────────────────────────────
    # T4: 技术/材料关键词
    # ──────────────────────────────────────────────
    TECH_MATERIAL_KEYWORDS = {
        "display": [
            "microled", "micro-led", "micro led", "miniled", "mini-led", "mini led",
            "amoled", "qd-oled", "oled panel", "micro oled", "transparent display",
            "flexible display", "foldable display", "rollable display",
            "量子点", "microled显示", "柔性显示", "卷曲显示", "透明显示"
        ],
        "battery": [
            "solid state battery", "solid-state battery", "silicon anode",
            "energy density", "fast charging technology", "wireless charging tech",
            "silicon carbon battery",
            "固态电池", "硅负极", "能量密度", "快充技术", "无线充电技术", "硅碳电池"
        ],
        "material": [
            "graphene", "carbon nanotube", "perovskite", "gallium nitride", "gan material",
            "silicon carbide material", "sic material", "titanium alloy", "ceramic material",
            "新材料", "石墨烯", "碳纳米管", "钙钛矿", "氮化镓材料", "碳化硅材料", "钛合金"
        ],
        "thermal": [
            "vapor chamber", "heat pipe", "graphite sheet", "thermal interface material",
            "均热板", "热管", "石墨散热", "导热材料"
        ],
        "sensor": [
            "under-display camera", "under display fingerprint", "ultrasonic fingerprint",
            "3d sensing", "tof sensor", "lidar for phone",
            "屏下摄像头", "屏下指纹", "超声波指纹", "3D传感", "飞行时间传感器"
        ],
        "ai_hardware": [
            "on-device ai chip", "mobile npu", "phone ai processor", "appliance ai chip",
            "端侧AI芯片", "手机AI芯片", "家电AI处理器"
        ]
    }

    # T4 High: OEM已确认采用的关键词
    T4_HIGH_KEYWORDS = [
        "confirmed", "adopted", "integrated into", "used in", "equipped with",
        "to be used", "will feature", "announced for",
        "confirmed for", "designed for", "built into",
        "确认采用", "搭载", "已量产", "首发", "用于", "配备", "内置",
        "供应给", "已应用于", "已用于"
    ]

    # T4 Med: 已商业化可用的关键词
    T4_MED_KEYWORDS = [
        "commercialized", "available", "mass production", "mass produced",
        "now shipping", "in production", "launched",
        "已商业化", "已量产", "量产", "商用", "可供", "已上市"
    ]

    # ──────────────────────────────────────────────
    # 强制排除关键词（命中即丢弃整条新闻）
    # ──────────────────────────────────────────────
    HARD_EXCLUDE_KEYWORDS = [
        # 半导体行业（非CE产品）
        "semiconductor fab", "wafer fab", "chip fab", "foundry capacity", "foundry expansion",
        "semiconductor manufacturing plant", "chip manufacturing",
        "semiconductor industry", "chip industry", "semiconductor sector",
        "semiconductor supply chain", "chip supply chain",
        "advanced packaging", "cowos", "3d-ic", "heterogeneous integration",
        "semiconductor equipment", "chip equipment", "etching equipment", "lithography",
        "semiconductor test", "wafer test", "chip test",
        "eda tool", "pcb design tool", "chip design tool",
        "llm inference chip", "ai accelerator chip", "ai training chip",
        "hpc chip", "data center chip", "server chip",
        "semiconductor climate", "semi foundation", "semiconductor association",
        "chip sovereignty", "semiconductor policy", "chip act",
        "semiconductor talent", "chip talent", "semiconductor workforce",
        "silicon photonics", "plasma photonics",
        "芯片行业", "半导体行业", "半导体产业", "晶圆厂", "芯片制造厂",
        "半导体制造", "封装厂", "先进封装", "异构集成",
        "宽禁带半导体", "半导体设备", "光刻", "刻蚀设备",
        "半导体测试", "EDA工具", "芯片设计工具",
        "AI训练芯片", "AI加速器", "数据中心芯片", "服务器芯片",
        "半导体主权", "芯片法案", "半导体协会", "SEMI基金",
        "芯片人才", "半导体人才",
        # 论坛/路演/展览（非CE）
        "路演", "项目路演", "investor pitch", "startup pitch",
        "semiconductor conference", "chip conference", "semi exhibition",
        "半导体展览", "芯片展览",
        # 汽车/非CE应用
        "automotive chip", "car chip", "vehicle semiconductor",
        "自动驾驶芯片", "车规芯片", "汽车半导体",
        # 纯软件/AI生态
        "llm model", "foundation model", "large language model",
        "ai platform", "ai ecosystem", "generative ai platform",
        # 人员变动/协会新闻（无产品）
        "elected president", "new ceo", "appoints ceo", "board member",
        "当选主席", "当选会长",
    ]

    # 需要业务相关关键词（至少命中一个才保留）
    CE_RELEVANCE_KEYWORDS = [
        "phone", "smartphone", "mobile", "handset",
        "tv", "television", "home appliance", "refrigerator", "washer", "vacuum",
        "consumer electronics", "laptop", "tablet", "wearable", "smartwatch",
        "手机", "智能手机", "电视", "家电", "冰箱", "洗衣机", "吸尘器", "消费电子",
        "笔记本", "平板", "可穿戴", "智能手表",
        "iphone", "galaxy", "pixel", "xiaomi", "huawei", "oppo", "vivo", "honor",
        "小米", "华为", "荣耀", "apple", "苹果",
        "foxconn", "富士康", "pegatron", "display panel", "面板",
        "oled", "microled", "miniled",
        "battery", "电池", "solid state"
    ]

    # 跨栏目去重优先级 (T1 最高)
    TOPIC_PRIORITY = {1: 4, 2: 3, 3: 2, 4: 1}

    def __init__(self, topics_config: Dict = None):
        self.config = topics_config or {}
        self.stats = {
            "total_input": 0,
            "classified": 0,
            "rejected": 0,
            "filtered_irrelevant": 0,
            "filtered_semiconductor": 0,
            "by_topic": defaultdict(int),
            "by_priority": defaultdict(int)
        }

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def is_relevant(self, title: str, content: str = "") -> bool:
        """双重过滤：强制排除半导体行业新闻 + CE相关性检查"""
        text = (title + " " + content).lower()

        # 1. 硬排除（命中即丢）
        for kw in self.HARD_EXCLUDE_KEYWORDS:
            if kw.lower() in text:
                self.stats["filtered_semiconductor"] += 1
                return False

        # 2. CE相关性（至少命中一个）
        return any(kw.lower() in text for kw in self.CE_RELEVANCE_KEYWORDS)

    def classify(self, title: str, content: str = "") -> List[int]:
        """
        严格分类，返回 topic id 列表（单一归属已由 cross_topic_deduplicate 确保）。
        同时设置优先级字段到对象外部（通过返回后由调用方写入 article）。
        """
        self.stats["total_input"] += 1

        if not self.is_relevant(title, content):
            self.stats["filtered_irrelevant"] += 1
            return []

        text = (title + " " + content).lower()
        topics = []

        # T1: SEA 现有工厂扩产
        if self._check_t1(text):
            topics.append(1)
            self.stats["by_topic"][1] += 1

        # T2: SEA 新建工厂（T1 已匹配则跳过）
        if 1 not in topics and self._check_t2(text):
            topics.append(2)
            self.stats["by_topic"][2] += 1

        # T3: 产品发布
        t3_ok, t3_priority = self._check_t3(title, text)
        if t3_ok:
            topics.append(3)
            self.stats["by_topic"][3] += 1
            self.stats["by_priority"][f"t3_{t3_priority}"] += 1

        # T4: 新技术/材料（T3 已匹配则跳过 High，避免重叠）
        t4_ok, t4_priority = self._check_t4(text)
        if t4_ok and 3 not in topics:
            topics.append(4)
            self.stats["by_topic"][4] += 1
            self.stats["by_priority"][f"t4_{t4_priority}"] += 1

        if topics:
            self.stats["classified"] += 1
        else:
            self.stats["rejected"] += 1

        return topics

    def get_t3_priority(self, title: str, content: str = "") -> str:
        """获取 T3 优先级: high / med / low"""
        _, priority = self._check_t3(title, (title + " " + content).lower())
        return priority or "low"

    def get_t4_priority(self, title: str, content: str = "") -> str:
        """获取 T4 优先级: high / med / low"""
        _, priority = self._check_t4((title + " " + content).lower())
        return priority or "low"

    def get_product_category(self, title: str, content: str = "") -> str:
        """获取 T3 产品类别标签"""
        text = (title + " " + content).lower()
        if any(kw in text for kw in self.MOBILE_KEYWORDS):
            return "手机"
        if any(kw in text for kw in self.HOME_APPLIANCE_KEYWORDS):
            return "家电"
        return "数码"

    def cross_topic_deduplicate(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
        """
        跨栏目去重：同一新闻只保留优先级最高的 Topic（单一归属原则）。
        同时将 article["topics"] 更新为单一 topic。
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
                article["topics"] = [topic_id]
                result[topic_id].append(article)

        after_total = sum(len(a) for a in result.values())
        print(f"   🔄 Cross-topic dedup: {before_total} → {after_total} (removed {before_total - after_total})")
        return result

    def semantic_deduplicate(self, articles: List[Dict]) -> Tuple[List[Dict], int]:
        """
        语义级去重：删除描述同一事件的重复新闻（Jaccard 相似度 ≥ 0.55）。
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
            return len(s1 & s2) / len(s1 | s2)

        kept: List[Dict] = []
        removed = 0
        token_cache: List[set] = []

        for article in articles:
            tokens = tokenize(article.get("title", "") + " " + article.get("summary", "")[:200])
            is_dup = any(jaccard(tokens, ec) >= SIMILARITY_THRESHOLD for ec in token_cache)
            if is_dup:
                removed += 1
            else:
                kept.append(article)
                token_cache.append(tokens)

        return kept, removed

    # ------------------------------------------------------------------
    # 内部分类逻辑
    # ------------------------------------------------------------------

    def _check_t1(self, text: str) -> bool:
        """T1: SEA 现有工厂扩产（非新建）"""
        if not any(loc.lower() in text for loc in self.SEA_LOCATIONS):
            return False
        if not any(kw.lower() in text for kw in self.CE_INDUSTRY_KEYWORDS):
            return False
        if not any(kw.lower() in text for kw in self.EXPANSION_KEYWORDS):
            return False
        # 有新建特征词 → 应归 T2
        if any(kw.lower() in text for kw in self.NEW_FACTORY_INDICATORS):
            return False
        return True

    def _check_t2(self, text: str) -> bool:
        """T2: SEA 新建工厂"""
        if not any(loc.lower() in text for loc in self.SEA_LOCATIONS):
            return False
        if not any(kw.lower() in text for kw in self.CE_INDUSTRY_KEYWORDS):
            return False
        return any(kw.lower() in text for kw in self.NEW_FACTORY_KEYWORDS)

    def _check_t3(self, title: str, text: str) -> Tuple[bool, str]:
        """
        T3: 手机/家电产品发布。
        返回 (是否匹配, 优先级 high/med/low)
        """
        has_mobile  = any(kw.lower() in text for kw in self.MOBILE_KEYWORDS)
        has_appliance = any(kw.lower() in text for kw in self.HOME_APPLIANCE_KEYWORDS)

        if not (has_mobile or has_appliance):
            return False, ""

        has_launch  = any(kw.lower() in text for kw in self.LAUNCH_KEYWORDS)
        has_review  = any(kw.lower() in text for kw in self.REVIEW_KEYWORDS)
        has_pricing = any(kw.lower() in text for kw in self.PRICING_KEYWORDS)

        if not (has_launch or has_review or has_pricing):
            return False, ""

        # 优先级判断
        if has_launch and self._has_product_model(title + " " + text):
            return True, "high"
        if has_review:
            return True, "med"
        if has_pricing:
            return True, "low"
        # 有发布但无明确型号 → low
        return True, "low"

    def _check_t4(self, text: str) -> Tuple[bool, str]:
        """
        T4: 消费电子相关新技术/材料。
        返回 (是否匹配, 优先级 high/med/low)
        """
        has_tech = False
        for keywords in self.TECH_MATERIAL_KEYWORDS.values():
            if any(kw.lower() in text for kw in keywords):
                has_tech = True
                break

        if not has_tech:
            return False, ""

        # 必须有 CE 应用链接（手机或家电）
        has_ce_link = (
            any(kw.lower() in text for kw in self.MOBILE_KEYWORDS) or
            any(kw.lower() in text for kw in self.HOME_APPLIANCE_KEYWORDS)
        )
        if not has_ce_link:
            return False, ""

        # 优先级
        if any(kw.lower() in text for kw in self.T4_HIGH_KEYWORDS):
            return True, "high"
        if any(kw.lower() in text for kw in self.T4_MED_KEYWORDS):
            return True, "med"
        return True, "low"

    def _has_product_model(self, text: str) -> bool:
        """检测文本中是否含有明确的产品型号"""
        for pattern in self.PRODUCT_MODEL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return dict(self.stats)

    def print_stats(self):
        print("\n   📊 Classification Statistics:")
        print(f"      Input              : {self.stats['total_input']}")
        print(f"      ✅ Classified      : {self.stats['classified']}")
        print(f"      ❌ Rejected        : {self.stats['rejected']}")
        print(f"      🚫 Irrelevant      : {self.stats['filtered_irrelevant']}")
        print(f"      🚫 Semiconductor   : {self.stats['filtered_semiconductor']}")
        topic_names = {1: "T1-SEA扩产", 2: "T2-新建厂", 3: "T3-产品发布", 4: "T4-新技术"}
        for tid in range(1, 5):
            count = self.stats["by_topic"][tid]
            print(f"      {topic_names[tid]:12}: {count:3} articles")
        for pk, pv in self.stats["by_priority"].items():
            print(f"      [{pk}]: {pv}")

    def reset_stats(self):
        self.stats = {
            "total_input": 0, "classified": 0, "rejected": 0,
            "filtered_irrelevant": 0, "filtered_semiconductor": 0,
            "by_topic": defaultdict(int), "by_priority": defaultdict(int)
        }
