"""Fiche produit : API de detail, page du front (SEO) et sitemap issu de l'API."""

import html
import json
import os
import re
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
SLUG = "tente-bivouac-ultralight-2p"
META_DESCRIPTION = re.compile(r'<meta name="description" content="([^"]*)"')
JSON_LD = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def _json_ld_blocks(page: str) -> list[dict[str, Any]]:
    return [json.loads(html.unescape(raw)) for raw in JSON_LD.findall(page)]


class TestProductDetailApi:
    def test_returns_description_specs_images_and_rating(self, client: httpx.Client) -> None:
        body = client.get(f"/api/shop/products/{SLUG}").json()

        assert body["description"]
        assert body["specs"]["weight_grams"] == 1480
        assert body["specs"]["waterproofing_mm"] == 3000
        assert body["specs"]["comfort_temp_c"] == -5
        assert body["specs"]["seasons"] == 3
        assert body["specs"]["material"] == "Nylon Ripstop 20D"
        assert len(body["image_urls"]) == 2
        assert (body["rating_value"], body["rating_count"]) == (4.8, 132)

    def test_unknown_slug_returns_a_generic_404_without_the_input(
        self, client: httpx.Client
    ) -> None:
        response = client.get("/api/shop/products/zz-evil-zz")

        assert response.status_code == 404
        assert response.json() == {"detail": "Produit introuvable."}
        assert "zz-evil-zz" not in response.text


class TestProductPage:
    def test_page_is_served_from_the_api_with_a_140_to_160_characters_description(
        self, client: httpx.Client
    ) -> None:
        response = client.get(f"/produits/{SLUG}")

        assert response.status_code == 200
        match = META_DESCRIPTION.search(response.text)
        assert match is not None
        assert 140 <= len(html.unescape(match.group(1))) <= 160

    def test_page_exposes_product_and_breadcrumb_json_ld(self, client: httpx.Client) -> None:
        blocks = _json_ld_blocks(client.get(f"/produits/{SLUG}").text)

        product = next(b for b in blocks if b.get("@type") == "Product")
        assert product["name"] == "Tente Bivouac Ultralight 2P"
        assert product["offers"]["price"] == "329.00"
        assert product["offers"]["availability"] == "https://schema.org/InStock"
        assert product["aggregateRating"]["reviewCount"] == 132
        assert any(b.get("@type") == "BreadcrumbList" for b in blocks)

    def test_sold_out_product_is_reported_out_of_stock(self, client: httpx.Client) -> None:
        page = client.get("/produits/sac-de-couchage-synthetique-0").text

        product = next(b for b in _json_ld_blocks(page) if b.get("@type") == "Product")
        assert product["offers"]["availability"] == "https://schema.org/OutOfStock"

    def test_unknown_product_page_is_a_404(self, client: httpx.Client) -> None:
        assert client.get("/produits/inconnu").status_code == 404


class TestSitemap:
    def test_sitemap_lists_every_product_of_the_api(self, client: httpx.Client) -> None:
        slugs = {
            item["slug"]
            for item in client.get("/api/shop/products", params={"page_size": 50}).json()["items"]
        }

        sitemap = client.get("/sitemap.xml")

        assert sitemap.status_code == 200
        listed = set(re.findall(r"/produits/([a-z0-9-]+)</loc>", sitemap.text))
        assert listed == slugs
        assert len(slugs) == 15
