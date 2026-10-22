"""API d'administration du catalogue : garde par JWKS, validation, concurrence, image, journaux conformes."""

import io
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from app.catalog.__tests__.admin_fakes import InMemoryImageStorage
from app.catalog.application.archive_product import ArchiveProductUseCase
from app.catalog.application.create_product import CreateProductUseCase
from app.catalog.application.get_admin_product import GetAdminProductUseCase
from app.catalog.application.get_product import GetProductUseCase
from app.catalog.application.list_admin_products import ListAdminProductsUseCase
from app.catalog.application.update_product import UpdateProductUseCase
from app.catalog.application.upload_product_image import (
    MAX_IMAGE_BYTES,
    UploadProductImageUseCase,
)
from app.catalog.infrastructure.models.base import CatalogBase
from app.catalog.infrastructure.repositories.sqlalchemy_admin_product_repository import (
    SqlAlchemyAdminProductRepository,
)
from app.catalog.infrastructure.repositories.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.core.logging.email_pseudonymizer import EmailPseudonymizer
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.customer_identity.__tests__.tokens import AUDIENCE, ISSUER, SigningKey
from app.customer_identity.application.authorize_operator import AuthorizeOperatorUseCase
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.jwks_source import JwksSource
from app.customer_identity.infrastructure.clients.jwks_client_token_verifier import (
    JwksClientTokenVerifier,
)
from app.customer_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache
from app.customer_identity.infrastructure.clients.system_clock import SystemClock
from app.main import create_app

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
BASE = "/admin/products"
AS_OPERATOR = object()  # jeton d'opérateur valide par défaut (None = aucun jeton)
VALID = {
    "name": "Tente Tunnel 4 Saisons",
    "category": "tentes",
    "price_cents": 24900,
    "short_description": "Tente robuste",
    "description": "Une tente pour toutes les saisons.",
    "specs": {"weight_grams": 3200, "material": "Nylon"},
    "stock": 8,
}


class _Jwks(JwksSource):
    def __init__(self, key: SigningKey) -> None:
        self.keys = {key.kid: key.jwk}
        self.down = False

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        if self.down:
            raise VerificationKeysUnavailableError
        return dict(self.keys)


class _Stack:
    def __init__(self) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        CatalogBase.metadata.create_all(self.engine)
        self.key = SigningKey()
        self.jwks = _Jwks(self.key)
        self.stream = io.StringIO()
        self.storage = InMemoryImageStorage()
        events = StructlogBusinessEventLogger("basecamp-shop", self.stream)
        repository = SqlAlchemyAdminProductRepository(self.engine)
        pseudonymizer = EmailPseudonymizer("cle-de-test-pour-les-empreintes")
        verifier = JwksClientTokenVerifier(
            JwksKeyCache(self.jwks, lambda: 1000.0, 300.0, 10.0), ISSUER, AUDIENCE
        )
        self.application = create_app()
        state = self.application.state
        state.authorize_operator_use_case = AuthorizeOperatorUseCase(
            verifier, SystemClock(), events, "face"
        )
        state.list_admin_products_use_case = ListAdminProductsUseCase(repository)
        state.get_admin_product_use_case = GetAdminProductUseCase(repository)
        state.create_product_use_case = CreateProductUseCase(repository, events, pseudonymizer)
        state.update_product_use_case = UpdateProductUseCase(repository, events, pseudonymizer)
        state.archive_product_use_case = ArchiveProductUseCase(repository, events, pseudonymizer)
        state.upload_product_image_use_case = UploadProductImageUseCase(
            repository, self.storage, events, pseudonymizer
        )
        state.get_product_use_case = GetProductUseCase(
            SqlAlchemyProductRepository(self.engine), events
        )

    def token(self, roles: list[str] | None = None, amr: list[str] | None = None) -> str:
        extra: dict[str, Any] = {"roles": roles or ["operator"]}
        extra["amr"] = amr if amr is not None else ["pwd", "face"]
        return self.key.token(extra=extra)

    async def call(
        self,
        method: str,
        path: str,
        *,
        token: object | None = AS_OPERATOR,
        json_body: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        sent = {"X-Correlation-ID": CORRELATION_ID, **(headers or {})}
        if token is AS_OPERATOR:
            token = self.token()
        if token:
            sent["Authorization"] = f"Bearer {token}"
        async with AsyncClient(
            transport=ASGITransport(app=self.application), base_url="http://t"
        ) as client:
            return await client.request(method, path, json=json_body, content=content, headers=sent)

    async def create(self, **overrides: Any) -> dict[str, Any]:
        response = await self.call("POST", BASE, json_body={**VALID, **overrides})
        assert response.status_code == 201, response.text
        return dict(response.json())


@pytest.fixture
def stack() -> Iterator[_Stack]:
    built = _Stack()
    yield built
    built.engine.dispose()


ROUTES = [
    ("GET", BASE),
    ("POST", BASE),
    ("GET", f"{BASE}/x"),
    ("PATCH", f"{BASE}/x"),
    ("POST", f"{BASE}/x/archive"),
    ("POST", f"{BASE}/x/image"),
]


class TestGuard:
    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_without_a_token_every_route_answers_401(
        self, stack: _Stack, method: str, path: str
    ) -> None:
        response = await stack.call(method, path, token=None, json_body={})

        assert response.status_code == 401
        assert response.json() == {"detail": "Authentification requise."}
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_a_forged_expired_or_garbage_token_is_a_401(self, stack: _Stack) -> None:
        foreign = SigningKey("autre").token(extra={"roles": ["operator"], "amr": ["face"]})
        expired = stack.key.token(
            issued_at=1.0, lifetime=60, extra={"roles": ["operator"], "amr": ["face"]}
        )

        for token in ("pas.un.jeton", foreign, expired):
            assert (await stack.call("GET", BASE, token=token)).status_code == 401

    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_a_customer_token_answers_403(
        self, stack: _Stack, method: str, path: str
    ) -> None:
        token = stack.token(roles=["customer"], amr=["pwd", "face"])

        response = await stack.call(method, path, token=token, json_body={})

        assert response.status_code == 403
        assert response.json() == {"detail": "Acces refuse."}

    @pytest.mark.parametrize("amr", [[], ["pwd"], ["pwd", "otp"]])
    async def test_an_operator_without_the_face_factor_answers_403(
        self, stack: _Stack, amr: list[str]
    ) -> None:
        token = stack.token(roles=["operator"], amr=amr)

        assert (await stack.call("GET", BASE, token=token)).status_code == 403
        created = await stack.call("POST", BASE, token=token, json_body=VALID)
        assert created.status_code == 403
        listed = await stack.call("GET", BASE)
        assert listed.json()["total"] == 0  # rien n'a été créé

    async def test_the_operator_with_the_face_factor_is_let_in(self, stack: _Stack) -> None:
        assert (await stack.call("GET", BASE)).status_code == 200

    async def test_without_readable_keys_the_answer_is_503_never_an_access(
        self, stack: _Stack
    ) -> None:
        token = stack.token()
        stack.jwks.down = True

        response = await stack.call("GET", BASE, token=token)

        assert response.status_code == 503 and response.headers["retry-after"] == "5"


class TestCatalogLifecycle:
    async def test_create_read_update_and_list(self, stack: _Stack) -> None:
        created = await stack.create()

        assert (created["id"], created["slug"], created["version"]) == (
            "tente-tunnel-4-saisons",
            "tente-tunnel-4-saisons",
            1,
        )
        assert created["archived_at"] is None and created["image_urls"] == []
        got = await stack.call("GET", f"{BASE}/{created['id']}")
        assert got.json() == created
        patched = await stack.call(
            "PATCH",
            f"{BASE}/{created['id']}",
            json_body={"version": 1, "price_cents": 0, "stock": 3},
        )
        assert patched.status_code == 200
        assert (patched.json()["price_cents"], patched.json()["stock"]) == (0, 3)
        assert patched.json()["version"] == 2
        listed = (await stack.call("GET", BASE)).json()
        assert (listed["total"], [i["id"] for i in listed["items"]]) == (1, [created["id"]])

    async def test_a_stale_version_is_a_409_and_nothing_changes(self, stack: _Stack) -> None:
        created = await stack.create()
        path = f"{BASE}/{created['id']}"
        await stack.call("PATCH", path, json_body={"version": 1, "stock": 5})

        stale = await stack.call("PATCH", path, json_body={"version": 1, "stock": 99})

        assert (stale.status_code, stale.json()) == (409, {"detail": "Version perimee."})
        assert (await stack.call("GET", path)).json()["stock"] == 5

    async def test_the_same_slug_twice_is_a_409_and_an_unknown_product_a_404(
        self, stack: _Stack
    ) -> None:
        await stack.create()

        duplicate = await stack.call("POST", BASE, json_body=VALID)

        assert (duplicate.status_code, duplicate.json()) == (
            409,
            {"detail": "Produit deja existant."},
        )
        assert (await stack.call("GET", f"{BASE}/absent")).status_code == 404
        absent = await stack.call("PATCH", f"{BASE}/absent", json_body={"version": 1, "stock": 1})
        assert absent.status_code == 404
        assert (await stack.call("POST", f"{BASE}/absent/archive")).status_code == 404

    async def test_archiving_hides_the_product_from_customers_but_keeps_it_for_admins(
        self, stack: _Stack
    ) -> None:
        created = await stack.create()
        public = f"/products/{created['slug']}"
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://t"
        ) as client:
            assert (await client.get(public)).status_code == 200

            archived = await stack.call("POST", f"{BASE}/{created['id']}/archive")
            again = await stack.call("POST", f"{BASE}/{created['id']}/archive")

            assert (await client.get(public)).status_code == 404
        assert archived.status_code == 200 and archived.json()["archived_at"] is not None
        assert again.json()["version"] == archived.json()["version"]
        assert (await stack.call("GET", BASE)).json()["total"] == 0
        with_archived = await stack.call("GET", f"{BASE}?include_archived=true")
        assert with_archived.json()["total"] == 1
        edit = await stack.call(
            "PATCH", f"{BASE}/{created['id']}", json_body={"version": 9, "stock": 1}
        )
        assert (edit.status_code, edit.json()) == (409, {"detail": "Produit archive."})


class TestValidation:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"price_cents": -1},
            {"price_cents": 19.9},
            {"price_cents": "100"},
            {"price_cents": True},
            {"stock": -1},
            {"stock": "3"},
            {"stock": 1.5},
            {"name": ""},
            {"name": "x" * 201},
            {"short_description": "x" * 301},
            {"description": ""},
            {"category": "inconnue"},
            {"slug": "Pas Un Slug"},
            {"specs": {"weight_grams": -1}},
            {"specs": {"inconnu": 1}},
            {"id": "force-id"},
            {"rating_value": 5},
            {"archived_at": "2026-01-01T00:00:00Z"},
            {"version": 4},
        ],
    )
    async def test_invalid_creation_is_a_sanitized_422_without_effect(
        self, stack: _Stack, overrides: dict[str, Any]
    ) -> None:
        response = await stack.call("POST", BASE, json_body={**VALID, **overrides})

        assert response.status_code == 422
        assert "inconnue" not in response.text and "force-id" not in response.text
        assert (await stack.call("GET", f"{BASE}?include_archived=true")).json()["total"] == 0

    async def test_missing_required_fields_are_refused(self, stack: _Stack) -> None:
        body = {k: v for k, v in VALID.items() if k != "price_cents"}

        assert (await stack.call("POST", BASE, json_body=body)).status_code == 422

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"stock": 1},
            {"version": 0, "stock": 1},
            {"version": 1},
            {"version": 1, "stock": -1},
            {"version": 1, "slug": "autre"},
            {"version": 1, "images": []},
            {"version": 1, "price_cents": 1.5},
        ],
    )
    async def test_invalid_patch_bodies_are_422(self, stack: _Stack, body: dict[str, Any]) -> None:
        created = await stack.create()

        response = await stack.call("PATCH", f"{BASE}/{created['id']}", json_body=body)

        assert response.status_code == 422
        assert (await stack.call("GET", f"{BASE}/{created['id']}")).json() == created

    async def test_paging_limits_are_validated(self, stack: _Stack) -> None:
        for query in ("limit=0", "limit=101", "offset=-1", "include_archived=peutetre"):
            assert (await stack.call("GET", f"{BASE}?{query}")).status_code == 422


class TestImageUpload:
    async def test_a_real_image_is_stored_and_visible_through_media(self, stack: _Stack) -> None:
        created = await stack.create()

        response = await stack.call(
            "POST",
            f"{BASE}/{created['id']}/image",
            content=JPEG,
            headers={"Content-Type": "image/jpeg"},
        )

        assert response.status_code == 200
        body = response.json()
        (key,) = body["image_keys"]
        assert key.endswith(".jpg") and len(key) == 36
        assert body["image_urls"] == [f"/media/{key}"]
        assert stack.storage.objects[key] == (JPEG, "image/jpeg")
        assert body["version"] == created["version"] + 1

    @pytest.mark.parametrize(
        ("content", "declared"),
        [
            (b"GIF89a" + b"\x00" * 64, "image/gif"),
            (b"<svg onload=alert(1)></svg>", "image/svg+xml"),
            (b"<?php echo 1;", "image/jpeg"),  # déguisé : type annoncé faux
            (b"MZ" + b"\x00" * 64, "image/png"),
            (b"", "image/png"),
        ],
    )
    async def test_a_disguised_or_unsupported_file_is_a_422_without_side_effect(
        self, stack: _Stack, content: bytes, declared: str
    ) -> None:
        created = await stack.create()

        response = await stack.call(
            "POST",
            f"{BASE}/{created['id']}/image",
            content=content,
            headers={"Content-Type": declared},
        )

        assert (response.status_code, response.json()) == (422, {"detail": "Image invalide."})
        assert stack.storage.objects == {}
        assert (await stack.call("GET", f"{BASE}/{created['id']}")).json() == created

    async def test_a_file_over_two_megabytes_is_a_422_without_side_effect(
        self, stack: _Stack
    ) -> None:
        created = await stack.create()
        big = JPEG + b"\x00" * MAX_IMAGE_BYTES

        response = await stack.call("POST", f"{BASE}/{created['id']}/image", content=big)

        assert response.status_code == 422
        assert stack.storage.objects == {}
        assert (await stack.call("GET", f"{BASE}/{created['id']}")).json() == created

    async def test_unknown_products_and_a_storage_outage(self, stack: _Stack) -> None:
        created = await stack.create()
        stack.storage.failing = True

        missing = await stack.call("POST", f"{BASE}/absent/image", content=JPEG)
        outage = await stack.call("POST", f"{BASE}/{created['id']}/image", content=JPEG)

        assert missing.status_code == 404
        assert outage.status_code == 503 and outage.json() == {
            "detail": "Stockage des images indisponible."
        }
        assert (await stack.call("GET", f"{BASE}/{created['id']}")).json() == created


class TestLogs:
    async def test_every_change_is_logged_against_the_schema_without_sensitive_data(
        self, stack: _Stack
    ) -> None:
        created = await stack.create()
        path = f"{BASE}/{created['id']}"
        await stack.call("PATCH", path, json_body={"version": 1, "price_cents": 20000, "stock": 2})
        await stack.call("POST", f"{path}/image", content=JPEG)
        await stack.call("POST", f"{path}/archive")
        await stack.call("GET", BASE, token=None)

        output = stack.stream.getvalue()
        lines = [json.loads(line) for line in output.splitlines() if line.strip()]
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        for line in lines:
            validator.validate(line)
        changes = [line for line in lines if line["event"] == "catalog_admin.change"]
        assert [c["attributes"]["action"] for c in changes] == [
            "create",
            "update",
            "image",
            "archive",
        ]
        update = changes[1]
        assert update["attributes"]["old_price_cents"] == 24900
        assert (
            update["attributes"]["new_price_cents"] == 20000
            and update["attributes"]["new_stock"] == 2
        )
        assert update["actor_type"] == "user" and len(update["actor_id"]) == 16
        assert update["resource_id"] == created["id"]
        assert "Une tente pour toutes les saisons" not in output
        assert "Bearer" not in output


class TestSearch:
    async def test_q_filters_the_list_by_name(self, stack: _Stack) -> None:
        await stack.create(name="Tente Tunnel")
        await stack.create(name="Gourde inox")

        found = (await stack.call("GET", f"{BASE}?q=tunnel")).json()

        assert (found["total"], [i["name"] for i in found["items"]]) == (1, ["Tente Tunnel"])
        assert (await stack.call("GET", f"{BASE}?q=" + "x" * 101)).status_code == 422


class TestOpenApi:
    def test_the_contract_describes_every_admin_route_and_forbids_extra_fields(
        self, stack: _Stack
    ) -> None:
        document = stack.application.openapi()

        paths = document["paths"]
        assert set(paths[BASE]) == {"get", "post"}
        assert set(paths[f"{BASE}/{{product_id}}"]) == {"get", "patch"}
        assert set(paths[f"{BASE}/{{product_id}}/archive"]) == {"post"}
        assert set(paths[f"{BASE}/{{product_id}}/image"]) == {"post"}
        schemas = document["components"]["schemas"]
        for name in ("AdminProductCreateRequest", "AdminProductUpdateRequest", "AdminSpecs"):
            assert schemas[name]["additionalProperties"] is False
        assert "version" in schemas["AdminProductUpdateRequest"]["required"]
