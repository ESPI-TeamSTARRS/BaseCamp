"""Stockage S3 : signature SigV4 (vecteur publié par AWS), requête PUT et pannes converties."""

from datetime import UTC, datetime

import httpx
import pytest

from app.catalog.domain.errors.image_storage_error import ImageStorageError
from app.catalog.infrastructure.storage.s3_product_image_storage import S3ProductImageStorage
from app.catalog.infrastructure.storage.sigv4_signer import Sigv4Signer

# Clés d'exemple publiées dans la documentation AWS (aucun secret réel).
AWS_EXAMPLE_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_EXAMPLE_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
NOW = datetime(2013, 5, 24, 0, 0, tzinfo=UTC)


class TestSigv4Signer:
    def test_reproduces_the_aws_documentation_get_object_example(self) -> None:
        signer = Sigv4Signer(AWS_EXAMPLE_ID, AWS_EXAMPLE_KEY, "us-east-1", "s3")

        authorization = signer.authorization(
            "GET",
            "/test.txt",
            {
                "host": "examplebucket.s3.amazonaws.com",
                "range": "bytes=0-9",
                "x-amz-content-sha256": EMPTY_SHA256,
                "x-amz-date": "20130524T000000Z",
            },
            EMPTY_SHA256,
            NOW,
        )

        assert authorization == (
            "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
            "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
        )

    def test_the_signature_changes_with_the_payload_and_the_key(self) -> None:
        headers = {
            "host": "h",
            "x-amz-content-sha256": EMPTY_SHA256,
            "x-amz-date": "20130524T000000Z",
        }
        one = Sigv4Signer("id", "secret-one", "us-east-1", "s3")
        two = Sigv4Signer("id", "secret-two", "us-east-1", "s3")

        assert one.authorization("PUT", "/b/k", headers, EMPTY_SHA256, NOW) != two.authorization(
            "PUT", "/b/k", headers, EMPTY_SHA256, NOW
        )
        assert one.authorization("PUT", "/b/k", headers, EMPTY_SHA256, NOW) != one.authorization(
            "PUT", "/b/other", headers, EMPTY_SHA256, NOW
        )


def _storage(handler: httpx.MockTransport, secret: str = "s3-secret") -> S3ProductImageStorage:  # noqa: S107
    return S3ProductImageStorage(
        httpx.Client(transport=handler),
        endpoint="http://seaweedfs:8333",
        bucket="product-images",
        access_key="s3-access",
        secret_key=secret,
        region="us-east-1",
        clock=lambda: NOW,
    )


class TestS3ProductImageStorage:
    def test_puts_the_object_signed_in_the_bucket_with_its_content_type(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        _storage(httpx.MockTransport(handler)).store("abc.jpg", b"\xff\xd8\xffdata", "image/jpeg")

        (request,) = seen
        assert (request.method, str(request.url)) == (
            "PUT",
            "http://seaweedfs:8333/product-images/abc.jpg",
        )
        assert request.headers["content-type"] == "image/jpeg"
        assert request.content == b"\xff\xd8\xffdata"
        assert request.headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=s3-access/20130524/us-east-1/s3/aws4_request"
        )
        assert "s3-secret" not in request.headers["authorization"]

    @pytest.mark.parametrize("status", [403, 404, 500, 503])
    def test_a_refusal_or_an_outage_becomes_a_storage_error(self, status: int) -> None:
        storage = _storage(httpx.MockTransport(lambda request: httpx.Response(status)))

        with pytest.raises(ImageStorageError):
            storage.store("abc.jpg", b"x", "image/jpeg")

    def test_an_unreachable_server_becomes_a_storage_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refusé")

        with pytest.raises(ImageStorageError):
            _storage(httpx.MockTransport(handler)).store("abc.jpg", b"x", "image/jpeg")

    def test_without_configured_keys_nothing_is_sent(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200)

        storage = _storage(httpx.MockTransport(handler), "")

        with pytest.raises(ImageStorageError):
            storage.store("abc.jpg", b"x", "image/jpeg")

        assert calls == []
