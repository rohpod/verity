"""What shows an AI capability being used (architecture section D, stage 6; ADR 0021, decision
9, and ADR 0022). Pure.

`check_vc060` answers "are the AI permissions that were granted ever exercised?" from CloudTrail
only. `U#` usage records are never counted here: the demo's come from a mock, and counting them
would hide the seeded unused `bedrock:InvokeModel` grant. A call that failed or was refused
carries an `errorCode` and proves nothing (ADR 0025, decision 3).
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from verity_core.content.schema import AiAction
from verity_core.discovery.boundary import CollectedRole, Statement, TrailEvent
from verity_core.model.usage import UsageRecord

CONTROL = "ctl:VC-060"
SERVICE_EVENT = "AwsServiceEvent"  # something AWS did, not a call


def _matches(action: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(action.lower(), p.lower()) for p in patterns)


def granted_ai_actions(
    ai_actions: Collection[AiAction], statements: Iterable[Statement]
) -> tuple[str, ...]:
    """The listed AI actions the statements grant, sorted. An `Allow` statement grants an action
    if one of its `Action` patterns matches, or, for `NotAction`, if none of its patterns do.
    `Deny` is not subtracted, which errs towards reporting a grant."""
    granted = {
        listed.action
        for s in statements
        if s.effect == "Allow"
        for listed in ai_actions
        if _matches(listed.action, s.actions) != s.not_action
    }
    return tuple(sorted(granted))


def trail_shows_ai(
    role_name: str | None, events: Iterable[TrailEvent], sources: Collection[str]
) -> bool:
    return role_name is not None and any(
        e.role_name == role_name
        and e.event_source in sources
        and e.event_type != SERVICE_EVENT
        and e.error_code is None
        for e in events
    )


def usage_shows_ai(records: Sequence[UsageRecord]) -> bool:
    return len(records) > 0


def _proves(event: TrailEvent, action: AiAction) -> bool:
    """A call to the action: from its service, by name, not a service event, and not one that
    failed or was refused."""
    service = action.action.partition(":")[0]
    return (
        event.event_type != SERVICE_EVENT
        and event.error_code is None
        and event.event_source.partition(".")[0] == service
        and event.event_name.lower() in {name.lower() for name in action.trail_events}
    )


@dataclass(frozen=True)
class Vc060:
    granted: tuple[str, ...]
    unused: tuple[str, ...]  # granted, event history could show it, and nothing did
    unverifiable: tuple[str, ...]  # granted, and event history cannot show it
    roles_unseen: int  # roles of the system's functions that the crawler cannot read

    @property
    def outcome(self) -> str:
        if self.unused:
            return "fail"
        return "inconclusive" if self.unverifiable or self.roles_unseen else "pass"

    def content(self, system_id: str) -> dict:
        """The Evidence content. `control` and `scope` are what the assessor matches on."""
        return {
            "control": CONTROL,
            "scope": system_id,
            "outcome": self.outcome,
            "granted": list(self.granted),
            "unused": list(self.unused),
            "unverifiable": list(self.unverifiable),
            "roles_unseen": self.roles_unseen,
        }


def check_vc060(
    ai_actions: Collection[AiAction],
    roles: Iterable[CollectedRole],
    events: Iterable[TrailEvent],
    sources: Collection[str],
    roles_unseen: int = 0,
) -> Vc060:
    """`fail` if a granted action has no event from the role that grants it, `inconclusive` if
    one cannot be checked or a role cannot be seen, otherwise `pass` (ADR 0022, decision 3). Each
    role is judged by its own events, so one role's use does not excuse another's grant."""
    events = [e for e in events if e.event_source in sources]
    by_name = {a.action: a for a in ai_actions}
    granted: set[str] = set()
    unused: set[str] = set()
    unverifiable: set[str] = set()
    for role in roles:
        own = [e for e in events if e.role_name == role.name]
        for name in granted_ai_actions(ai_actions, role.statements):
            action = by_name[name]
            granted.add(name)
            if not action.trail_events:
                unverifiable.add(name)
            elif not any(_proves(e, action) for e in own):
                unused.add(name)
    return Vc060(
        tuple(sorted(granted)), tuple(sorted(unused)), tuple(sorted(unverifiable)), roles_unseen
    )
