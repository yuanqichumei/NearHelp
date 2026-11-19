"""Preview or remove one explicitly selected demo guest request and its discussion."""

import argparse
from pathlib import Path

from .db import connect


def clean_request(path: Path, request_id: int, apply=False):
    if not path.is_file():
        raise ValueError("找不到指定的数据库文件。")
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT t.title FROM help_requests h JOIN accounts a ON a.id=h.author_id
               JOIN topics t ON t.id=h.topic_id WHERE h.topic_id=? AND a.is_demo=1""",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError("没有找到由演示访客发布的该条需求。")
        if apply:
            for table in ("help_messages", "help_conversations", "help_offers", "help_reports"):
                db.execute(f"DELETE FROM {table} WHERE request_id=?", (request_id,))
            db.execute("DELETE FROM comments WHERE topic_id=?", (request_id,))
            db.execute("DELETE FROM help_requests WHERE topic_id=?", (request_id,))
            db.execute("DELETE FROM topics WHERE id=?", (request_id,))
        return row["title"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--request", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        title = clean_request(args.db, args.request, args.apply)
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    print(("已清理" if args.apply else "预览，将清理需求及关联评论、申请、私信和举报"), args.request, title)
