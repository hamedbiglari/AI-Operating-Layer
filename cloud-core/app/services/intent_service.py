"""
Intent service (master spec section 24).

`classify_query` runs the pure rule engine
(app/services/intent_classifier.py) against `query.query` and persists
its matches as Intent rows — idempotent with respect to intent_type
(re-running never creates a duplicate row for a type the query already
has an Intent for) and is the ONLY path that auto-transitions
`Query.status` from DISCOVERED to CLASSIFIED (never touched if the
query is already ARCHIVED — archiving is an explicit human
deprioritization the classifier must not silently undo).

`create_manual_intent` is the human-override path
(classification_source=MANUAL) — it never edits an existing rule-engine
row, only adds a new one, so classification history is never lost (see
Intent's model docstring).
"""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import IntentClassificationSource, IntentType, QueryStatus
from app.models.intent import Intent
from app.models.query import Query
from app.services import intent_classifier
from app.services.audit import record_audit_log


def classify_query(db: Session, *, query: Query, actor_user_id: UUID | None) -> list[Intent]:
    existing_rows = db.execute(select(Intent).where(Intent.query_id == query.id)).scalars().all()
    existing_types = {row.intent_type for row in existing_rows}

    rule_matches = intent_classifier.classify(query.query)
    created: list[Intent] = []
    for match in rule_matches:
        if match.intent_type in existing_types:
            continue
        intent = Intent(
            organization_id=query.organization_id,
            query_id=query.id,
            intent_type=match.intent_type,
            confidence=match.confidence,
            classification_source=IntentClassificationSource.RULE_ENGINE,
            reason=match.reason,
            is_primary=False,
        )
        db.add(intent)
        created.append(intent)
        existing_types.add(match.intent_type)

    if not created:
        return []
    db.flush()

    has_primary = db.execute(
        select(exists().where(Intent.query_id == query.id, Intent.is_primary.is_(True)))
    ).scalar()
    if not has_primary:
        primary_match = intent_classifier.pick_primary(rule_matches)
        if primary_match is not None:
            for intent in created:
                if intent.intent_type == primary_match.intent_type:
                    intent.is_primary = True
                    break

    if query.status == QueryStatus.DISCOVERED:
        query.status = QueryStatus.CLASSIFIED

    db.flush()
    record_audit_log(
        db,
        organization_id=query.organization_id,
        user_id=actor_user_id,
        action="query.classified",
        resource_type="query",
        resource_id=query.id,
        new_value={"intent_count": len(created), "types": [i.intent_type.value for i in created]},
    )
    db.commit()
    for intent in created:
        db.refresh(intent)
    db.refresh(query)
    return created


def create_manual_intent(
    db: Session,
    *,
    query: Query,
    intent_type: IntentType,
    entity_id: UUID | None,
    confidence: float | None,
    reason: str | None,
    is_primary: bool,
    actor_user_id: UUID,
) -> Intent:
    if is_primary:
        db.execute(
            Intent.__table__.update()
            .where(Intent.query_id == query.id, Intent.is_primary.is_(True))
            .values(is_primary=False)
        )

    intent = Intent(
        organization_id=query.organization_id,
        query_id=query.id,
        intent_type=intent_type,
        confidence=confidence,
        entity_id=entity_id,
        classification_source=IntentClassificationSource.MANUAL,
        reason=reason,
        is_primary=is_primary,
    )
    db.add(intent)
    db.flush()

    if query.status == QueryStatus.DISCOVERED:
        query.status = QueryStatus.CLASSIFIED

    record_audit_log(
        db,
        organization_id=query.organization_id,
        user_id=actor_user_id,
        action="intent.manual_created",
        resource_type="intent",
        resource_id=intent.id,
        new_value={"intent_type": intent_type.value, "is_primary": is_primary},
    )
    db.commit()
    db.refresh(intent)
    db.refresh(query)
    return intent


def list_intents_for_query(
    db: Session, *, query_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[Intent], int]:
    from sqlalchemy import func

    base = select(Intent).where(Intent.query_id == query_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, Intent, sort, "created_at", SortDirection.ASC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total
