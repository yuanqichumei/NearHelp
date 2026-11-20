"""Build a cached discussion brief on an administrator's explicit request."""
import json
import os
import time

from .db import connect
from .deepseek import DeepSeekError, synthesize
from .zhihu import ZhihuError, search_answers


def rag_enabled():
    return os.getenv("ZHIHU_RAG_ENABLED", "").lower() == "true"


def eligible_ids(rows):
    return {row["id"] for row in rows if row["ai_consent"] and sum(c.isalnum() for c in row["content"]) >= 6}


def cached_insights(db, topic_id, sources):
    row = db.execute("SELECT payload FROM discussion_insights WHERE topic_id=?", (topic_id,)).fetchone()
    if row is None:
        return {"zhihu": [], "local": [], "comparison": [], "include_zhihu": False}
    payload = json.loads(row["payload"])
    # Keep a generated result only while all input answers are still visible to this reader.
    # An uncited answer can also have influenced the result.
    valid = set(payload["inputs"]) <= eligible_ids(sources)
    references = [ref for ref in payload["zhihu"] if ref.get("text")]
    return {
        "zhihu": references, "local": payload["local"] if valid else [],
        "comparison": payload["comparison"] if valid and references and rag_enabled() else [],
        "include_zhihu": payload.get("include_zhihu", bool(references)),
    }


def refresh_insights(path, topic_id, title, query, sources, include_zhihu):
    started = time.time()
    ids = eligible_ids(sources)
    local = [{"id": f"L{row['id']}", "text": row["content"]} for row in sources if row["id"] in ids][:24]
    with connect(path) as db:
        cached = db.execute("SELECT payload FROM discussion_insights WHERE topic_id=?", (topic_id,)).fetchone()
    previous = json.loads(cached["payload"]) if cached else None
    payload = {"query": query, "include_zhihu": include_zhihu, "inputs": [int(item["id"][1:]) for item in local],
               "zhihu": [], "local": [], "comparison": []}
    messages = []
    refs = []
    if include_zhihu:
        try:
            refs = search_answers(query)
            payload["zhihu"] = refs
            messages.append(f"找到 {len(refs)} 条知乎回答。")
        except ZhihuError as error:
            if previous and previous["query"] == query:
                payload["zhihu"] = previous["zhihu"]
            messages.append(str(error))
    else:
        messages.append("本话题的知乎回答已关闭。")

    if len(local) >= 3:
        if previous and previous["inputs"] == payload["inputs"]:
            payload["local"] = previous["local"]
            if rag_enabled() and previous["zhihu"] == payload["zhihu"]:
                payload["comparison"] = previous["comparison"]
        try:
            payload["local"] = synthesize(title, local)
            messages.append("已生成附近 AI 小结。")
        except DeepSeekError as error:
            messages.append(str(error))
        if refs and rag_enabled():
            try:
                payload["comparison"] = synthesize(title, local, [{"id": r["id"], "text": r["text"]} for r in refs])
                messages.append("已生成有来源的观点对照。")
            except DeepSeekError as error:
                messages.append(str(error))
    else:
        messages.append("需要至少 3 位附近访客发表符合条件的新回答后才能生成小结。")
    with connect(path) as db:
        db.execute("""INSERT INTO discussion_insights(topic_id,payload,updated_at) VALUES (?,?,?)
            ON CONFLICT(topic_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
            WHERE excluded.updated_at >= discussion_insights.updated_at""",
                   (topic_id, json.dumps(payload, ensure_ascii=False), started))
    return {"message": " ".join(messages)}
