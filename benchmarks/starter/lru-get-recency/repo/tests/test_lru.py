from cachekit import LRUCache


def test_put_and_get():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing", 0) == 0


def test_capacity_respected():
    cache = LRUCache(1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert len(cache) == 1
    assert "b" in cache
