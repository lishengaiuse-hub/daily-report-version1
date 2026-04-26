#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Topic Classifier for CE Intelligence
Version: 7.1 - 严格规则重构（消除误报 / 强化T3-T4 / 增加验证层）

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
        "earphone", "earbuds", "headphone", "airpods", "耳机",
        "speaker", "soundbar", "音箱",
        "digital device", "数码产品",
        "phone assembly", "手机组装",
        "appliance manufacturing", "家电制造",
        "electronics assembly", "电子组装",
        "electronics manufacturing", "电子制造",
        # 已知CE代工厂 / OEM品牌（品牌名本身即代表CE相关）
        "foxconn", "富士康", "pegatron", "wistron", "compal", "luxshare",
        "boe", "lg display", "samsung display", "csot", "tianma",
        "apple", "google", "microsoft",   # 主要CE OEM
        "iphone", "galaxy", "pixel", "surface",
        "xiaomi", "huawei", "oppo", "vivo", "honor",
        # 组件/供应链（CE专属）
        "display panel", "面板", "oled panel", "touch panel",
        "camera module", "battery pack", "phone battery"
    ]

    # ──────────────────────────────────────────────
    # T1: 现有工厂扩产关键词（不包含新建）
    # ──────────────────────────────────────────────
    EXPANSION_KEYWORDS = [
        # EN — explicit expansion
        "expand", "expansion", "expanding", "expanded",
        "increase capacity", "additional capacity", "capacity increase", "capacity expansion",
        "boost production", "boost capacity",
        "ramp up", "ramp up production", "ramps up", "ramping up",
        "scale up", "scale up production", "scale production",
        "scales up", "scaling up", "stepped up", "step up production",
        "accelerates investment", "accelerate production", "accelerating investment",
        "invest in existing", "additional investment", "increasing investment",
        "upgrade facility", "upgrade production",
        "add production line", "add assembly line",
        "double capacity", "triple capacity", "lift production",
        "increase output", "higher output", "increase allocation",
        "strengthens presence", "deepens investment",
        # CN
        "扩产", "扩建", "扩大", "产能扩大", "产能增加", "产能提升",
        "追加投资", "增资", "扩大投资", "加大投资",
        "产能爬坡", "新增产线", "产能翻倍", "增加产线",
        "提升产能", "加速投资", "深化投资"
    ]

    # T1 中需排除的"新建"特征词（有这些 → 应去 T2 而非 T1）
    NEW_FACTORY_INDICATORS = [
        "new factory", "new plant", "new facility", "new manufacturing",
        "groundbreaking", "break ground", "奠基", "开工", "新建", "新工厂",
        "construction of", "build a factory", "set up factory",
        "establish factory", "首个工厂", "新厂", "first factory in",
        "brand new plant", "greenfield"
    ]

    # ──────────────────────────────────────────────
    # T2: 新建工厂关键词
    # ──────────────────────────────────────────────
    NEW_FACTORY_KEYWORDS = [
        # EN
        "new factory", "new plant", "new facility", "new manufacturing facility",
        "groundbreaking", "break ground", "greenfield",
        "construction of factory", "build factory", "building factory",
        "set up manufacturing", "establish manufacturing",
        "brand new factory", "first factory in", "first plant in",
        "open new factory", "open new plant", "new assembly plant",
        "new production site", "new manufacturing hub", "new manufacturing base",
        "invest in new facility", "build new site",
        # CN
        "新工厂", "新建工厂", "奠基", "开工", "兴建", "建厂",
        "首个工厂", "首家工厂", "新产线", "新园区",
        "宣布建厂", "开设工厂", "设立工厂", "开设新厂",
        "新制造基地", "新生产基地"
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

    # T3 产品发布关键词（仅限实际发布，不含传言/泄露）
    LAUNCH_KEYWORDS = [
        "launch", "announce", "release", "unveil", "debut", "introduce",
        "goes on sale", "ships", "shipping", "officially launched",
        "发布", "推出", "上市", "发售", "亮相", "首发", "宣布",
        "开售", "正式发布", "正式推出", "specs confirmed", "规格确认", "确认搭载"
    ]

    # T3 High 必须排除的传言/泄露关键词
    RUMOR_KEYWORDS = [
        "rumor", "rumored", "leak", "leaked", "reportedly", "report says",
        "allegedly", "sources say", "said to", "tipped", "unconfirmed",
        "render", "renders", "concept", "expected to", "may feature",
        "could launch", "might launch",
        "传言", "传闻", "曝光", "爆料", "疑似", "据传", "据报道", "消息称",
        "渲染图", "渲染", "泄露", "疑曝", "可能搭载", "预计发布"
    ]

    # T3 产品白名单（必须命中才允许进入 Topic3）
    # 包含产品类型名称 + 知名CE设备品牌/产品线（这些名称本身就代表CE产品）
    VALID_PRODUCTS = [
        # 产品类型（英文）
        "smartphone", "phone", "mobile phone", "handset",
        "foldable phone", "flip phone", "foldable",
        "tv", "television", "smart tv", "oled tv", "qled tv",
        "refrigerator", "fridge", "washing machine", "washer", "dryer",
        "air conditioner", "air purifier",
        "robot vacuum", "vacuum cleaner",
        "tablet", "laptop", "notebook",
        "smartwatch", "smart watch", "wearable",
        "earbuds", "earphone", "headphone", "soundbar",
        # 知名CE设备品牌/产品线（含意即CE产品）
        "iphone", "ipad", "galaxy", "galaxy tab", "galaxy watch",
        "xperia", "pixel", "pixel watch",
        "redmi", "find x", "find n", "reno",
        "mate", "nova", "pura", "honor magic",
        "razr", "zenbook", "rog phone",
        "macbook", "surface",
        # 产品类型（中文）
        "手机", "智能手机", "折叠屏手机", "折叠屏", "平板", "笔记本", "电视",
        "冰箱", "洗衣机", "空调", "净化器", "扫地机器人", "智能手表", "耳机"
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

    # 产品型号正则（T3 High 判断依据）— 精确品牌+型号模式，避免误匹配
    MODEL_PATTERN = re.compile(
        r"("
        r"Galaxy\s+\S+"                       # Galaxy S25 Ultra / Z Fold7
        r"|iPhone\s+\d+\w*"                   # iPhone 17 / 17e / 17 Pro
        r"|iPad\s+[\w\s]+"                    # iPad Pro / iPad mini
        r"|Xperia\s+\d+\s*\w*"               # Xperia 1 VIII
        r"|REDMI\s+\S+"                       # REDMI K90 Max
        r"|Redmi\s+\S+"                       # Redmi Note 14
        r"|vivo\s+[YVXSx]\d+\w*"             # vivo Y600 Pro / X200
        r"|Find\s+[XN]\d+\w*"                # Find X9 Ultra
        r"|Reno\s+\d+\w*"                    # Reno 14 Pro
        r"|Mate\s+\d+\w*"                    # Mate 70 Pro
        r"|Nova\s+\d+\w*"                    # Nova 13
        r"|Honor\s+\w+\d+\w*"               # Honor Magic7
        r"|Razr\s*\(\d{4}\)"                 # Razr (2026)
        r"|Pixel\s+\d+\w*"                   # Pixel 10 Pro XL
        r"|ROG\s+\S+"                        # ROG Phone 9
        r"|ZenBook\s+\S+"                    # ZenBook A16
        r"|MagicPad\s+\S+"                   # MagicPad 3 Pro
        r"|小米\s*\d+\w*"                    # 小米15 Pro
        r"|麒麟\s*\d+\w*"                   # 麒麟9030S
        r"|天玑\s*\d+\w*"                   # 天玑9400
        r")",
        re.IGNORECASE
    )

    # ──────────────────────────────────────────────
    # T4: 材料/技术白名单（必须命中才进入 Topic4）
    # ──────────────────────────────────────────────
    MATERIAL_KEYWORDS = [
        # 显示材料/面板技术（扩大覆盖）
        "oled material", "oled panel", "oled stack", "oled display panel",
        "amoled", "amoled display", "amoled panel",
        "ltps panel", "ltpo panel", "ltps amoled",
        "display panel technology", "display panel supply", "panel shipment",
        "display panel price", "panel price",
        "microled", "micro-led", "micro led",
        "miniled", "mini-led", "mini led",
        "qd-oled", "quantum dot material", "display stack", "display material",
        "micro oled", "transparent display panel", "flexible display panel",
        "display supply", "panel supply", "screen technology", "display technology",
        "tandem oled", "blue pholed", "oled technology",
        # 电池材料/技术
        "solid state battery", "solid-state battery", "silicon anode",
        "silicon carbon battery", "energy density breakthrough",
        "fast charging technology", "wireless charging technology",
        "battery material", "anode material", "cathode material",
        # 新材料
        "graphene", "carbon nanotube", "perovskite",
        "gallium nitride material", "gan material",
        "silicon carbide material", "sic material",
        "titanium alloy", "ceramic material",
        # 散热/结构
        "vapor chamber", "heat pipe", "graphite sheet",
        "thermal interface material",
        # 传感/摄像
        "under-display camera", "under display fingerprint",
        "ultrasonic fingerprint sensor", "3d sensing module",
        "tof sensor", "lidar module",
        # 中文
        "OLED材料", "OLED面板", "MicroLED", "MiniLED",
        "固态电池", "硅负极", "硅碳电池", "量子点材料",
        "显示材料", "石墨烯", "碳纳米管", "钙钛矿",
        "氮化镓材料", "碳化硅材料", "钛合金",
        "均热板", "热管", "导热材料", "散热材料",
        "屏下摄像头", "屏下指纹", "超声波指纹传感器"
    ]

    # T4 High: 明确指出被 OEM 采用（adoption signal）
    ADOPTION_SIGNAL_KEYWORDS = [
        "used in", "adopted by", "will be used in", "designed for",
        "integrated into", "equipped with", "built into",
        "confirmed for", "supplied to", "selected by",
        "搭载", "用于", "配备", "内置", "确认采用",
        "供应给", "已应用于", "已用于", "首发于",
        "将用于", "选定", "选用"
    ]

    # T4 Med: 已商业化/量产（需比High更保守）
    T4_MED_KEYWORDS = [
        "mass produced", "mass production started", "commercially available",
        "now in production", "entered mass production", "begin mass production",
        "已量产", "正式量产", "批量生产", "商业化量产",
        "开始量产", "进入量产", "实现量产"
    ]

    # T4 Low: 研发/早期阶段
    T4_LOW_KEYWORDS = [
        "research", "development stage", "prototype", "early stage",
        "lab", "laboratory", "r&d", "proof of concept",
        "研发", "研究阶段", "原型", "早期", "实验室", "概念验证"
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
        "electric vehicle battery", "ev battery pack", "ev chip",
        "autonomous driving", "self-driving chip",
        "自动驾驶芯片", "车规芯片", "汽车半导体", "新能源汽车电池",
        # 纯软件/AI平台/生态/应用
        "llm model", "foundation model", "large language model",
        "ai platform", "ai ecosystem", "generative ai platform",
        "ai chatbot", "ai chat app", "ai assistant app", "chatbot release",
        "ai model has", "new ai model", "ai reasoning", "ai promises",
        "software update", "os update", "firmware update",
        "android update", "ios update", "app store news",
        "cloud computing", "saas platform",
        "messaging app", "standalone app", "now on the app store",
        "available on the app store", "digital id feature", "wallet app",
        "软件更新", "系统更新", "固件升级", "生态系统", "AI聊天", "AI助手应用",
        "AI大模型", "大语言模型",
        # 流媒体/娱乐内容（Apple TV+等）
        "apple tv+", "streaming service", "tv show", "tv series", "tv comedy",
        "tv drama", "streaming content", "original series", "new comedy",
        "new series", "movie premiere", "film review",
        "流媒体", "电视剧", "综艺", "电影首映", "剧集",
        # 生活方式/人物专访/社论
        "lifestyle", "人物专访", "建筑设计师", "阅读清单", "碎片时间",
        "低头是", "抬头是", "散步", "街道上", "城市空间",
        # 食品/餐饮/非CE内容
        "食品安全", "餐饮", "网络餐饮", "食品案例", "鸭肉", "牛肉",
        "幽灵外卖", "过期原料", "food safety", "restaurant review",
        # CSR/环保/公关（无产品）
        "coral reef", "environmental initiative", "sustainability initiative",
        "csr initiative", "receives award", "international recognition",
        "environmental award", "green initiative",
        "珊瑚礁", "环保倡议", "社会责任", "获奖", "荣获",
        # 观点/评论/社论
        "commentary:", "opinion:", "editorial:", "column:", "analysis:",
        "gets the worst", "is a glimpse into",
        # 论坛/会议/路演
        "webinar", "symposium", "industry forum", "investor day",
        "路演", "项目路演", "investor pitch", "startup pitch",
        "semiconductor conference", "chip conference", "semi exhibition",
        "半导体展览", "芯片展览",
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
        "xperia", "sony", "lg electronics", "tcl", "hisense", "sharp", "panasonic",
        "motorola", "lenovo", "asus", "oneplus", "realme", "transsion", "tecno",
        "小米", "华为", "荣耀", "apple", "苹果", "索尼", "海信", "夏普", "松下",
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

        # T4: 先检查技术/材料（材料采用新闻优先归 T4，避免被 T3 误吸收）
        t4_ok, t4_priority = self._check_t4(text)
        if t4_ok:
            topics.append(4)
            self.stats["by_topic"][4] += 1
            self.stats["by_priority"][f"t4_{t4_priority}"] += 1

        # T3: 产品发布（已归 T4 则跳过，防止材料新闻被误归为产品发布）
        t3_ok, t3_priority = self._check_t3(title, text)
        if t3_ok and 4 not in topics:
            topics.append(3)
            self.stats["by_topic"][3] += 1
            self.stats["by_priority"][f"t3_{t3_priority}"] += 1

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

        Hard gates (in order):
        1. Must contain a product from VALID_PRODUCTS whitelist
        2. Must have launch/review/pricing signal
        3. High = real launch + product model (no rumors)
           Med  = product review
           Low  = pricing news OR launch without model OR launch with rumor
        """
        # Gate 1: 必须命中产品白名单
        if not any(kw.lower() in text for kw in self.VALID_PRODUCTS):
            return False, ""

        has_launch  = any(kw.lower() in text for kw in self.LAUNCH_KEYWORDS)
        has_review  = any(kw.lower() in text for kw in self.REVIEW_KEYWORDS)
        has_pricing = any(kw.lower() in text for kw in self.PRICING_KEYWORDS)

        # Gate 2: 必须有明确信号
        if not (has_launch or has_review or has_pricing):
            return False, ""

        is_rumor = any(kw.lower() in text for kw in self.RUMOR_KEYWORDS)
        has_model = self._has_product_model(title + " " + text)

        # 优先级判断（严格顺序）
        if has_launch and has_model and not is_rumor:
            return True, "high"   # 真实发布 + 明确型号 + 非传言
        if has_review and not is_rumor:
            return True, "med"    # 真实评测
        if has_pricing:
            return True, "low"    # 价格新闻
        if has_launch or has_review:
            return True, "low"    # 有发布信号但有传言/无型号 → low
        return False, ""

    def _check_t4(self, text: str) -> Tuple[bool, str]:
        """
        T4: 消费电子相关新技术/材料。
        返回 (是否匹配, 优先级 high/med/low)

        Hard gates (in order):
        1. Must contain material/tech from MATERIAL_KEYWORDS whitelist
        2. Must NOT be a product launch/pricing event (→ T3 territory)
        3. Must have CE application link
        4. High = confirmed adoption by OEM (ADOPTION_SIGNAL)
           Med  = mass production started/commercialized
           Low  = R&D / early stage
        """
        # Gate 1: 必须命中材料/技术白名单
        if not any(kw.lower() in text for kw in self.MATERIAL_KEYWORDS):
            return False, ""

        # Gate 2: 排除纯产品价格新闻（定价新闻属于 T3 领域）
        # 注意：只排除 PRICING，不排除 LAUNCH（材料采用通知也会用 "announce"）
        is_product_pricing = (
            any(kw.lower() in text for kw in self.VALID_PRODUCTS) and
            any(kw.lower() in text for kw in self.PRICING_KEYWORDS)
        )
        if is_product_pricing:
            return False, ""   # 价格新闻归 T3 Low，不归 T4

        # Gate 3: 必须有 CE 应用链接（技术需要落地到具体产品或消费电子领域）
        CE_LINK_KEYWORDS = [
            "phone", "smartphone", "mobile", "iphone", "galaxy",
            "tv", "television", "home appliance",
            "consumer electronics", "electronic device", "electronics",
            "wearable", "tablet", "laptop", "earbuds",
            "手机", "电视", "家电", "消费电子", "显示器"
        ]
        has_ce_link = any(kw.lower() in text for kw in CE_LINK_KEYWORDS)
        if not has_ce_link:
            return False, ""

        # 优先级（严格顺序）
        if any(kw.lower() in text for kw in self.ADOPTION_SIGNAL_KEYWORDS):
            return True, "high"
        if any(kw.lower() in text for kw in self.T4_MED_KEYWORDS):
            return True, "med"
        return True, "low"   # 含技术词 + CE链接，但无明确量产/采用信号 → low

    def _has_product_model(self, text: str) -> bool:
        """检测文本中是否含有明确的产品型号（使用精确品牌+型号正则）"""
        return bool(self.MODEL_PATTERN.search(text))

    # ------------------------------------------------------------------
    # 验证层（输出前最终规则检查）
    # ------------------------------------------------------------------

    def validate_article(self, article: Dict) -> bool:
        """
        输出前逐条验证。违规条目降级或标记，严重违规返回 False（删除）。

        规则：
        - T3 High 无产品型号 → 降级为 Low
        - T3 High 含传言关键词 → 降级为 Low
        - T4 High 无 adoption signal → 降级为 Med
        - T3 或 T4 含产品白名单外的内容 → 不删除，已在分类时过滤
        """
        topics = article.get("topics", [])

        if 3 in topics:
            priority = article.get("t3_priority", "low")
            if priority == "high":
                text = (article.get("title", "") + " " + article.get("summary", "")).lower()
                is_rumor = any(kw.lower() in text for kw in self.RUMOR_KEYWORDS)
                has_model = self._has_product_model(article.get("title", "") + " " + text)
                if is_rumor or not has_model:
                    article["t3_priority"] = "low"   # 降级，不删除

        if 4 in topics:
            priority = article.get("t4_priority", "low")
            if priority == "high":
                text = (article.get("title", "") + " " + article.get("summary", "")).lower()
                has_adoption = any(kw.lower() in text for kw in self.ADOPTION_SIGNAL_KEYWORDS)
                if not has_adoption:
                    article["t4_priority"] = "med"   # 降级为 Med

        return True   # 降级处理，无需删除

    def validate_batch(self, articles: List[Dict]) -> List[Dict]:
        """批量验证，就地修改优先级字段"""
        for article in articles:
            self.validate_article(article)
        return articles

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
