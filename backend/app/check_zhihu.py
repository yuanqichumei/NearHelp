"""Print titles and links returned by the official hot-list API."""

import os
import sys

from .zhihu import ZhihuError, fetch_hot_list


def main() -> int:
    try:
        result = fetch_hot_list()
    except ZhihuError as error:
        print(error, file=sys.stderr)
        return 1

    secret = os.environ["ZHIHU_ACCESS_SECRET"].strip()
    print(f"知乎热榜返回 {len(result.items)} 条，Data.Total={result.total}")
    for item in result.items:
        title = " ".join(item.title.split()).replace(secret, "[已隐藏]")
        url = item.url.replace(secret, "[已隐藏]")
        print(f"{title}\n{url}")
    if not result.items:
        print("接口请求成功，但热榜为空。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
