import copy

from confmerge import deep_merge


def test_nested_siblings_kept():
    base = {"db": {"host": "localhost", "pool": {"min": 1, "max": 5}}}
    merged = deep_merge(base, {"db": {"pool": {"max": 20}}})
    assert merged == {"db": {"host": "localhost", "pool": {"min": 1, "max": 20}}}


def test_base_not_mutated():
    base = {"db": {"host": "localhost", "pool": {"min": 1, "max": 5}}}
    snapshot = copy.deepcopy(base)
    deep_merge(base, {"db": {"host": "prod", "pool": {"max": 20}}})
    assert base == snapshot


def test_override_not_mutated():
    override = {"db": {"pool": {"max": 20}}}
    snapshot = copy.deepcopy(override)
    deep_merge({"db": {"pool": {"min": 1}}}, override)
    assert override == snapshot


def test_scalar_replaces_dict():
    assert deep_merge({"a": {"b": 1}}, {"a": 5}) == {"a": 5}
