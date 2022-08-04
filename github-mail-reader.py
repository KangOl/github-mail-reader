#!/usr/bin/env python3
from textwrap import shorten
from functools import lru_cache

import requests
import tomli
from imap_tools import MailBox, AND, MailMessageFlags
from rich.progress import track

with open("config.toml", "rb") as fp:
    config = tomli.load(fp)["github-mail-reader"]


@lru_cache(128)
def pull_state(owner, repo, kind, number):
    if kind == "pull":
        kind = "pulls"
    elif kind != "issues":
        # can be `check-suites`
        return None

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {config['gh_token']}",
    }
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/{kind}/{number}", headers=headers
    )
    resp.raise_for_status()
    return resp.json()["state"]


def ref_data(reference):
    if "/security-advisories@" in reference:
        return None, None
    owner, repo, kind, number = (
        reference.lstrip("< ").rstrip(" >").partition("@")[0].split("/", 3)
    )
    state = pull_state(owner, repo, kind, number)
    return f"{owner}/{repo}#{number}", state


with MailBox(config["server"]).login(
    config["login"], config["password"], initial_folder=config["folder"]
) as box:

    criteria = AND(from_="notifications@github.com", seen=False)

    count = len(box.numbers(criteria))
    print(f"{count} unread emails found")

    msgs = box.fetch(
        criteria,
        limit=None,
        mark_seen=False,
        headers_only=True,
        bulk=True,
    )

    for msg in track(msgs, total=count):
        ref = msg.headers.get("references", msg.headers["message-id"])[0]
        pr, state = ref_data(ref)
        if state in {"closed", "merged"}:
            subject = shorten(msg.subject, 80, placeholder="…")
            print(f"mark message {subject!r} as seen because {pr} is {state}")
            box.flag([msg.uid], MailMessageFlags.SEEN, True)
