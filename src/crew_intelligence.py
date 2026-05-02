#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CE Intelligence System — CrewAI Multi-Agent Version
多Agent情报系统示例：搜索 → 过滤 → 分类 → 生成报告

需要: pip install crewai crewai-tools
      DEEPSEEK_API_KEY 环境变量
"""

import os
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool, ScrapeWebsiteTool

# ── 工具配置 ──────────────────────────────────────────────────────────
# Serper: 免费 2500次/月 (serper.dev)
# Tavily: 免费 1000次/月 (tavily.com) — 替代选项
search_tool = SerperDevTool()

# ── LLM 配置（使用 DeepSeek） ─────────────────────────────────────────
from crewai import LLM
deepseek_llm = LLM(
    model="deepseek/deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
    temperature=0.1
)

# ── Agent 定义 ────────────────────────────────────────────────────────

search_agent = Agent(
    role="消费电子情报搜索员",
    goal="搜索今日东南亚制造、产品发布、新技术材料的最新新闻",
    backstory="""你专门搜索消费电子行业新闻。
    重点关注：越南/印度/泰国/马来西亚/印尼工厂新闻；
    手机/家电新品发布；OLED/MicroLED/固态电池技术进展。
    排除：半导体晶圆厂、纯软件更新、汽车芯片。""",
    tools=[search_tool],
    llm=deepseek_llm,
    verbose=True
)

filter_agent = Agent(
    role="情报质量过滤官",
    goal="严格过滤不相关内容，确保每条新闻都符合消费电子情报标准",
    backstory="""你是严格的情报质量控制官。
    必须删除：三星自有产品发布（保留三星评测和Samsung Display技术）、
    半导体制造业、软件更新、汽车应用、航空应用、
    家电服务商、电信运营商产品库、新闻聚合摘要。
    宁可少，不可错。""",
    llm=deepseek_llm,
    verbose=True
)

classifier_agent = Agent(
    role="消费电子情报分类专家",
    goal="将过滤后的新闻按 Topic1-4 准确分类并标注优先级",
    backstory="""你按照严格规则分类新闻：
    Topic1: 东南亚CE制造扩产（现有工厂）
    Topic2: 东南亚新建CE工厂
    Topic3: CE产品发布 [High=型号+发布行为词+非传言 / Med=评测 / Low=价格传言]
    Topic4: CE新技术材料 [High=OEM已采用 / Med=已量产 / Low=研发阶段]""",
    llm=deepseek_llm,
    verbose=True
)

writer_agent = Agent(
    role="情报报告撰写员",
    goal="生成结构化的消费电子产业情报日报",
    backstory="""你负责将分类好的新闻整理成专业日报。
    每条新闻写2-3句中文摘要（50-100字）。
    格式：核心事件 + 具体数据 + 行业影响。
    零幻觉原则：只使用原文中的信息。""",
    llm=deepseek_llm,
    verbose=True
)

# ── Task 定义 ────────────────────────────────────────────────────────

from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")

task_search = Task(
    description=f"""
    搜索 {today} 的以下类别最新新闻：
    1. 东南亚消费电子制造扩产/新建工厂（越南/印度/泰国/马来西亚/印尼）
    2. 手机/家电/平板/笔记本等CE产品发布评测
    3. OLED/MicroLED/固态电池/散热材料/复合材料等CE新技术

    每类至少搜索5-10条，记录：标题、来源、日期、摘要
    """,
    agent=search_agent,
    expected_output="结构化的新闻列表，包含标题/来源/日期/摘要"
)

task_filter = Task(
    description="""
    对搜索结果进行严格过滤，删除：
    - 三星自有产品发布（保留：三星评测、Samsung Display技术、三星SEA工厂）
    - 半导体制造业（晶圆厂/封装厂/EDA）
    - 软件更新（SmartThings/系统更新/App发布）
    - 汽车/航空应用
    - 新闻聚合摘要（要闻提示等）
    - 家电服务商/电信产品库
    - 完全无关内容（食品安全/犯罪等）

    输出：过滤后的新闻列表
    """,
    agent=filter_agent,
    expected_output="过滤后的干净新闻列表",
    context=[task_search]
)

task_classify = Task(
    description="""
    将过滤后的新闻分类到以下Topic，并标注优先级：

    Topic1: 东南亚CE制造扩产（SEA地区+CE行业+扩产信号）
    Topic2: 东南亚新建CE工厂（SEA地区+CE行业+新建信号）
    Topic3: CE产品发布
      - High: 明确型号 + 发布行为词(officially launched/unveiled/ships) + 无传言词
      - Med: 产品评测(review/hands-on)
      - Low: 价格/传言/无型号
    Topic4: CE新技术材料
      - High: 已确认OEM采用(used in/adopted by/starts shipping)
      - Med: 已商业化量产
      - Low: 研发阶段

    归属优先级: Topic3 > Topic4 > Topic2 > Topic1
    输出：每条新闻的Topic分类和优先级
    """,
    agent=classifier_agent,
    expected_output="带Topic分类和优先级标注的新闻列表",
    context=[task_filter]
)

task_report = Task(
    description=f"""
    生成 {today} 消费电子产业情报日报，格式如下：

    ## 🚨 ALERTS（满足≥2个维度：行业格局/核心技术/供应链风险/重大投资）

    ## 🟩 Topic 1 — Consumer Electronics Manufacturing in Southeast Asia

    ## 🟦 Topic 2 — New Manufacturing Plants in Southeast Asia

    ## 🟥 Topic 3 — Major Product Announcements
    ### [High Priority]
    ### [Low Priority]
    ### [Med Priority]

    ## 🟨 Topic 4 — New Technology / Materials
    ### [High Priority]
    ### [Med Priority]
    ### [Low Priority]

    每条新闻格式：
    **日期 · 来源**
    [类别] 标题
    中文摘要（2-3句）
    """,
    agent=writer_agent,
    expected_output="完整格式化的消费电子产业情报日报",
    context=[task_classify]
)

# ── Crew 执行 ────────────────────────────────────────────────────────

def run_intelligence_report():
    crew = Crew(
        agents=[search_agent, filter_agent, classifier_agent, writer_agent],
        tasks=[task_search, task_filter, task_classify, task_report],
        process=Process.sequential,
        verbose=True
    )
    result = crew.kickoff()
    print("\n" + "="*60)
    print("📰 消费电子产业情报日报")
    print("="*60)
    print(result)
    return result

if __name__ == "__main__":
    run_intelligence_report()
