    def cross_topic_deduplicate(self, articles_by_topic: Dict[int, List[Dict]]) -> Dict[int, List[Dict]]:
        """
        跨栏目去重：同一新闻只保留在优先级最高的Topic
        
        Topic优先级: T1(竞品) > T2(技术) > T3(制造) > T4(展会) > T5(供应链)
        """
        topic_priority = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1}
        
        # 收集所有文章的指纹
        article_fingerprints = {}
        
        before_total = sum(len(articles) for articles in articles_by_topic.values())
        
        for topic_id, articles in articles_by_topic.items():
            for article in articles:
                # 生成指纹：URL + 标题前50字符
                url = article.get('link', article.get('url', ''))
                title = article.get('title', '')[:50]
                fingerprint = hashlib.md5(f"{url}_{title}".encode()).hexdigest()
                
                priority = topic_priority.get(topic_id, 0)
                
                if fingerprint not in article_fingerprints:
                    article_fingerprints[fingerprint] = (topic_id, article, priority)
                else:
                    existing_topic, existing_article, existing_priority = article_fingerprints[fingerprint]
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
