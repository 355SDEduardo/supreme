"""Conservative one-to-one source matching and per-field factual provenance."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from difflib import SequenceMatcher

from .statement_parsers import normalized
from .statement_types import Candidate, Group, ParsedSource

PRIORITY = {'ofx': 4, 'xlsx': 3, 'csv': 2, 'pdf': 1}


def signature(row: Candidate | Group) -> tuple:
    return row.date, row.amount, row.type


def refresh(group: Group) -> None:
    for field in ('date', 'amount', 'type'):
        choices = sorted(group.candidates, key=lambda c: (-c.quality[field], -PRIORITY[c.format], c.id))
        best = choices[0]
        if any(c.quality[field] == best.quality[field] and getattr(c, field) != getattr(best, field)
               for c in choices[1:]):
            issue = f'Divergência de {field} entre fontes com a mesma qualidade; revise os documentos.'
            if issue not in group.issues:
                group.issues.append(issue)
        setattr(group, field, getattr(best, field))
        group.field_sources[field] = best.id


def new_group(row: Candidate) -> Group:
    group = Group(id=hashlib.sha256(row.id.encode()).hexdigest()[:32], date=row.date,
                  amount=row.amount, type=row.type, candidates=[row], field_sources={})
    refresh(group)
    return group


def similarity(row: Candidate, group: Group) -> float:
    result = 0.0
    for candidate in group.candidates:
        if (row.reference and row.reference == candidate.reference
                and row.reference_kind == candidate.reference_kind):
            return 2.0
        a, b = normalized(row.description), normalized(candidate.description)
        score = SequenceMatcher(None, a, b).ratio()
        if a in b or b in a:
            score = max(score, .85)
        result = max(result, score)
    return result


def merge_sources(sources: list[ParsedSource]) -> list[Group]:
    groups: list[Group] = []
    for source in sorted(sources, key=lambda s: (-PRIORITY[s.format], -len(s.rows), s.sha256)):
        remaining = []
        for row in source.rows:
            anchors = [g for g in groups if row.reference_kind == 'fitid' and row.reference
                       and any(c.reference_kind == 'fitid' and c.reference == row.reference for c in g.candidates)]
            if len(anchors) == 1 and all(c.source_id != source.id for c in anchors[0].candidates):
                anchors[0].candidates.append(row)
                refresh(anchors[0])
            else:
                if anchors:
                    raise ValueError('FITID repetido ou ambíguo dentro da mesma fonte.')
                remaining.append(row)
        buckets: dict[tuple, list[Candidate]] = defaultdict(list)
        for row in remaining:
            buckets[signature(row)].append(row)
        for key, rows in buckets.items():
            available = [g for g in groups if signature(g) == key
                         and all(c.source_id != source.id for c in g.candidates)]
            if not available:
                groups.extend(new_group(row) for row in rows)
                continue
            if len(rows) == len(available) == 1:
                available[0].candidates.append(rows[0])
                refresh(available[0])
                continue
            unmatched = list(rows)
            # Unique reciprocal text/reference matches identify records; they do not select the final text.
            for row in list(unmatched):
                scores = [(similarity(row, g), g) for g in available]
                if not scores:
                    break
                scores.sort(key=lambda p: p[0], reverse=True)
                best_score, best = scores[0]
                competition = [similarity(other, best) for other in unmatched if other.id != row.id]
                if (best_score >= .65 and (len(scores) == 1 or best_score > scores[1][0] + .08)
                        and (not competition or best_score > max(competition) + .08)):
                    best.candidates.append(row)
                    refresh(best)
                    available.remove(best)
                    unmatched.remove(row)
            if unmatched and available:
                indistinguishable = len({normalized(r.description) for r in unmatched}) == 1 and all(
                    any(normalized(c.description) == normalized(unmatched[0].description) for c in g.candidates)
                    for g in available)
                if indistinguishable and len(unmatched) == len(available):
                    for row, group in zip(unmatched, available):
                        group.candidates.append(row)
                        refresh(group)
                    unmatched = []
                else:
                    issue = 'Movimentos com mesma data/valor/tipo não puderam ser pareados com segurança.'
                    for group in available:
                        group.issues.append(issue)
                    for row in unmatched:
                        group = new_group(row)
                        group.issues.append(issue)
                        groups.append(group)
                    unmatched = []
            groups.extend(new_group(row) for row in unmatched)
    for group in groups:
        if all(c.currency != 'BRL' for c in group.candidates):
            group.issues.append('Moeda OFX BRC inconsistente: anexe uma fonte em reais que comprove o valor.')
    return sorted(groups, key=lambda group: (group.date, group.id))
