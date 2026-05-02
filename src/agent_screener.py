#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Agent Screener
对每个 Topic 的文章进行 AI 二次筛查，过滤规则分类器漏网的噪声内容

使用方式：
    screener = AgentScreener()
    articles_by_topic = screener.screen_all(articles_by_topic)
"""

import os
import json
import time
from typing import Dict, List, Tuple
from openai import OpenAI


class AgentScreener:
    """
    DeepSeek Agent 筛查器
    对分类后的文章进行逐 Topic AI 验证，输出理由+保留/删除决定
    """

    # 每个 Topic 的专属筛查 Prompt
    TOPIC_PROMPTS = {
        1: """你是消费电子制造情报审核专家。

审核 Topic 1（东南亚消费电子制造扩产）文章是否真正符合：
✅ 必须同时满足：
   1. 地区：越南/印度/泰国/马来西亚/印尼/新加坡/菲律宾
   2. 行业：手机/家电/平板/消费电子产品的制造/组装
   3. 事件：现有工厂的扩产/追加投资/产能提升（非新建工厂）

❌ 必须删除：
   - 旅游/金融/农业投资
   - 半导体晶圆厂/芯片制造
   - 汽车制造
   - 纯政策/经济分析文章（无具体公司/工厂）
   - 新建工厂（→ Topic 2，不是 Topic 1）

对每篇文章返回 keep（保留）或 remove（删除）+ 一句理由。""",

        2: """你是消费电子制造情报审核专家。

审核 Topic 2（东南亚新建消费电子工厂）文章是否真正符合：
✅ 必须同时满足：
   1. 地区：越南/印度/泰国/马来西亚/印尼/新加坡/菲律宾
   2. 行业：手机/家电/平板/消费电子产品制造
   3. 事件：新建工厂/新厂宣布/奠基/开工（非扩产）

❌ 必须删除：
   - 旅游/金融/科技园区（非制造）
   - 半导体/芯片/晶圆厂
   - 汽车/新能源汽车工厂
   - 纯泛亚供应链分析
   - 只是扩产而非新建（→ Topic 1）

对每篇文章返回 keep 或 remove + 一句理由。""",

        3: """你是消费电子产品情报审核专家。

审核 Topic 3（重大产品发布）文章的分类是否正确：

✅ High Priority 必须全部满足：
   1. 含明确产品型号（Galaxy S26/iPhone 17/Xiaomi 15 Pro 等）
   2. 含真实发布行为词（officially launched/unveiled/goes on sale/正式发布/亮相）
      注意："specs confirmed"/"规格确认" 不是发布行为词
   3. 不含传言词（rumor/leaked/reportedly/could feature/有望/据传/博主透露）

✅ Med Priority：产品评测（review/hands-on/tested）

✅ Low Priority：价格/传言/无型号

❌ 必须删除整篇文章（无论什么优先级）：
   - 三星自有产品发布/功能/软件（保留三星评测和Samsung Display技术）
   - 软件App发布（不是硬件产品）
   - 流媒体内容（Apple TV+剧集等）
   - 家电零售商/服务商
   - 掩膜版/光掩模新闻

对每篇文章：先判断是否删除，再判断优先级是否正确，返回结果。""",

        4: """你是消费电子新技术材料情报审核专家。

审核 Topic 4（新技术/新材料）文章是否真正符合：

✅ 必须同时满足：
   1. 含材料/技术白名单（OLED面板/MicroLED/固态电池/石墨烯散热/碳纤维复合/钛合金等）
   2. 有消费电子应用场景（手机/家电/电视/平板等）

✅ 优先级：
   - High：明确OEM已采用（used in/adopted by/starts shipping/供应给/搭载）
   - Med：已商业化量产（mass produced/已量产）
   - Low：研发阶段

❌ 必须删除：
   - 纯半导体/芯片制造（无CE产品链接）
   - 光子计算/光通信（数据中心应用）
   - 汽车/航空应用的材料
   - 纯产品发布（→ Topic 3，不是 Topic 4）
   - 面板出货量/价格统计数据

对每篇文章返回 keep 或 remove + 优先级是否正确 + 一句理由。"""
    }

    # 批量处理的 Prompt 模板
    BATCH_PROMPT = """请逐篇审核以下 {count} 篇文章，严格按规则判断。

文章列表：
{articles}

对每篇文章，返回以下 JSON 格式（数组，与输入顺序一致）：
[
  {{"index": 0, "decision": "keep", "priority": "high", "reason": "一句话理由"}},
  {{"index": 1, "decision": "remove", "priority": null, "reason": "删除原因"}},
  ...
]

decision: "keep" 或 "remove"
priority: "high"/"med"/"low"（仅 Topic 3/4 需要，Topic 1/2 填 null）
reason: 简短中文理由（10-20字）

只返回 JSON 数组，不要其他文字。"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            print("⚠️  AgentScreener: 无 DEEPSEEK_API_KEY，跳过 AI 筛查")
            self.enabled = False
            return

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com/v1"
        )
        self.enabled = True
        self.stats = {"removed": 0, "kept": 0, "priority_fixed": 0, "api_calls": 0}
        print("✅  AgentScreener: DeepSeek API 就绪")

    def screen_topic(self, topic_id: int, articles: List[Dict],
                     batch_size: int = 10) -> Tuple[List[Dict], int]:
        """
        对单个 Topic 的文章进行 AI 筛查。
        返回 (保留的文章列表, 删除数量)
        """
        if not self.enabled or not articles:
            return articles, 0

        system_prompt = self.TOPIC_PROMPTS.get(topic_id, "")
        kept = []
        removed_count = 0

        # 分批处理（避免超出 context 限制）
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            results = self._screen_batch(system_prompt, batch, topic_id)

            for j, result in enumerate(results):
                if j >= len(batch):
                    break
                art = batch[j]
                decision = result.get("decision", "keep").lower()
                reason   = result.get("reason", "")
                new_pri  = result.get("priority")

                if decision == "remove":
                    removed_count += 1
                    print(f"   🗑️  [T{topic_id}] 删除: {art.get('title','')[:50]} | {reason}")
                else:
                    # 修正优先级（如果 AI 认为分类有误）
                    if new_pri and topic_id == 3 and new_pri != art.get("t3_priority"):
                        old = art.get("t3_priority", "?")
                        art["t3_priority"] = new_pri
                        self.stats["priority_fixed"] += 1
                        print(f"   🔄  [T3] 优先级修正 {old}→{new_pri}: {art.get('title','')[:45]}")
                    elif new_pri and topic_id == 4 and new_pri != art.get("t4_priority"):
                        old = art.get("t4_priority", "?")
                        art["t4_priority"] = new_pri
                        self.stats["priority_fixed"] += 1
                        print(f"   🔄  [T4] 优先级修正 {old}→{new_pri}: {art.get('title','')[:45]}")
                    kept.append(art)

            # API 速率限制保护
            time.sleep(0.5)

        return kept, removed_count

    def screen_all(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
        """
        对所有 Topic 的文章进行 AI 筛查。
        返回筛查后的 articles_by_topic
        """
        if not self.enabled:
            return articles_by_topic

        print("\n🤖 Agent 筛查层启动...")
        result = {}
        total_removed = 0

        for topic_id in [1, 2, 3, 4]:
            arts = articles_by_topic.get(topic_id, [])
            if not arts:
                result[topic_id] = []
                continue

            print(f"\n   📋 Topic {topic_id}: 审核 {len(arts)} 篇...")
            kept, removed = self.screen_topic(topic_id, arts)
            result[topic_id] = kept
            total_removed += removed
            self.stats["kept"]    += len(kept)
            self.stats["removed"] += removed
            print(f"   ✅ Topic {topic_id}: 保留 {len(kept)} 篇，删除 {removed} 篇")

        print(f"\n🤖 Agent 筛查完成:")
        print(f"   保留: {self.stats['kept']} 篇")
        print(f"   删除: {self.stats['removed']} 篇")
        print(f"   优先级修正: {self.stats['priority_fixed']} 篇")
        print(f"   API 调用: {self.stats['api_calls']} 次")
        return result

    def _screen_batch(self, system_prompt: str, batch: List[Dict],
                      topic_id: int) -> List[Dict]:
        """单批次 AI 筛查"""
        # 构建文章列表文本
        articles_text = ""
        for j, art in enumerate(batch):
            pri_key = "t3_priority" if topic_id == 3 else "t4_priority"
            pri = art.get(pri_key, "")
            articles_text += (
                f"[{j}] 标题: {art.get('title', '')}\n"
                f"    摘要: {(art.get('summary', '') or '')[:200]}\n"
                f"    来源: {art.get('source', '')}\n"
                f"    日期: {art.get('date', art.get('published_date', ''))}\n"
                + (f"    当前优先级: {pri}\n" if pri else "")
                + "\n"
            )

        user_prompt = self.BATCH_PROMPT.format(
            count=len(batch),
            articles=articles_text
        )

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            self.stats["api_calls"] += 1

            raw = response.choices[0].message.content.strip()
            # 解析返回的 JSON
            data = json.loads(raw)
            # 支持两种格式：数组 或 {"results": [...]}
            if isinstance(data, list):
                return data
            for key in ["results", "articles", "decisions"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [{"decision": "keep", "priority": None, "reason": "解析失败"} for _ in batch]

        except json.JSONDecodeError as e:
            print(f"   ⚠️  JSON 解析失败: {e}")
            return [{"decision": "keep", "priority": None, "reason": "解析失败"} for _ in batch]
        except Exception as e:
            print(f"   ⚠️  API 调用失败: {e}")
            return [{"decision": "keep", "priority": None, "reason": "API失败"} for _ in batch]
