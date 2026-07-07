class StandardDefinition:
    key: str
    name: str
    year: int | None
    parent: str | None
    digits: int
    part_shift: int
    part_digits: int
    clauses: list[ClauseDefinition]
