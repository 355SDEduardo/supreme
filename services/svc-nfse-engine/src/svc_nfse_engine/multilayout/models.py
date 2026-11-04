from dataclasses import dataclass
@dataclass(frozen=True)
class ParseIssue:
    filename: str
    message: str
