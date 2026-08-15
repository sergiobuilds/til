#!/usr/bin/env python3
"""Validate public study issues against the repo quality gate."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    "## 출처",
    "## Issue Metadata",
    "## TL;DR",
    "## 학습 질문",
    "## 문제의식",
    "## 구조 분해",
    "## 근거",
    "## 비판적 분석",
    "## 분석 관점",
    "## 적용 가능 요소",
    "## 보류할 요소",
    "## 관련 이슈",
    "## Action Items",
]

FORBIDDEN = [
    "copy",
    "copied",
    "copying",
    "카피",
    "베끼",
    "imitation",
    "흡수",
    "훔치",
    "판정: 공개",
    "게시 위치",
    "public-approved",
    "private-required",
    "공개/비공개",
    "Discord source",
    "discord.com/channels",
    "/home/campbell",
    "vault",
    "Vault",
    "셀레네",
    "케이퍼",
]

SENSITIVE_PATTERNS = [
    (re.compile(r"\b(?:public_til|private_queue|needs_confirmation)\b", re.I), "internal destination token"),
    (re.compile(r"`blocked`", re.I), "internal blocked token"),
    (re.compile(r"(?im)^\s*(?:[-*]\s*)?(?:destination|reason)\s*[:|]"), "internal routing field"),
    (re.compile(r"\|\s*(?:destination|reason)\s*\|", re.I), "internal routing table"),
    (re.compile(r"판정\s*:\s*공개|공개\s*가능|공개\s*/\s*비공개|public\s*/\s*private|게시\s*위치"), "public/private decision text"),
    (re.compile(r"\b(?:Kaper|discord\.com/channels|Discord source)\b|케이퍼"), "internal channel reference"),
    (re.compile(r"(?:/home/|/tmp/|/mnt/[a-z]/|/Users/|file://|[A-Za-z]:\\|localhost|127\.0\.0\.1)"), "local path or local URL"),
    (re.compile(r"\b(?:vault|blonde\.svvys\.com|youtube-digest|digest_artifact)\b|file sha256", re.I), "internal artifact reference"),
    (re.compile(r"나정환|shaun0927|sharingan", re.I), "internal analysis target"),
    (re.compile(r"그대로\s*(?:가져|쓰)|따라\s*쓰|흡수|내재화|이식"), "copy-style expression"),
]


def gh_json(args: list[str]) -> object:
    return json.loads(subprocess.check_output(["gh", *args], text=True))


def contains_forbidden(text: str, needle: str) -> bool:
    if needle.isascii():
        return needle.lower() in text.lower()
    return needle in text


def sensitive_hits(text: str) -> list[str]:
    return [label for pattern, label in SENSITIVE_PATTERNS if pattern.search(text)]


def validate_content(
    ident: str,
    title: str,
    body: str,
    comment_text: str,
    min_body: int,
    min_comment: int,
) -> list[str]:
    errors: list[str] = []
    full_text = f"{title}\n{body}\n{comment_text}"

    if not body.startswith("## 출처"):
        errors.append(f"{ident}: body must start with ## 출처")

    if len(body) < min_body:
        errors.append(f"{ident}: body too short ({len(body)} < {min_body})")

    if len(comment_text) < min_comment:
        errors.append(f"{ident}: comments too short ({len(comment_text)} < {min_comment})")

    for section in REQUIRED_SECTIONS:
        if section not in body:
            errors.append(f"{ident}: missing section {section}")

    for forbidden in FORBIDDEN:
        if contains_forbidden(full_text, forbidden):
            errors.append(f"{ident}: forbidden term {forbidden}")

    for hit in sensitive_hits(full_text):
        errors.append(f"{ident}: sensitive public-surface pattern {hit}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="myeolkoreaseoul/til")
    parser.add_argument("--min-body", type=int, default=3500)
    parser.add_argument("--min-comment", type=int, default=900)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--title", default="local study packet")
    parser.add_argument("--body-file")
    parser.add_argument("--comment-file")
    parser.add_argument("--state", default="all", choices=["open", "closed", "all"])
    args = parser.parse_args()

    if args.comment_file and not args.body_file:
        parser.error("--body-file is required with --comment-file")

    if args.body_file:
        if not args.comment_file:
            parser.error("--comment-file is required with --body-file")

        body = Path(args.body_file).read_text(encoding="utf-8")
        comment_text = Path(args.comment_file).read_text(encoding="utf-8")
        errors = validate_content(
            "local packet",
            args.title,
            body,
            comment_text,
            args.min_body,
            args.min_comment,
        )

        if errors:
            print("\n".join(errors))
            return 1

        print("ok: checked local packet")
        return 0

    issues = gh_json(
        [
            "issue",
            "list",
            "-R",
            args.repo,
            "--state",
            args.state,
            "--limit",
            str(args.limit),
            "--json",
            "number,title,body",
        ]
    )

    errors: list[str] = []
    for issue in sorted(issues, key=lambda item: item["number"]):
        number = issue["number"]
        body = issue.get("body") or ""
        comments = gh_json(
            [
                "api",
                f"repos/{args.repo}/issues/{number}/comments",
                "--paginate",
            ]
        )
        comment_text = "\n".join(comment.get("body") or "" for comment in comments)
        errors.extend(
            validate_content(
                f"#{number}",
                issue.get("title") or "",
                body,
                comment_text,
                args.min_body,
                args.min_comment,
            )
        )

    if errors:
        print("\n".join(errors))
        return 1

    print(f"ok: checked {len(issues)} issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
