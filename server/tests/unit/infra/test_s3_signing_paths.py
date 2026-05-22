from infra.auth.s3_signing import canonical_request_path


def test_canonical_request_path_encodes_decoded_spaces() -> None:
    assert (
        canonical_request_path("/s3/relic/Local Testing/file.csv")
        == "/s3/relic/Local%20Testing/file.csv"
    )


def test_canonical_request_path_does_not_double_encode_percent_twenty() -> None:
    """Proxy stacks may leave %20 literal in request.url.path."""
    assert (
        canonical_request_path("/s3/relic/Local%20Testing/file.csv")
        == "/s3/relic/Local%20Testing/file.csv"
    )


def test_canonical_request_path_preserves_slashes() -> None:
    assert (
        canonical_request_path("/s3/relic/photos/2024/cat.jpg")
        == "/s3/relic/photos/2024/cat.jpg"
    )
