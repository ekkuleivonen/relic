import pytest

from domain.auth.bearer import parse_bearer_access_key


@pytest.mark.parametrize(
    ("authorization", "expected"),
    [
        (None, None),
        ("", None),
        ("Basic abc", None),
        ("Bearer", None),
        ("Bearer no-colon", None),
        ("Bearer :secret", None),
        ("Bearer RK123:", None),
        (
            "Bearer RKABCDEF:super-secret",
            ("RKABCDEF", "super-secret"),
        ),
        (
            "bearer rk1:secret-with:colons",
            ("rk1", "secret-with:colons"),
        ),
    ],
)
def test_parse_bearer_access_key(authorization, expected):
    assert parse_bearer_access_key(authorization) == expected
