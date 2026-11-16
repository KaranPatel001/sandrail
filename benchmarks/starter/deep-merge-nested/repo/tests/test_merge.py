from confmerge import deep_merge


def test_flat_override():
    assert deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}


def test_new_keys_added():
    assert deep_merge({"a": 1}, {"c": 4}) == {"a": 1, "c": 4}
