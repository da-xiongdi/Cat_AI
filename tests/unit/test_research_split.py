import pytest

from catalyst_ai.datasets.research_split import partition


def test_groups_folds_and_replay():
    rows = [{'record_id': str(i), 'doi': str(i // 2), 'repeat_group': 'r' if i in (0, 2) else ''} for i in range(20)]
    for strategy in ('random', 'doi'):
        p = partition(rows, strategy=strategy, folds=3)
        assert p == partition(list(reversed(rows)), strategy=strategy, folds=3)
        assert set(p['train']).isdisjoint(p['test'])
        assert set(p['train']) | set(p['test']) == {r['record_id'] for r in rows}
        assert sorted(x for fold in p['validation_folds'] for x in fold) == p['train']
        for group in p['groups']:
            assert set(group) <= set(p['train']) or set(group) <= set(p['test'])
            assert sum(bool(set(group) & set(f)) for f in p['validation_folds']) <= 1
        if strategy == 'doi':
            assert any({'0', '1', '2', '3'} <= set(g) for g in p['groups'])


def test_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        partition([{'record_id': 'x', 'doi': ''}], strategy='doi')
