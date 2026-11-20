"""Create a new dedicated NearHelp moderator on the server, without a public enrollment route."""

import argparse
from getpass import getpass
from pathlib import Path
import re
import sqlite3
import sys
from uuid import uuid4

from .auth import new_password_hash
from .config import database_path
from .db import connect, initialize


def create_admin(path, username, password):
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,24}", username):
        raise ValueError("账号需为 3–24 个小写字母、数字或下划线。")
    if not 12 <= len(password) <= 128:
        raise ValueError("管理员密码需为 12–128 个字符。")
    if not path.is_file():
        raise ValueError("未找到数据库，请核对服务实际使用的路径。")
    initialize(path)
    digest = new_password_hash(password)
    with connect(path) as connection:
        try:
            connection.execute(
                "INSERT INTO accounts (id,username,nickname,password_hash,is_admin) VALUES (?,?,?,?,1)",
                (str(uuid4()), username, "Around You 管理员", digest),
            )
        except sqlite3.IntegrityError:
            raise ValueError("该账号名已被使用，请选择一个新的管理员账号名。") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--db", type=Path, help="SQLite 文件，默认使用服务配置")
    parser.add_argument("--password-stdin", action="store_true", help="从标准输入读取一行密码")
    args = parser.parse_args()
    try:
        if args.password_stdin:
            password = sys.stdin.readline(132).rstrip("\r\n")
        else:
            password = getpass("新管理员密码：")
            if password != getpass("再次输入密码："):
                raise ValueError("两次输入的密码不一致。")
        create_admin(args.db or database_path(), args.username, password)
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    print("已创建管理员账号。")


if __name__ == "__main__":
    main()
