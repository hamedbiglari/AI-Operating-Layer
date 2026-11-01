"""Aggregates for the AI visibility report (V5-visibility-detail-aggregates).

One call returns everything the report's headline stats, over-time chart, country table and breakdowns need for a
rolling window, so the screen never asks once per day, country or page (Rule 17). Every number is a count of stored
rows for the caller's organization; nothing is estimated:

- "Automated requests" are page views whose actor type is a known automated client (search crawler, AI crawler, AI
  answering a user, agent tool). Views of unknown type are reported separately as unclassified, never folded in.
- Countries come only from `geo_country` as the adapter supplied it (ADR-079); views without one are counted, not
  guessed.
- The mean time on page averages only views that reported a time; with no samples it is null, never 0.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ActorType
from app.models.page_view import PageView
from app.models.visibility import VisibilityTest

AUTOMATED = (ActorType.SEARCH_CRAWLER, ActorType.AI_CRAWLER, ActorType.AI_USER_AGENT, ActorType.AGENT_TOOL)
TOP_COUNTRIES = 20
TOP_PAGES = 10


def _utc_day(column):  # noqa: ANN001, ANN202
    return func.date_trunc("day", func.timezone("UTC", column))


def aggregates(db: Session, *, organization_id: UUID, days: int, now: datetime | None = None) -> dict:
    until = now or datetime.now(timezone.utc)
    since = until - timedelta(days=days)

    views = (PageView.organization_id == organization_id, PageView.occurred_at >= since, PageView.occurred_at <= until)
    automated = (*views, PageView.actor_type.in_(AUTOMATED))

    observations = db.execute(select(func.count()).select_from(VisibilityTest).where(
        VisibilityTest.organization_id == organization_id, VisibilityTest.tested_at >= since,
        VisibilityTest.tested_at <= until)).scalar_one()

    by_type = dict(db.execute(select(PageView.actor_type, func.count()).where(*views)
                              .group_by(PageView.actor_type)).all())
    automated_requests = sum(n for t, n in by_type.items() if t in AUTOMATED)

    dwell = db.execute(select(func.avg(PageView.dwell_ms), func.count(PageView.dwell_ms)).where(*views)).one()

    countries = db.execute(select(PageView.geo_country, func.count().label("n")).where(*automated, PageView.geo_country.isnot(None))
                           .group_by(PageView.geo_country).order_by(func.count().desc(), PageView.geo_country)).all()
    without_country = db.execute(select(func.count()).select_from(PageView)
                                 .where(*automated, PageView.geo_country.is_(None))).scalar_one()

    pages = db.execute(select(PageView.path, func.count()).where(*automated).group_by(PageView.path)
                       .order_by(func.count().desc(), PageView.path).limit(TOP_PAGES)).all()

    # One expression object per query, so SELECT and GROUP BY render the same bound parameters.
    req_day, obs_day = _utc_day(PageView.occurred_at), _utc_day(VisibilityTest.tested_at)
    req_days = dict(db.execute(select(req_day, func.count()).where(*automated).group_by(req_day)).all())
    obs_days = dict(db.execute(select(obs_day, func.count()).where(
        VisibilityTest.organization_id == organization_id, VisibilityTest.tested_at >= since,
        VisibilityTest.tested_at <= until).group_by(obs_day)).all())

    def day_count(counts: dict, d: date) -> int:
        return sum(n for k, n in counts.items() if k is not None and k.date() == d)

    by_day, d = [], since.astimezone(timezone.utc).date()
    while d <= until.astimezone(timezone.utc).date():
        by_day.append({"day": d, "observations": day_count(obs_days, d), "requests": day_count(req_days, d)})
        d += timedelta(days=1)

    country_rows = [{"country": c, "requests": n} for c, n in countries]
    return {
        "days": days, "since": since, "until": until,
        "platform_observations": observations,
        "automated_requests": automated_requests,
        "unclassified_requests": by_type.get(ActorType.UNKNOWN, 0),
        "countries_reached": len(country_rows),
        "top_country": country_rows[0] if country_rows else None,
        "requests_without_country": without_country,
        "mean_dwell_ms": round(float(dwell[0])) if dwell[1] else None,
        "dwell_samples": dwell[1],
        "by_day": by_day,
        "by_country": country_rows[:TOP_COUNTRIES],
        "by_actor_type": [{"key": t.value, "requests": n} for t, n in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0].value))
                          if t != ActorType.HUMAN],
        "top_pages": [{"key": path, "requests": n} for path, n in pages],
    }
