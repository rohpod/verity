"""What shows an AI capability being used (architecture section D, stage 6; ADR 0021, decision
9). Pure.

`check_vc060` answers "are the AI permissions that were granted ever exercised?" from CloudTrail
only. `U#` usage records are never counted here: the demo's come from a mock, and counting them
would hide the seeded unused `bedrock:Converse` grant.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from verity_core.discovery.boundary import CollectedRole, Statement, TrailEvent
from verity_core.model.usage import UsageRecord

CONTROL = "ctl:VC-060"


def _overlaps(granted: str, ai_action: str) -> bool:
    """A grant covers an AI action in either direction, ignoring case: `bedrock:*` and `*` cover
    `bedrock:Invoke*`, and `bedrock:InvokeModel` falls under it."""
    a, b = granted.lower(), ai_action.lower()
    return fnmatchcase(b, a) or fnmatchcase(a, b)


def granted_ai_actions(
    ai_actions: Collection[str], statements: Iterable[Statement]
) -> tuple[str, ...]:
    """The granted actions, as written, that overlap an AI action. Only `Allow` counts, and a
    `NotAction` statement is ignored."""
    return tuple(
        sorted(
            {
                action
                for s in statements
                if s.effect == "Allow" and not s.negated
                for action in s.actions
                if any(_overlaps(action, ai) for ai in ai_actions)
            }
        )
    )


def trail_action(event: TrailEvent) -> str:
    """`bedrock.amazonaws.com` and `Converse` give `bedrock:Converse`."""
    return f"{event.event_source.partition('.')[0]}:{event.event_name}"


def trail_shows_ai(
    role_name: str | None, events: Iterable[TrailEvent], sources: Collection[str]
) -> bool:
    return role_name is not None and any(
        e.role_name == role_name and e.event_source in sources for e in events
    )


def usage_shows_ai(records: Sequence[UsageRecord]) -> bool:
    return len(records) > 0


@dataclass(frozen=True)
class Vc060:
    granted: tuple[str, ...]
    unused: tuple[str, ...]
    unparsed: bool

    @property
    def outcome(self) -> str:
        return "fail" if self.unused else "pass"

    def content(self, system_id: str) -> dict:
        """The Evidence content. `control` and `scope` are what the assessor matches on."""
        return {
            "control": CONTROL,
            "scope": system_id,
            "outcome": self.outcome,
            "granted": list(self.granted),
            "unused": list(self.unused),
            "unparsed": self.unparsed,
        }


def check_vc060(
    ai_actions: Collection[str],
    roles: Iterable[CollectedRole],
    events: Iterable[TrailEvent],
    sources: Collection[str],
) -> Vc060:
    """A grant is unused if no event of its own role calls an action it covers."""
    events = [e for e in events if e.event_source in sources]
    granted: set[str] = set()
    unused: set[str] = set()
    unparsed = False
    for role in roles:
        own = [trail_action(e).lower() for e in events if e.role_name == role.name]
        for grant in granted_ai_actions(ai_actions, role.statements):
            granted.add(grant)
            if not any(fnmatchcase(action, grant.lower()) for action in own):
                unused.add(grant)
        unparsed = unparsed or any(s.effect == "Allow" and s.negated for s in role.statements)
    return Vc060(tuple(sorted(granted)), tuple(sorted(unused)), unparsed)
