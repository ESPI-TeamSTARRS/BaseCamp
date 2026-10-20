"""Parcours catalogue sur la pile complete : API, images du bucket et pages du front."""

import os
import re
from collections import Counter
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
CATEGORIES = {"tentes", "couchage", "sacs-a-dos", "cuisine", "securite"}
MEDIA_SRC = re.compile(r'src="(/media/[^"]+)"')


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def _all_products(client: httpx.Client) -> list[dict[str, Any]]:
    response = client.get("/api/shop/products", params={"page_size": 50})
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


class TestCatalogApi:
    def test_lists_the_fifteen_products_of_the_five_categories(self, client: httpx.Client) -> None:
        body = client.get("/api/shop/products", params={"page_size": 50}).json()

        assert body["total"] == 15
        assert Counter(item["category"] for item in body["items"]) == dict.fromkeys(CATEGORIES, 3)

    def test_list_is_paginated(self, client: httpx.Client) -> None:
        body = client.get("/api/shop/products", params={"page": 2, "page_size": 10}).json()

        assert (body["page"], body["page_size"], body["total"]) == (2, 10, 15)
        assert len(body["items"]) == 5

    def test_filters_by_category(self, client: httpx.Client) -> None:
        body = client.get("/api/shop/products", params={"category": "tentes"}).json()

        assert body["total"] == 3
        assert {item["category"] for item in body["items"]} == {"tentes"}

    def test_unknown_category_returns_422_without_reflecting_the_input(
        self, client: httpx.Client
    ) -> None:
        response = client.get("/api/shop/products", params={"category": "zz-evil-zz"})

        assert response.status_code == 422
        assert "zz-evil-zz" not in response.text

    def test_exposes_sold_out_and_low_stock_availability(self, client: httpx.Client) -> None:
        by_slug = {item["slug"]: item for item in _all_products(client)}

        assert by_slug["sac-de-couchage-synthetique-0"]["availability"] == "out_of_stock"
        assert by_slug["sac-a-dos-ultralight-38l"]["availability"] == "low_stock"
        assert by_slug["rechaud-titane-ultralight"]["availability"] == "in_stock"

    def test_prices_are_integer_cents(self, client: httpx.Client) -> None:
        assert all(isinstance(item["price_cents"], int) for item in _all_products(client))


class TestCatalogImages:
    def test_every_product_image_is_served_from_the_bucket(self, client: httpx.Client) -> None:
        urls = [url for item in _all_products(client) for url in item["image_urls"]]

        assert len(urls) >= 15
        for url in urls:
            response = client.get(url)
            assert response.status_code == 200, url
            assert response.headers["content-type"].startswith("image/"), url

    def test_bucket_is_read_only_and_not_listable(self, client: httpx.Client) -> None:
        assert client.get("/media/").status_code in {403, 404}
        assert client.post("/media/intrus.svg", content=b"<svg/>").status_code in {404, 405}
        assert client.delete("/media/rechaud-titane-ultralight-1.svg").status_code in {404, 405}


class TestCatalogPages:
    def test_home_page_lists_products_with_working_images(self, client: httpx.Client) -> None:
        response = client.get("/")

        assert response.status_code == 200
        sources = MEDIA_SRC.findall(response.text)
        assert sources, "aucune image du catalogue sur l'accueil"
        assert all(client.get(src).status_code == 200 for src in set(sources))

    def test_category_page_shows_only_its_products(self, client: httpx.Client) -> None:
        response = client.get("/categories/tentes")

        assert response.status_code == 200
        assert "Tente Tunnel 4 Saisons 3P" in response.text
        assert "Réchaud Titane Ultralight" not in response.text
        sources = MEDIA_SRC.findall(response.text)
        assert len(set(sources)) == 3
        assert all(client.get(src).status_code == 200 for src in set(sources))

    def test_unknown_category_page_is_a_404(self, client: httpx.Client) -> None:
        assert client.get("/categories/inconnue").status_code == 404

    def test_product_page_still_works(self, client: httpx.Client) -> None:
        response = client.get("/produits/tente-bivouac-ultralight-2p")

        assert response.status_code == 200
        assert "Tente Bivouac Ultralight 2P" in response.text
