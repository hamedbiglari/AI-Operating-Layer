"""
Scholarly metadata providers for federated research: Crossref, PubMed (NCBI E-utilities),
Europe PMC. Real HTTP clients against fixed official hosts only (no user-supplied URL is ever
requested — SSRF-safe by construction); the transport is injectable for tests.

A provider reports only what it RETURNED: metadata, and an abstract when the API included one.
It never downloads or claims full text. Open-access full-text *locations* are recorded as
acquisition paths, not as accessed content.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

CROSSREF = "https://api.crossref.org"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
ALLOWED_HOSTS = {"api.crossref.org", "eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"}
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


@dataclass
class ScholarlyRecord:
    provider: str
    external_id: str | None
    title: str | None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    abstract: str | None = None
    publisher: str | None = None
    journal: str | None = None
    year: str | None = None
    landing_url: str | None = None
    oa_urls: list[str] = field(default_factory=list)
    open_access: bool | None = None           # None = provider did not say
    license: str | None = None


class ProviderUnavailable(RuntimeError):
    pass


def clean(text: str | None) -> str | None:
    if not text:
        return None
    t = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", t).strip() or None


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d)
    return d or None


def plain_text_query(q: str) -> str:
    """Crossref's query.bibliographic has no boolean syntax: drop operators and quotes."""
    return re.sub(r"\s+", " ", re.sub(r'\b(AND|OR|NOT)\b|[()"]', " ", q)).strip()


class _Base:
    name = "base"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.Client:
        ua = f"AI-Operating-Layer/1.0 (mailto:{settings.RESEARCH_CONTACT_EMAIL})" if settings.RESEARCH_CONTACT_EMAIL else "AI-Operating-Layer/1.0"
        return httpx.Client(timeout=TIMEOUT, transport=self._transport, headers={"User-Agent": ua}, follow_redirects=False)

    def _get(self, client: httpx.Client, url: str, params: dict) -> dict:
        host = httpx.URL(url).host
        if host not in ALLOWED_HOSTS:           # defence in depth: fixed hosts only
            raise ProviderUnavailable(f"host not allowed: {host}")
        try:
            r = client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{type(exc).__name__}") from None
        if r.status_code != 200:
            raise ProviderUnavailable(f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise ProviderUnavailable("invalid JSON") from None


class CrossrefProvider(_Base):
    name = "crossref"

    def search(self, query: str, limit: int = 20) -> list[ScholarlyRecord]:
        with self._client() as c:
            data = self._get(c, f"{CROSSREF}/works", {"query.bibliographic": plain_text_query(query), "rows": limit})
        out = []
        for it in (data.get("message") or {}).get("items") or []:
            links = [l.get("URL") for l in it.get("link") or [] if l.get("URL")]
            lic = (it.get("license") or [{}])[0].get("URL") if it.get("license") else None
            year = None
            parts = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
            if parts and parts[0]:
                year = str(parts[0])
            out.append(ScholarlyRecord(
                provider=self.name, external_id=it.get("DOI"), title=clean((it.get("title") or [None])[0]),
                doi=norm_doi(it.get("DOI")), abstract=clean(it.get("abstract")), publisher=it.get("publisher"),
                journal=(it.get("container-title") or [None])[0], year=year, landing_url=it.get("URL"),
                oa_urls=[], open_access=None, license=lic))
            # Crossref full-text links are publisher links, often paywalled: kept as acquisition paths only.
            out[-1].oa_urls = []
            out[-1].landing_url = out[-1].landing_url or (links[0] if links else None)
        return out


class PubMedProvider(_Base):
    name = "pubmed"

    def search(self, query: str, limit: int = 20) -> list[ScholarlyRecord]:
        base = {"db": "pubmed", "retmode": "json"}
        if settings.NCBI_API_KEY:
            base["api_key"] = settings.NCBI_API_KEY.get_secret_value()
        with self._client() as c:
            ids = ((self._get(c, f"{EUTILS}/esearch.fcgi", {**base, "term": query, "retmax": limit})
                    .get("esearchresult") or {}).get("idlist") or [])
            if not ids:
                return []
            summ = self._get(c, f"{EUTILS}/esummary.fcgi", {**base, "id": ",".join(ids)}).get("result") or {}
        out = []
        for uid in summ.get("uids") or ids:
            it = summ.get(uid) or {}
            aids = {a.get("idtype"): a.get("value") for a in it.get("articleids") or []}
            out.append(ScholarlyRecord(
                provider=self.name, external_id=str(uid), title=clean(it.get("title")), doi=norm_doi(aids.get("doi")),
                pmid=str(uid), pmcid=aids.get("pmc"), abstract=None,  # esummary carries no abstract
                publisher=None, journal=it.get("fulljournalname") or it.get("source"),
                year=(it.get("pubdate") or "")[:4] or None))
        return out


class EuropePMCProvider(_Base):
    name = "europepmc"

    def search(self, query: str, limit: int = 20) -> list[ScholarlyRecord]:
        with self._client() as c:
            data = self._get(c, f"{EUROPEPMC}/search", {"query": query, "format": "json", "resultType": "core", "pageSize": limit})
        out = []
        for it in (data.get("resultList") or {}).get("result") or []:
            urls = [u for u in ((it.get("fullTextUrlList") or {}).get("fullTextUrl") or [])]
            oa = [u.get("url") for u in urls if (u.get("availability") or "").lower().startswith("open access") and u.get("url")]
            oa_flag = {"Y": True, "N": False}.get(it.get("isOpenAccess"))
            out.append(ScholarlyRecord(
                provider=self.name, external_id=it.get("id"), title=clean(it.get("title")), doi=norm_doi(it.get("doi")),
                pmid=it.get("pmid"), pmcid=it.get("pmcid"), abstract=clean(it.get("abstractText")),
                publisher=None, journal=((it.get("journalInfo") or {}).get("journal") or {}).get("title") or it.get("journalTitle"),
                year=str(it.get("pubYear")) if it.get("pubYear") else None, oa_urls=oa, open_access=oa_flag,
                license=it.get("license")))
        return out


class NotConfiguredWebProvider:
    """Placeholder for 'Web / other providers': no web search API is configured on this Cloud Core."""
    name = "web"

    def search(self, query: str, limit: int = 20) -> list[ScholarlyRecord]:
        raise NotImplementedError("no web search provider configured")


def default_providers(transport: httpx.BaseTransport | None = None) -> list:
    return [CrossrefProvider(transport), PubMedProvider(transport), EuropePMCProvider(transport), NotConfiguredWebProvider()]
