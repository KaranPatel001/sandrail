from textkit import slugify


def test_simple_title():
    assert slugify("Hello World") == "hello-world"


def test_lowercases():
    assert slugify("PYTHON") == "python"
