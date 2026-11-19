"""Record an editorial hot topic in the default community."""

import argparse

from .config import database_path
from .db import DEFAULT_COMMUNITY, connect, initialize
from .hot_topics import MANUAL, save_hot_topic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument("url")
    args = parser.parse_args()
    path = database_path()
    initialize(path)
    try:
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            topic_id = save_hot_topic(connection, DEFAULT_COMMUNITY, MANUAL, args.title, args.url)
    except ValueError as error:
        parser.error(str(error))
    print(f"/topics/{topic_id}")


if __name__ == "__main__":
    main()
