"""Table products et jeu de donnees initial du catalogue (15 produits, 5 categories).

Les prix sont des entiers en centimes d'euro. Les images sont referencees par leur cle dans le
bucket product-images (voir infra/seed/images). Neuf produits viennent de l'ancien catalogue
statique du front, six sont nouveaux (3 produits par categorie).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = ("tentes", "couchage", "sacs-a-dos", "cuisine", "securite")


def _product(
    slug: str,
    name: str,
    category: str,
    price_cents: int,
    short_description: str,
    description: str,
    specs: dict[str, Any],
    stock: int,
    rating_value: float,
    rating_count: int,
    compare_at_price_cents: int | None = None,
    image_count: int = 1,
) -> dict[str, Any]:
    return {
        "id": slug,
        "slug": slug,
        "name": name,
        "category": category,
        "price_cents": price_cents,
        "compare_at_price_cents": compare_at_price_cents,
        "short_description": short_description,
        "description": description,
        "images": [f"{slug}-{n}.svg" for n in range(1, image_count + 1)],
        "specs": specs,
        "stock": stock,
        "rating_value": rating_value,
        "rating_count": rating_count,
    }


SEED_PRODUCTS: list[dict[str, Any]] = [
    # --- Tentes ---
    _product(
        "tente-bivouac-ultralight-2p",
        "Tente Bivouac Ultralight 2P",
        "tentes",
        32900,
        "Abri autoportant 2 places, 3 saisons, conçu pour la grande randonnée en autonomie.",
        "Armature aluminium 7001 et double toit Nylon Ripstop 20D siliconé pour résister au vent "
        "sans compromis sur le poids. Montage rapide à deux arceaux croisés, ventilation double "
        "flux anti-condensation et abside généreuse pour le matériel.",
        {
            "weight_grams": 1480,
            "waterproofing_mm": 3000,
            "comfort_temp_c": -5,
            "seasons": 3,
            "material": "Nylon Ripstop 20D",
        },
        24,
        4.8,
        132,
        compare_at_price_cents=38900,
        image_count=2,
    ),
    _product(
        "tente-tunnel-4-saisons-3p",
        "Tente Tunnel 4 Saisons 3P",
        "tentes",
        48900,
        "Tunnel 3 places renforcé pour la neige et le vent, double abside.",
        "Structure tunnel à trois arceaux en alliage haute résistance, toile 40D enduite 5000 mm "
        "et jupes anti-neige. Deux entrées et deux absides pour cuisiner à l'abri.",
        {
            "weight_grams": 3100,
            "waterproofing_mm": 5000,
            "comfort_temp_c": -15,
            "seasons": 4,
            "material": "Nylon 40D enduit PU",
        },
        12,
        4.7,
        41,
    ),
    _product(
        "tarp-ultralight-3x3",
        "Tarp Ultralight 3x3",
        "tentes",
        8900,
        "Bâche d'abri 3 x 3 m en Dyneema, 280 g, modulable en dix configurations.",
        "Tarp polyvalent en composite Dyneema étanche, renforts aux 16 points d'ancrage et "
        "coutures thermosoudées. Idéal pour un abri léger ou en complément d'une tente.",
        {"weight_grams": 280, "waterproofing_mm": 10000, "seasons": 3, "material": "Dyneema DCF"},
        33,
        4.6,
        58,
    ),
    # --- Couchage ---
    _product(
        "sac-de-couchage-duvet-900",
        "Sac de Couchage Duvet 900",
        "couchage",
        27900,
        "Duvet d'oie déperlant 900 cuin, confort -9°C, compressible à l'extrême.",
        "Garnissage en duvet d'oie déperlant certifié RDS (900 cuin) pour un rapport chaleur/poids "
        "inégalé. Capuche ajustable, collerette anti-déperdition et pochette de compression incluse.",
        {
            "weight_grams": 850,
            "comfort_temp_c": -9,
            "seasons": 3,
            "material": "Duvet d'oie 900 cuin déperlant",
        },
        18,
        4.9,
        87,
    ),
    _product(
        "matelas-gonflable-isolant-r7",
        "Matelas Gonflable Isolant R7",
        "couchage",
        14900,
        "R-value 7.0, isolation hiver, gonflage rapide par pompe intégrée.",
        "Chambres horizontales et isolation multicouche réfléchissante (R-value 7.0) pour les "
        "bivouacs hivernaux. Pompe à sac intégrée et valve double action.",
        {
            "weight_grams": 620,
            "comfort_temp_c": -15,
            "seasons": 4,
            "material": "Nylon 40D + isolation TPU réfléchissante",
        },
        31,
        4.7,
        64,
    ),
    _product(
        "sac-de-couchage-synthetique-0",
        "Sac de Couchage Synthétique Confort 0°C",
        "couchage",
        11900,
        "Isolation synthétique résistante à l'humidité, confort 0°C, lavable en machine.",
        "Garnissage synthétique à fibres creuses qui conserve son pouvoir isolant humide, "
        "fermeture éclair à double curseur et capuche enveloppante. Un choix robuste et abordable.",
        {"weight_grams": 1350, "comfort_temp_c": 0, "seasons": 3, "material": "Polyester 20D"},
        0,
        4.4,
        73,
    ),
    # --- Sacs à dos ---
    _product(
        "sac-a-dos-randonnee-55l",
        "Sac à Dos Trek 55L",
        "sacs-a-dos",
        21900,
        "Armature ergonomique ventilée, portage longue distance, 55 litres.",
        "Armature aluminium et dos ventilé en treillis 3D. Portage ajustable sur 15 cm, ceinture "
        "lombaire moulée et compartiment pour poche à eau. Fixations tente et matelas externes.",
        {"weight_grams": 1620, "capacity_liters": 55, "material": "Nylon 420D Ripstop"},
        15,
        4.6,
        103,
    ),
    _product(
        "sac-a-dos-ultralight-38l",
        "Sac à Dos Ultralight 38L",
        "sacs-a-dos",
        18900,
        "Sac sans armature de 38 litres, 780 g, pour la randonnée rapide et légère.",
        "Dos plat compatible matelas en mousse, poches latérales extensibles et ceinture amovible. "
        "Toile enduite déperlante pour affronter la pluie fine.",
        {"weight_grams": 780, "capacity_liters": 38, "material": "Nylon 210D enduit"},
        4,
        4.5,
        29,
    ),
    _product(
        "sac-a-dos-expedition-70l",
        "Sac à Dos Expédition 70L",
        "sacs-a-dos",
        27900,
        "70 litres à réglage de dos intégral pour les treks de plus d'une semaine.",
        "Armature double lame, harnais réglable sans outil, panneau avant zippé et housse de pluie "
        "intégrée. Pensé pour porter 20 kg confortablement sur plusieurs jours.",
        {"weight_grams": 2150, "capacity_liters": 70, "material": "Nylon 500D Cordura"},
        9,
        4.7,
        36,
    ),
    # --- Cuisine ---
    _product(
        "rechaud-titane-ultralight",
        "Réchaud Titane Ultralight",
        "cuisine",
        5900,
        "Réchaud à gaz pliable 25 g, puissance 2800 W, piézo intégré.",
        "Titane de 25 grammes, 2800 W pour une ébullition rapide même en altitude. Pieds pliables "
        "grand angle, allumage piézoélectrique intégré, livré avec étui.",
        {"weight_grams": 25, "material": "Titane grade 5"},
        42,
        4.8,
        211,
    ),
    _product(
        "popote-titane-900ml",
        "Popote Titane 900ml",
        "cuisine",
        3900,
        "Gamelle titane ultralégère avec couvercle poêle et poignées pliantes.",
        "Popote en titane pur de 900 ml pour les sorties solo ou duo. Couvercle réversible utilisable "
        "comme poêle, poignées pliantes anti-brûlure, sac de transport en mesh inclus.",
        {"weight_grams": 142, "material": "Titane pur"},
        56,
        4.7,
        98,
    ),
    _product(
        "filtre-a-eau-portable",
        "Filtre à Eau Portable",
        "cuisine",
        3400,
        "Filtration 0.1 micron, élimine 99.99% des bactéries, 4000 L de capacité.",
        "Filtre à paille compact, membrane à fibres creuses 0.1 micron éliminant 99.99% des "
        "bactéries et protozoaires. 4000 litres sans entretien pour 58 grammes.",
        {"weight_grams": 58, "material": "Fibres creuses + ABS"},
        67,
        4.6,
        145,
    ),
    # --- Sécurité ---
    _product(
        "lampe-frontale-rechargeable",
        "Lampe Frontale Rechargeable",
        "securite",
        4400,
        "600 lumens, USB-C, étanche IPX6, autonomie 40h en mode éco.",
        "Jusqu'à 600 lumens en pleine puissance et 40 h d'autonomie en mode éco. Certification IPX6 "
        "et éclairage rouge nocturne pour préserver la vision au bivouac.",
        {"weight_grams": 92, "material": "ABS + silicone"},
        38,
        4.7,
        176,
    ),
    _product(
        "boussole-orientation-pro",
        "Boussole d'Orientation Pro",
        "securite",
        2900,
        "Boussole de précision avec clinomètre, loupe et viseur de visée.",
        "Visée miroir, clinomètre intégré pour estimer la pente, loupe de lecture de carte et "
        "liquide d'amortissement anti-vibration pour une lecture stable.",
        {"weight_grams": 65, "material": "ABS renforcé + verre minéral"},
        29,
        4.5,
        52,
    ),
    _product(
        "trousse-premiers-secours-rando",
        "Trousse de Premiers Secours Randonnée",
        "securite",
        3600,
        "Trousse étanche de 38 éléments pour la randonnée et le bivouac, 210 g.",
        "Pansements, compresses, bandes, couverture de survie, pince à échardes et guide de "
        "secours illustré, dans une pochette étanche à fermeture éclair.",
        {"weight_grams": 210, "material": "Nylon enduit étanche"},
        21,
        4.8,
        64,
    ),
]


def upgrade() -> None:
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    products = op.create_table(
        "products",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("compare_at_price_cents", sa.Integer(), nullable=True),
        sa.Column("short_description", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("images", json_type, nullable=False),
        sa.Column("specs", json_type, nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("rating_value", sa.Numeric(2, 1), nullable=False),
        sa.Column("rating_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("price_cents > 0", name="ck_products_price_positive"),
        sa.CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),
        sa.CheckConstraint("rating_value >= 0 AND rating_value <= 5", name="ck_products_rating"),
        sa.CheckConstraint(
            "category IN ('" + "', '".join(CATEGORIES) + "')", name="ck_products_category"
        ),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.bulk_insert(products, SEED_PRODUCTS)


def downgrade() -> None:
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")
