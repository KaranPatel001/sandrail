from versions import compare, latest


def test_minor_numeric():
    assert compare("1.10.0", "1.9.0") == 1


def test_major_numeric():
    assert compare("10.0.0", "9.99.99") == 1


def test_patch_numeric():
    assert compare("0.0.2", "0.0.10") == -1


def test_latest_numeric():
    assert latest(["1.2.0", "1.10.0", "1.9.9"]) == "1.10.0"


def test_prerelease_suffix_ignored():
    assert compare("1.10.0-rc1", "1.9.0") == 1
