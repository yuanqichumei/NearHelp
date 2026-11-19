"""Account authentication for NearTalk actions that require a durable identity."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, SecretStr

from .db import connect
from .location import SESSION_SECONDS, rate_limit

COOKIE = "neartalk_account"
DEMO_COOKIE = "nearhelp_demo"


class Credentials(BaseModel):
    username: str
    password: SecretStr


class Registration(Credentials):
    nickname: str


def password_digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_account(connection, request, *, allow_demo=False):
    cookies = (COOKIE, DEMO_COOKIE) if allow_demo and request.app.state.demo_guests else (COOKIE,)
    for name in cookies:
        token = request.cookies.get(name, "")
        if re.fullmatch(r"[a-zA-Z0-9_-]{43}", token):
            actor = connection.execute(
                """SELECT a.id, a.username, a.nickname, a.share_presence, a.discoverable, a.is_demo
                   FROM accounts a JOIN account_sessions s ON s.account_id = a.id
                   WHERE s.id=? AND s.expires_at>? AND a.is_demo=?""",
                (token_digest(token), time.time(), name == DEMO_COOKIE),
            ).fetchone()
            if actor:
                return actor
    return None


def require_account(connection, request, *, allow_demo=False):
    account = current_account(connection, request, allow_demo=allow_demo)
    if account is None:
        raise HTTPException(401, "请先登录。")
    return account


def current_help_user(connection, request):
    return current_account(connection, request, allow_demo=True)


def require_help_user(connection, request):
    return require_account(connection, request, allow_demo=True)


def same_origin(request):
    # Browser POSTs with Origin must originate on the site's exact origin.
    origin = request.headers.get("origin")
    if origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "请求来源无效。")


def public_account(account):
    return {"id": account["id"], "username": account["username"], "nickname": account["nickname"], "is_demo": bool(account["is_demo"]),
            "share_presence": bool(account["share_presence"]), "discoverable": bool(account["discoverable"])}


def open_session(connection, request, response, user_id, cookie=COOKIE):
    token = secrets.token_urlsafe(32)
    previous = request.cookies.get(cookie)
    if previous:
        connection.execute("DELETE FROM account_sessions WHERE id = ?", (token_digest(previous),))
    connection.execute("INSERT INTO account_sessions VALUES (?, ?, ?)",
                       (token_digest(token), user_id, time.time() + SESSION_SECONDS))
    response.set_cookie(cookie, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict")


def auth_router(path):
    router = APIRouter(prefix="/api/auth")

    @router.post("/session")
    def start(request: Request, response: Response):
        same_origin(request)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = current_help_user(connection, request)
            if account:
                return public_account(account)
            if not request.app.state.demo_guests:
                return None
            rate_limit(connection, request, "demo-create", time.time(), 30)
            actor = str(uuid4())
            nickname = "邻友·" + actor[:6].upper()
            connection.execute(
                "INSERT INTO accounts(id, username, nickname, password_hash, is_demo) VALUES (?,?,?,'',1)",
                (actor, "demo:" + actor, nickname),
            )
            open_session(connection, request, response, actor, DEMO_COOKIE)
            return public_account(connection.execute("SELECT * FROM accounts WHERE id=?", (actor,)).fetchone())

    def auth_limit(request, action, limit):
        same_origin(request)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rate_limit(connection, request, action, time.time(), limit)

    @router.post("/register", status_code=201)
    def register(body: Registration, request: Request, response: Response):
        auth_limit(request, "register", 15)
        username, nickname = body.username.strip().lower(), body.nickname.strip()
        password = body.password.get_secret_value()
        if not re.fullmatch(r"[a-z0-9_]{3,24}", username) or not 1 <= len(nickname) <= 24:
            raise HTTPException(422, "账号需为 3–24 个字母、数字或下划线，昵称需为 1–24 个字符。")
        if not 10 <= len(password) <= 128:
            raise HTTPException(422, "密码需为 10–128 个字符。")
        salt = secrets.token_bytes(16)
        user_id = str(uuid4())
        try:
            digest = password_digest(password, salt)
            with connect(path) as connection:
                connection.execute(
                    "INSERT INTO accounts (id, username, nickname, password_hash) VALUES (?, ?, ?, ?)",
                    (user_id, username, nickname, salt.hex() + ":" + digest),
                )
                open_session(connection, request, response, user_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "这个账号名已被使用。") from None
        return public_account({"id": user_id, "username": username, "nickname": nickname,
                               "is_demo": False, "share_presence": False, "discoverable": False})

    @router.post("/login")
    def login(body: Credentials, request: Request, response: Response):
        auth_limit(request, "login", 20)
        username = body.username.strip().lower()
        password = body.password.get_secret_value()
        if not 10 <= len(password) <= 128 or not re.fullmatch(r"[a-z0-9_]{3,24}", username):
            raise HTTPException(401, "账号或密码不正确。")
        with connect(path) as connection:
            account = connection.execute("SELECT * FROM accounts WHERE username = ? AND is_demo=0", (username,)).fetchone()
        salt, digest = account["password_hash"].split(":") if account else ("00" * 16, "00" * 64)
        valid = hmac.compare_digest(password_digest(password, bytes.fromhex(salt)), digest)
        if not account or not valid:
            raise HTTPException(401, "账号或密码不正确。")
        with connect(path) as connection:
            open_session(connection, request, response, account["id"])
        return public_account(account)

    @router.get("/me")
    def me(request: Request):
        with connect(path) as connection:
            account = current_help_user(connection, request)
            return public_account(account) if account is not None else None

    @router.post("/logout", status_code=204)
    def logout(request: Request, response: Response):
        same_origin(request)
        token = request.cookies.get(COOKIE)
        if token:
            with connect(path) as connection:
                connection.execute("DELETE FROM account_sessions WHERE id = ?", (token_digest(token),))
        response.delete_cookie(COOKIE)

    return router
