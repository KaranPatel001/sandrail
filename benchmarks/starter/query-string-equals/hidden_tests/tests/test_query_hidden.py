from urlkit import parse_query


def test_value_with_equals():
    assert parse_query("sig=abc==&next=/home") == {"sig": ["abc=="], "next": ["/home"]}


def test_value_with_inner_equals():
    assert parse_query("expr=a=b") == {"expr": ["a=b"]}


def test_plus_and_percent():
    assert parse_query("q=hello+world%21") == {"q": ["hello world!"]}


def test_repeated_and_bare_keys():
    assert parse_query("tag=a&tag=b&flag") == {"tag": ["a", "b"], "flag": [""]}
