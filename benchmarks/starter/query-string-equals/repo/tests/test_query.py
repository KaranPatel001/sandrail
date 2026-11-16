from urlkit import parse_query


def test_basic():
    assert parse_query("a=1&b=2") == {"a": ["1"], "b": ["2"]}


def test_leading_question_mark():
    assert parse_query("?q=x") == {"q": ["x"]}
