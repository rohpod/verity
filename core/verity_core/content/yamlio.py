"""Reading one YAML content file into a model, with errors that name the file."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError


class ContentError(ValueError):
    """A content file that cannot be read. The message names the file."""

    def __init__(self, path: Path, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path


class UniqueKeyLoader(yaml.SafeLoader):
    """`yaml.safe_load` silently keeps the last of two equal keys. In content that would drop
    a mapping without a trace, so it is an error."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


@contextmanager
def reading(path: Path) -> Iterator[None]:
    try:
        yield
    except ContentError:
        raise
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in exc.errors()
        )
        raise ContentError(path, details) from exc
    except (ValueError, yaml.YAMLError) as exc:
        raise ContentError(path, str(exc)) from exc


def parse[M: BaseModel](path: Path, model: type[M]) -> M:
    with reading(path):
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)  # noqa: S506
        return model.model_validate(data)
