"""
Cross-phase forensic integrity (Phase 0-12 audit).

These are structural invariants that no single phase owns, and that the
per-phase suites therefore never checked. Each exists because the audit
found a real defect or a real near-miss.
"""

import ast
import pathlib
import re

import pytest

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def _modules():
    return [f for f in APP.rglob("*.py") if "__pycache__" not in str(f)]


def test_no_function_is_defined_twice_in_the_same_module() -> None:
    """REGRESSION (F5): `ingest_document_job` was defined twice in
    `workers/tasks.py`. Python silently keeps the second, and both
    registered as Celery task `documents.ingest` — so the first was dead
    code that *looked* live, and a reader could not tell which ran.

    Same-file redefinition is always a defect: it is either a merge
    accident or an append that should have been an edit."""
    offenders = []
    for module in _modules():
        tree = ast.parse(module.read_text())
        names = [
            n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            offenders.append(f"{module.name}: {sorted(duplicates)}")
    assert offenders == [], f"functions redefined in the same module: {offenders}"


def test_no_class_is_defined_twice_in_the_same_module() -> None:
    offenders = []
    for module in _modules():
        tree = ast.parse(module.read_text())
        names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            offenders.append(f"{module.name}: {sorted(duplicates)}")
    assert offenders == [], f"classes redefined in the same module: {offenders}"


def test_every_celery_task_name_is_registered_exactly_once() -> None:
    """A duplicate task NAME is worse than a duplicate function: Celery
    silently binds the name to whichever registered last, so the running
    worker may execute code the reader is not looking at."""
    # ONE pattern covering both the single-line and multiline decorator
    # forms. The first draft used two patterns and double-counted the
    # multiline one, reporting a duplicate that did not exist — a false
    # positive is as harmful as a false negative in an audit.
    names = []
    for module in _modules():
        for match in re.finditer(
            r'@celery_app\.task\(\s*(?:\n\s*)?name="([^"]+)"', module.read_text()
        ):
            names.append(match.group(1))
    duplicates = {n for n in names if names.count(n) > 1}
    assert duplicates == set(), f"Celery task names declared more than once: {duplicates}"


def test_query_normalization_has_exactly_one_implementation() -> None:
    """Phase 6 owns query normalization. A second implementation would let
    two code paths disagree about what counts as the same query — which
    would silently fragment clustering and deduplication."""
    definitions = []
    for module in _modules():
        if re.search(r"^def normalize_query\(", module.read_text(), re.M):
            definitions.append(module.name)
    assert definitions == ["query_service.py"], (
        f"normalize_query defined in {definitions}; Phase 6 must remain canonical"
    )


def test_every_tenant_scoped_model_has_organization_id() -> None:
    """`organizations` is the only legitimate exception — it IS the tenant."""
    import inspect

    import app.models as models
    from app.db.base import Base

    missing = []
    for _, obj in vars(models).items():
        if not (inspect.isclass(obj) and issubclass(obj, Base) and obj is not Base):
            continue
        if not hasattr(obj, "__table__"):
            continue
        columns = {c.name for c in obj.__table__.columns}
        if "organization_id" not in columns and obj.__tablename__ != "organizations":
            missing.append(obj.__tablename__)
    assert missing == [], f"tenant-scoped tables without organization_id: {missing}"


def test_no_enum_is_declared_and_never_used() -> None:
    """REGRESSION: `VisibilityJobStatus` shipped as a PostgreSQL type and
    was referenced exactly once — its own definition (P12-17)."""
    source = "\n".join(m.read_text() for m in _modules())
    enums = re.findall(
        r"^class (\w+)\((?:str, |int, )?enum\.Enum\)",
        (APP / "models" / "enums.py").read_text(), re.M,
    )
    dead = [e for e in enums if source.count(e) <= 2]
    assert dead == [], f"enums declared but never used: {dead}"


def test_no_model_module_is_unreferenced() -> None:
    source = "\n".join(m.read_text() for m in _modules())
    orphans = [
        f.stem for f in (APP / "models").glob("*.py")
        if f.stem != "__init__" and source.count(f.stem) <= 1
    ]
    assert orphans == [], f"model modules never imported: {orphans}"


def test_fixture_providers_cannot_be_confused_with_live_providers() -> None:
    """Stored observations must carry `is_fixture`, or fixture data becomes
    indistinguishable from a live measurement the moment it is read back."""
    from app.models.search_observation import SearchObservation
    from app.models.visibility import VisibilityTest

    assert "is_fixture" in {c.name for c in VisibilityTest.__table__.columns}
    assert "is_fixture" in {c.name for c in SearchObservation.__table__.columns}


def test_visibility_and_search_observations_stay_structurally_distinct() -> None:
    """Search yields position/URL; AI yields mention/citation. One table
    would be half-null in every row with no way to tell which half was
    legitimately empty."""
    from app.models.search_observation import SearchObservation
    from app.models.visibility import VisibilityTest

    search = {c.name for c in SearchObservation.__table__.columns}
    ai = {c.name for c in VisibilityTest.__table__.columns}
    for ai_only in ("mentioned", "cited", "recommended"):
        assert ai_only not in search
    for search_only in ("position", "impressions", "clicks", "ctr"):
        assert search_only not in ai
    assert "query_id" in search and "query_id" in ai


def test_no_global_ai_score_exists_anywhere() -> None:
    """The project has refused a headline number three times (ADR-047,
    ADR-059, ADR-064). This asserts none crept back in."""
    source = "\n".join(m.read_text() for m in _modules()).lower()
    for forbidden in ("visibility_score", "authority_score", "ai_score",
                      "readiness_score", "universal_score"):
        assert forbidden not in source, f"a global score named {forbidden} was introduced"


def test_click_and_purchase_are_not_representable_as_observations() -> None:
    """ADR-062: neither is observable from a platform response, so there is
    no column to write a guess into."""
    from app.models.visibility import VisibilityTest

    columns = {c.name for c in VisibilityTest.__table__.columns}
    for forbidden in ("clicked", "click_count", "purchased", "purchase_count", "conversions"):
        assert forbidden not in columns


def test_visibility_events_carry_no_causal_field() -> None:
    """The system observes that a value changed and cannot know why."""
    from app.models.visibility_project import VisibilityEvent

    columns = {c.name for c in VisibilityEvent.__table__.columns}
    for forbidden in ("cause", "caused_by", "impact", "attribution", "reason"):
        assert forbidden not in columns


def test_no_route_module_is_unregistered() -> None:
    """REGRESSION: an unregistered router is invisible dead code."""
    router_source = (APP / "api" / "v1" / "router.py").read_text()
    modules = {
        f.stem for f in (APP / "api" / "v1").glob("*.py")
        if f.stem not in ("__init__", "router")
    }
    registered = set(re.findall(r"from app\.api\.v1\.(\w+) import", router_source))
    assert modules - registered == set(), (
        f"router modules never registered: {sorted(modules - registered)}"
    )
