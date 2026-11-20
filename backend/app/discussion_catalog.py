"""Editorial starter questions. AI perspectives are authored in advance for each prompt."""

COMMUNITY = "nearhelp-discussions"
QUESTIONS = {
    "authorship": {
        "title": "如果 AI 写了九成代码，这个作品还算你做的吗？",
        "themes": ["代码贡献", "设计决策", "对成品负责"],
        "angle": "行数容易计算，判断却很难计量。假设两队生成了同一段程序，一队能找到它在手机上失败的原因并修好，另一队只能再试一次提示词。你会给两队一样的评价吗？",
        "url": "https://www.zhihu.com/question/2030599879777572198",
    },
    "learning": {
        "title": "有了 AI，学编程还应该从手写代码开始吗？",
        "themes": ["基础练习", "先做出作品", "理解和调试"],
        "angle": "第一次把想法跑起来，和第一次读懂一条报错，是两种不同的成就感。试着回忆自己卡得最久的一次：当时如果有人直接给出答案，你会学到什么，又会错过什么？",
        "url": "https://www.zhihu.com/question/638375888",
    },
    "tools": {
        "title": "哪一步交给 AI 之后，你反而花了更多时间？",
        "themes": ["描述需求", "排查错误", "验收结果"],
        "angle": "草稿生成得快，验证也可能更费力。可以拿你今天的一次任务作比较，把描述、等待、返工和验收的时间都算上，看节省发生在哪一步。",
        "url": "https://www.zhihu.com/question/640036429",
    },
    "teamwork": {
        "title": "小组合作时，怎么分工才算公平？",
        "themes": ["花费的时间", "各自的专长", "学习的机会"],
        "angle": "让最熟练的人一直负责展示，团队也许交付得最快，可新人就一直没法练习。你上一次合作时，哪件事应该由最擅长的人做，哪件事值得轮流试？",
        "url": "https://www.zhihu.com/question/604247909",
    },
    "hackathon-pick": {
        "title": "本次黑客松，你觉得哪个作品更好？",
        "themes": [],
        "angle": "一个作品可以因为技术扎实、切中真实需求或现场完成度高而出色。你印象最深的是哪个作品，它的哪个细节改变了你的判断？",
        "url": "",
    },
    "hong-kong-career": {
        "title": "港校毕业后，你打算留在香港发展吗？",
        "themes": [],
        "angle": "试着把毕业后的第一份工作和五年后的生活分开想。哪些具体机会、生活成本或家庭安排，会让你做不同的选择？",
        "url": "",
    },
}


def feature(db, venue, lat, lon, key, url):
    current = db.execute("SELECT * FROM discussion_rounds WHERE venue=? AND active=1 AND featured=1", (venue,)).fetchone()
    if current and current["question_key"] == key:
        db.execute("UPDATE discussion_rounds SET zhihu_url=? WHERE topic_id=?", (url, current["topic_id"]))
        return current["topic_id"]
    if current:
        db.execute("UPDATE discussion_rounds SET active=0, pinned_until=NULL WHERE topic_id=?", (current["topic_id"],))
        lat, lon = current["lat"], current["lon"]
    title = QUESTIONS[key]["title"]
    tid = db.execute("INSERT INTO topics (community_slug,guest_id,nickname,title,content) VALUES (?,?,?,?,?)",
                     (COMMUNITY, "editorial", "Around You", title, "")).lastrowid
    db.execute("INSERT INTO discussion_rounds(topic_id,venue,lat,lon,question_key,zhihu_url) VALUES (?,?,?,?,?,?)",
               (tid, venue, round(lat, 3), round(lon, 3), key, url))
    return tid


def seed(db):
    db.execute("INSERT OR IGNORE INTO communities(slug) VALUES (?)", (COMMUNITY,))
    if not db.execute("SELECT 1 FROM discussion_rounds LIMIT 1").fetchone():
        feature(db, "香港城市大学", 22.338, 114.172, "authorship", QUESTIONS["authorship"]["url"])
    for key in ("hackathon-pick", "hong-kong-career"):
        venue = "香港城市大学"
        if db.execute("SELECT 1 FROM discussion_rounds WHERE venue=? AND question_key=?", (venue, key)).fetchone():
            continue
        tid = db.execute("INSERT INTO topics (community_slug,guest_id,nickname,title,content) VALUES (?,?,?,?,?)",
                         (COMMUNITY, "editorial", "Around You", QUESTIONS[key]["title"], "")).lastrowid
        db.execute("""INSERT INTO discussion_rounds(topic_id,venue,lat,lon,question_key,zhihu_url,featured)
            VALUES (?,?,?,?,?,'',0)""", (tid, venue, 22.338, 114.172, key))
