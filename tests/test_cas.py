from vigil.cas import canonical_bytes, canonical_digest, cas_uri, short_id


def test_canonical_bytes_is_order_insensitive():
    a = {"b": 1, "a": {"y": 2, "x": 3}}
    b = {"a": {"x": 3, "y": 2}, "b": 1}
    assert canonical_bytes(a) == canonical_bytes(b)


def test_canonical_bytes_is_whitespace_free():
    assert b", " not in canonical_bytes({"a": 1, "b": 2})
    assert b": " not in canonical_bytes({"a": 1, "b": 2})


def test_digest_stable_across_key_order():
    assert canonical_digest({"a": 1, "b": 2}) == canonical_digest({"b": 2, "a": 1})


def test_cas_uri_prefix():
    assert cas_uri({"a": 1}).startswith("cas://sha256/")


def test_short_id_truncates():
    assert len(short_id(canonical_digest({"a": 1}), 12)) == 12
