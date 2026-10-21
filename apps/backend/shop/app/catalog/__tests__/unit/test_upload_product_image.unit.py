"""Téléversement d'image : type vérifié sur le contenu, taille bornée, nom aléatoire, aucun effet si refusé."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.catalog.__tests__.admin_fakes import (
    OPERATOR_ID,
    InMemoryAdminProducts,
    InMemoryImageStorage,
)
from app.catalog.__tests__.product_factory import make_product
from app.catalog.application.image_storage_unavailable_error import ImageStorageUnavailableError
from app.catalog.application.invalid_image_upload_error import InvalidImageUploadError
from app.catalog.application.product_conflict_error import ProductConflictError
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.application.upload_product_image import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_PRODUCT,
    UploadProductImageUseCase,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger

OPERATOR = UUID(OPERATOR_ID)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 " + b"\x00" * 32


class _Pseudonymizer:
    def pseudonymize(self, value: str) -> str:
        return "pseudo"


class _Setup:
    def __init__(self, storage: InMemoryImageStorage | None = None) -> None:
        self.product = make_product("tente")
        self.repository = InMemoryAdminProducts(self.product)
        self.storage = storage or InMemoryImageStorage()
        self.events = InMemoryBusinessEventLogger()
        self.tokens = iter(f"{n:032x}" for n in range(1, 100))
        self.use_case = UploadProductImageUseCase(
            self.repository,
            self.storage,
            self.events,
            _Pseudonymizer(),
            key_factory=lambda: next(self.tokens),
        )


class TestAcceptedImages:
    @pytest.mark.parametrize(
        ("content", "extension", "content_type"),
        [(JPEG, "jpg", "image/jpeg"), (PNG, "png", "image/png"), (WEBP, "webp", "image/webp")],
    )
    def test_a_real_image_is_stored_under_a_random_key_and_added_to_the_product(
        self, content: bytes, extension: str, content_type: str
    ) -> None:
        setup = _Setup()

        product = setup.use_case.execute(OPERATOR, setup.product.id, content)

        key = f"{1:032x}.{extension}"
        assert product.image_keys[-1] == key
        assert setup.storage.objects[key] == (content, content_type)
        assert product.version == setup.product.version + 1
        assert setup.events.events[-1].attributes["action"] == "image"

    def test_the_key_never_comes_from_the_client(self) -> None:
        setup = _Setup()

        first = setup.use_case.execute(OPERATOR, setup.product.id, JPEG)
        second = setup.use_case.execute(OPERATOR, setup.product.id, JPEG)

        assert first.image_keys[-1] != second.image_keys[-1]
        assert setup.product.slug not in second.image_keys[-1]

    def test_the_size_limit_is_two_megabytes_inclusive(self) -> None:
        setup = _Setup()
        at_limit = JPEG + b"\x00" * (MAX_IMAGE_BYTES - len(JPEG))

        setup.use_case.execute(OPERATOR, setup.product.id, at_limit)

        assert len(setup.storage.objects) == 1


class TestRefusedWithoutSideEffect:
    @pytest.mark.parametrize(
        "content",
        [
            b"",
            b"GIF89a" + b"\x00" * 64,
            b"<svg onload='alert(1)'></svg>",
            b"<?php system($_GET['c']); ?>",
            b"MZ\x90\x00" + b"\x00" * 64,
            b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 32,
            b"\xff\xd8",
            JPEG + b"\x00" * MAX_IMAGE_BYTES,
        ],
        ids=["empty", "gif", "svg", "php", "exe", "wav", "truncated", "too_large"],
    )
    def test_a_file_that_is_not_an_accepted_image_or_is_too_big_changes_nothing(
        self, content: bytes
    ) -> None:
        setup = _Setup()

        with pytest.raises(InvalidImageUploadError):
            setup.use_case.execute(OPERATOR, setup.product.id, content)

        assert setup.storage.objects == {}
        assert setup.repository.get(setup.product.id) == setup.product
        assert setup.events.events == []

    def test_unknown_or_archived_products_never_receive_a_file(self) -> None:
        setup = _Setup()
        setup.repository.archive(setup.product.id, datetime(2026, 10, 22, tzinfo=UTC))

        with pytest.raises(ProductNotFoundError):
            setup.use_case.execute(OPERATOR, "absent", JPEG)
        with pytest.raises(ProductConflictError) as error:
            setup.use_case.execute(OPERATOR, setup.product.id, JPEG)

        assert error.value.reason == "product_archived"
        assert setup.storage.objects == {}

    def test_a_product_with_ten_images_refuses_an_eleventh_before_storing_it(self) -> None:
        setup = _Setup()
        room = MAX_IMAGES_PER_PRODUCT - len(setup.product.image_keys)
        for _ in range(room):
            setup.use_case.execute(OPERATOR, setup.product.id, PNG)

        with pytest.raises(ProductConflictError) as error:
            setup.use_case.execute(OPERATOR, setup.product.id, PNG)

        assert error.value.reason == "too_many_images"
        assert len(setup.storage.objects) == room

    def test_a_storage_outage_is_reported_and_the_product_is_untouched(self) -> None:
        setup = _Setup(InMemoryImageStorage(failing=True))

        with pytest.raises(ImageStorageUnavailableError):
            setup.use_case.execute(OPERATOR, setup.product.id, JPEG)

        assert setup.repository.get(setup.product.id) == setup.product
