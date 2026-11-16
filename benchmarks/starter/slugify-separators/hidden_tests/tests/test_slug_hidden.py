from textkit import slugify


def test_punctuation_collapses():
    assert slugify("Hello, World!") == "hello-world"


def test_multiple_spaces():
    assert slugify("a   b    c") == "a-b-c"


def test_accents_removed():
    assert slugify("Crème Brûlée") == "creme-brulee"


def test_custom_separator():
    assert slugify("Hello,  World", sep="_") == "hello_world"


def test_no_leading_or_trailing_separator():
    assert slugify("  --Draft: v2--  ") == "draft-v2"
