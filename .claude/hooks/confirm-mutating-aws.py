#!/usr/bin/env python3
"""Claude Code PreToolUse hook: ask before mutating OpenTofu/Terraform/AWS commands.

Reads the hook event JSON on stdin. For a Bash command that may change infrastructure,
prints a decision of "ask" so the user must confirm. Anything it cannot parse also asks.
Stdlib only, so it runs without the project environment.
"""

import json
import re
import shlex
import sys

IAC_TOOLS = {"tofu", "terraform"}
IAC_MUTATING = {"apply", "destroy", "import", "taint", "untaint"}
IAC_STATE_MUTATING = {"rm", "mv", "push", "replace-provider"}
IAC_FLAGS_WITH_VALUE = {"-chdir"}

AWS_READ_ONLY_PREFIXES = ("describe", "get", "list", "lookup", "head", "batch-get", "validate")
AWS_READ_ONLY_VERBS = {"ls", "wait", "help", "query", "scan"}
AWS_READ_ONLY_COMMANDS = {
    ("configure", "get"),
    ("configure", "list"),
    ("configure", "list-profiles"),
}
AWS_ALWAYS_ASK_SERVICES = {"login", "sso", "configure"}  # configure set/import changes local config
AWS_CHARGED_PER_CALL_SERVICES = {"ce"}  # Cost Explorer: $0.01 a request, even for reads
LIVE_TEST_SWITCH = "VERITY_LIVE_AWS="  # live tests write through boto3, not the aws command
SEED_COMMANDS = {"verity", "verity_core.cli"}  # the script, or `python -m verity_core.cli`
WRITING_COMMANDS = {"seed", "assess"}  # with `--target dynamodb` they write to the real table
SEED_TARGET_AWS = "dynamodb"
LIVE_CRAWL = "crawl"  # without `--local` it invokes the deployed crawler (ADR 0025)
CRAWL_SAFE_FLAGS = {"--local", "--help", "-h"}
SEPARATORS = {"&&", "||", ";", "|", "&", "\n"}


def split_commands(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    commands: list[list[str]] = [[]]
    for token in lexer:
        if token in SEPARATORS or set(token) <= set("&|;"):
            commands.append([])
        else:
            commands[-1].append(token)
    return [c for c in commands if c]


def strip_prefix(tokens: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and wrappers such as env, sudo, command, exec."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok) or tok in {
            "env",
            "sudo",
            "command",
            "exec",
            "time",
            "nohup",
        }:
            i += 1
        else:
            break
    return tokens[i:]


def positional(tokens: list[str]) -> list[str]:
    out, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
        elif tok.split("=")[0] in IAC_FLAGS_WITH_VALUE and "=" not in tok:
            skip = True
        elif not tok.startswith("-"):
            out.append(tok)
    return out


def iac_reason(tool: str, args: list[str]) -> str | None:
    pos = positional(args)
    if not pos:
        return None
    if pos[0] in IAC_MUTATING:
        return f"{tool} {pos[0]} changes real infrastructure"
    if pos[0] == "state" and len(pos) > 1 and pos[1] in IAC_STATE_MUTATING:
        return f"{tool} state {pos[1]} edits state"
    return None


def aws_reason(args: list[str]) -> str | None:
    pos = []
    skip = False
    for tok in args:
        if skip:
            skip = False
        elif tok in {"--profile", "--region", "--output", "--query", "--endpoint-url"}:
            skip = True
        elif not tok.startswith("-"):
            pos.append(tok)
    if not pos:
        return None
    service = pos[0]
    verb = pos[1] if len(pos) > 1 else ""
    if service in AWS_CHARGED_PER_CALL_SERVICES:
        return f"aws {service} is charged per request"
    if (service, verb) in AWS_READ_ONLY_COMMANDS:
        return None
    if service in AWS_ALWAYS_ASK_SERVICES:
        return f"aws {service} changes local credentials or configuration"
    if not verb:
        return None
    if verb in AWS_READ_ONLY_VERBS or verb.startswith(AWS_READ_ONLY_PREFIXES):
        return None
    return f"aws {service} {verb} is not a known read-only call"


def seed_reason(tokens: list[str]) -> str | None:
    """`verity seed|assess --target dynamodb` and `verity crawl` without `--local`, also behind
    `uv run`. They reach AWS through boto3, not the aws command, so the checks above would miss
    them."""
    names = [t.rsplit("/", 1)[-1] for t in tokens]
    start = next((i for i, n in enumerate(names) if n in SEED_COMMANDS), None)
    if start is None:
        return None
    rest = tokens[start:]
    if LIVE_CRAWL in names[start:] and not CRAWL_SAFE_FLAGS & set(rest):
        return "verity crawl without --local runs the deployed crawler on the real account"
    command = next((n for n in names[start:] if n in WRITING_COMMANDS), None)
    if command is None:
        return None
    for i, tok in enumerate(rest):
        if tok == f"--target={SEED_TARGET_AWS}" or (
            tok == "--target" and rest[i + 1 : i + 2] == [SEED_TARGET_AWS]
        ):
            return f"verity {command} --target dynamodb writes to the real table"
    return None


def reason_for(command: str) -> str | None:
    try:
        parts = split_commands(command)
    except ValueError:
        return "command could not be parsed"
    for tokens in parts:
        if any(tok.startswith(LIVE_TEST_SWITCH) for tok in tokens):
            return "VERITY_LIVE_AWS runs tests against the real AWS account"
        if r := seed_reason(tokens):
            return r
        tokens = strip_prefix(tokens)
        if not tokens:
            continue
        exe = tokens[0].rsplit("/", 1)[-1]
        if exe in IAC_TOOLS:
            if r := iac_reason(exe, tokens[1:]):
                return r
        elif exe == "aws" and (r := aws_reason(tokens[1:])):
            return r
        elif exe in {"bash", "sh", "zsh"} and "-c" in tokens:
            idx = tokens.index("-c")
            if idx + 1 < len(tokens) and (r := reason_for(tokens[idx + 1])):
                return r
    return None


def main() -> None:
    try:
        event = json.load(sys.stdin)
        command = event.get("tool_input", {}).get("command", "")
    except (json.JSONDecodeError, AttributeError):
        command, reason = "", "hook input could not be parsed"
    else:
        reason = reason_for(command)
    if reason:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "ask",
                        "permissionDecisionReason": (
                            f"Verity rule: {reason}. Explain what it creates, its verified price "
                            "and how to delete it before approving (CLAUDE.md, hard constraint 3)."
                        ),
                    }
                }
            )
        )


if __name__ == "__main__":
    main()
