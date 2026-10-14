"""
SQL-LEVEL cross-tenant integrity (A3 / ADR-037).

Every prior phase's tenant tests went through the API, so they proved
the *service layer* rejects cross-tenant writes. They could not prove
the database would.

These tests bypass the service layer entirely and write through the ORM
session directly, which is the only way to demonstrate that the
composite foreign keys added in migration 0010 actually reject a
cross-tenant parent at the SQL level — the difference between an
application invariant and a database invariant.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.models.enums import OfferAvailability, ProductRelationType, ProductStatus
from app.models.offer import Offer
from app.models.product import Product
from app.models.product_relation import ProductRelation


def _org_and_product(client: TestClient, register_org, slug: str):
    org = register_org()
    product = client.post(
        "/api/v1/products", json={"name": "P", "slug": slug}, headers=org["headers"]
    ).json()
    return org, product


def test_database_rejects_offer_whose_org_differs_from_its_product(
    client: TestClient, register_org, db_session
) -> None:
    """The exact defect A3 existed to close, proven at SQL level."""
    org_a, product_a = _org_and_product(client, register_org, "a")
    org_b, _ = _org_and_product(client, register_org, "b")

    rogue = Offer(
        organization_id=uuid.UUID(org_b["organization"]["id"]),  # B's tenant...
        product_id=uuid.UUID(product_a["id"]),                    # ...A's product
        availability=OfferAvailability.IN_STOCK,
    )
    db_session.add(rogue)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_database_accepts_a_correctly_scoped_offer(client: TestClient, register_org, db_session) -> None:
    """Control: the constraint rejects mismatches, not everything."""
    org, product = _org_and_product(client, register_org, "a")

    valid = Offer(
        organization_id=uuid.UUID(org["organization"]["id"]),
        product_id=uuid.UUID(product["id"]),
        availability=OfferAvailability.IN_STOCK,
    )
    db_session.add(valid)
    db_session.flush()
    assert valid.id is not None
    db_session.rollback()


def test_database_rejects_cross_tenant_product_relation(
    client: TestClient, register_org, db_session
) -> None:
    org_a, product_a = _org_and_product(client, register_org, "a")
    org_b, product_b = _org_and_product(client, register_org, "b")

    rogue = ProductRelation(
        organization_id=uuid.UUID(org_a["organization"]["id"]),
        product_id=uuid.UUID(product_a["id"]),
        related_product_id=uuid.UUID(product_b["id"]),  # B's product
        relation_type=ProductRelationType.SIMILAR,
    )
    db_session.add(rogue)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_database_rejects_product_whose_knowledge_object_is_fabricated(
    client: TestClient, register_org, db_session
) -> None:
    """Not a composite-FK case, but confirms the plain FK still holds
    after the migration reshuffled constraints."""
    org = register_org()
    rogue = Product(
        organization_id=uuid.UUID(org["organization"]["id"]),
        name="P", slug="rogue", status=ProductStatus.DRAFT,
        knowledge_object_id=uuid.uuid4(),
    )
    db_session.add(rogue)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_database_rejects_mapping_whose_site_belongs_to_another_org(
    client: TestClient, register_org, db_session
) -> None:
    """The new Phase 9 table is born with the constraint, rather than
    repeating the defect a fifth time."""
    from app.models.enums import MappedObjectType
    from app.models.wordpress_mapping import WordPressMapping

    org_a = register_org()
    org_b = register_org()
    site_b = client.post(
        "/api/v1/sites", json={"name": "B", "domain": "b.example"}, headers=org_b["headers"]
    ).json()
    ko_a = client.post(
        "/api/v1/knowledge", json={"canonical_name": "K", "object_type": "plant"},
        headers=org_a["headers"],
    ).json()

    rogue = WordPressMapping(
        organization_id=uuid.UUID(org_a["organization"]["id"]),
        site_id=uuid.UUID(site_b["id"]),  # B's site
        object_type=MappedObjectType.KNOWLEDGE_OBJECT,
        object_id=uuid.UUID(ko_a["id"]),
        wordpress_post_id=1,
    )
    db_session.add(rogue)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_database_rejects_cross_tenant_installation_credential(
    client: TestClient, register_org, db_session
) -> None:
    from app.models.installation import Installation, InstallationCredential
    from app.models.enums import AdapterType

    org_a = register_org()
    org_b = register_org()
    inst_a = Installation(
        organization_id=uuid.UUID(org_a["organization"]["id"]),
        name="A", adapter_type=AdapterType.WORDPRESS,
    )
    db_session.add(inst_a)
    db_session.flush()

    rogue = InstallationCredential(
        organization_id=uuid.UUID(org_b["organization"]["id"]),  # B's tenant
        installation_id=inst_a.id,                                # A's installation
        key_id="k" + uuid.uuid4().hex[:16],
        secret_hash="x",
    )
    db_session.add(rogue)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
