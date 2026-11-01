# Persian (fa) glossary

Approved terms for every Persian string in `index.html`. Add a term here before
using it in the `FA` dictionary, so the same English word is never translated
two ways.

## Core knowledge terms

| English | Persian |
|---|---|
| Knowledge object | پرونده دانش (plural: پرونده‌های دانش) |
| Entity | موجودیت |
| Claim | ادعا |
| Evidence | شواهد (one piece: شاهد) |
| Source | منبع |
| Document | سند |
| Conversion | تبدیل سند |
| Knowledge gap | شکاف دانش |
| Conflict / conflicting | تعارض / متعارض |
| Provenance | منشأ |
| Version | نسخه |
| Research | پژوهش |
| Research again (button) | اجرای مجدد پژوهش |
| Research workspace (the "Research again" button in live mode) | میز کار پژوهش |
| Category / Section / Matrix | دسته / بخش / ماتریس |
| Coverage audit | ممیزی پوشش |
| Citation / Publication | استناد / انتشار |
| Full text | متن کامل |
| Reliability | قابل اعتماد بودن |
| Editorial assessment | ارزیابی تحریریه |

## Statuses

| English | Persian |
|---|---|
| Draft / In review / Approved / Published / Archived | پیش‌نویس / در حال بررسی / تأییدشده / منتشرشده / بایگانی‌شده |
| Queued / Processing / Retrying | در صف / در حال پردازش / تلاش دوباره |
| Succeeded / Failed / Cancelled | موفق / ناموفق / لغوشده |
| Needs human review / Pending review | نیازمند بررسی انسانی / در انتظار بررسی |
| Open / Resolved / Dismissed | باز / حل‌شده / ردشده |
| Sample data / Live data / Not connected | دادهٔ نمونه / دادهٔ زنده / متصل نیست |
| Finished (nothing left to do) / Show finished | تمام‌شده / نمایش تمام‌شده‌ها |
| Coming soon | به‌زودی |

## AI, commerce and account terms

| English | Persian |
|---|---|
| AI | هوش مصنوعی |
| AI visibility | دیده‌شدن در هوش مصنوعی |
| AI execution / Provider / Model | اجرای هوش مصنوعی / ارائه‌دهنده / مدل |
| Agent / Routing policy | عامل / سیاست مسیریابی |
| Memory / Workspace | حافظه / میز کار |
| Keyword / Query / Intent | کلیدواژه / عبارت جست‌وجو / هدف جست‌وجو |
| Crawler | خزنده |
| Organization / User / Owner | سازمان / کاربر / مالک |
| Wallet / Ledger / Payment | کیف پول / دفتر تراکنش‌ها / پرداخت |
| Product / Offer / SKU | محصول / پیشنهاد فروش / کد کالا (SKU) |
| Subscriber / Blog post | مشترک / نوشتهٔ وبلاگ |

## Knowledge list actions and messages

Approved in Part C (C9). Sentences are listed whole so the live templates
match them exactly.

| English | Persian |
|---|---|
| Filter / Clear filters (button) | فیلتر / پاک کردن فیلترها |
| Access token | توکن دسترسی |
| Loading… | در حال بارگذاری… |
| Retry (button; the status "Retrying" stays as above) | تلاش مجدد |
| Reconnect (button) | اتصال دوباره |
| Rows / Cards (view toggle) | ردیف‌ها / کارت‌ها |
| No knowledge objects yet. | هنوز پرونده دانشی وجود ندارد. |
| No knowledge objects match this search and these filters. | هیچ پرونده دانشی با این جست‌وجو و فیلترها مطابقت ندارد. |
| Finished objects are hidden; turn on Show finished to include them. | پرونده‌های تمام‌شده پنهان‌اند؛ برای نمایش آن‌ها «نمایش تمام‌شده‌ها» را روشن کنید. |
| Could not load knowledge objects ({error}). | بارگذاری پرونده‌های دانش ناموفق بود ({error}). |
| AI Core did not accept the access token (HTTP 401). It may have expired. | AI Core توکن دسترسی را نپذیرفت (HTTP 401). ممکن است منقضی شده باشد. |
| This access token is not allowed to read knowledge objects (HTTP 403). | این توکن دسترسی اجازهٔ خواندن پرونده‌های دانش را ندارد (HTTP 403). |

## Knowledge screen text

Static text on the Knowledge screen that stays visible in live mode. The two
policy-note rows are the halves of one paragraph, with the Sources & Documents
link between them.

| English | Persian |
|---|---|
| Sources & Documents | منابع و اسناد |
| Every keyword gets a dedicated object — complete with its own sources, claims, evidence, conflicts, gaps, and AI-visibility report. Click any Knowledge object to open its full, standalone management window. | برای هر کلیدواژه یک پرونده دانش جداگانه ساخته می‌شود، با منابع، ادعاها، شواهد، تعارض‌ها، شکاف‌ها و گزارش دیده‌شدن در هوش مصنوعی خودش. روی هر پرونده دانش کلیک کنید تا پنجرهٔ مدیریت کامل و مستقل آن باز شود. |
| Search knowledge objects | جست‌وجوی پرونده‌های دانش |
| Search by keywords - e.g. Toranjebin… | جست‌وجو با کلیدواژه — مثلاً ترنجبین… |
| Display mode | حالت نمایش |
| Rows view (toggle aria-label) | ردیف‌ها |
| Table — scroll sideways to see all of it | جدول — برای دیدن همهٔ آن، به پهلو پیمایش کنید |
| Knowledge objects, one row per keyword/entity, newest version first within each entity (table caption) | پرونده‌های دانش، یک ردیف برای هر کلیدواژه/موجودیت، با جدیدترین نسخه در ابتدای هر موجودیت |
| Policy note, before the link: A knowledge object is created from research or from sources contributing enough claims and evidence to support one — never fabricated because a query volume looked promising. Nothing here caps how many an organization can hold: this screen is built to hold tens, hundreds or thousands of them, searched/filtered/sorted/paginated server-side the same way | پرونده دانش از پژوهش یا از منابعی ساخته می‌شود که ادعاها و شواهد کافی برای پشتیبانی از آن فراهم کنند — هرگز فقط به این دلیل که حجم جست‌وجو امیدوارکننده به نظر می‌رسید ساخته نمی‌شود. سقفی برای تعداد پرونده‌های یک سازمان وجود ندارد: این صفحه برای ده‌ها، صدها یا هزاران پرونده ساخته شده و جست‌وجو، فیلتر، مرتب‌سازی و صفحه‌بندی آن‌ها در سمت سرور انجام می‌شود، مانند صفحهٔ |
| Policy note, after the link: is — the browser is never handed the whole collection at once. "Research again" on any row starts a new processing run against whatever sources have been added since — it creates a new version alongside the last one, never overwrites it. | ؛ مرورگر هرگز کل مجموعه را یک‌جا دریافت نمی‌کند. «اجرای مجدد پژوهش» در هر ردیف، پردازش تازه‌ای را روی منابعی که از آن زمان افزوده شده‌اند آغاز می‌کند. این کار نسخهٔ جدیدی در کنار نسخهٔ قبلی می‌سازد و هرگز آن را بازنویسی نمی‌کند. |

## Knowledge sample rows

Sample-only markup, hidden or replaced in live mode, translated so the screen
is complete in both modes.

| English | Persian |
|---|---|
| Sort: Open conflicts | مرتب‌سازی: تعارض‌های باز |
| Conflicts | تعارض‌ها |
| Re-run research on new/updated sources — creates a new version, never overwrites this one | اجرای مجدد پژوهش روی منابع جدید/به‌روزشده — نسخهٔ جدیدی می‌سازد و هرگز این نسخه را بازنویسی نمی‌کند |
| Re-run research — creates a new version | اجرای مجدد پژوهش — نسخهٔ جدیدی می‌سازد |
| Showing 4 of 4 in this fixture — representing an organization that may really hold thousands. Search, filter and sort narrow the server-side query; the page size stays fixed either way. | نمایش ۴ از ۴ در این دادهٔ نمونه — نمایندهٔ سازمانی که ممکن است در واقع هزاران پرونده داشته باشد. جست‌وجو، فیلتر و مرتب‌سازی، درخواست سمت سرور را محدود می‌کنند؛ اندازهٔ صفحه در هر حال ثابت می‌ماند. |
| {n} open (Evidence badge) | {n} باز |
| Needs review | نیازمند بررسی |
| {n} gaps, evidence needs review | {n} شکاف، شواهد نیازمند بررسی |
| Research again for {name} | اجرای مجدد پژوهش برای {name} |

Not translated: the Latin subtitle under each sample name (Toranjebin · Alhagi
manna, Saffron · Crocus sativus, Garlic · Allium sativum, Thyme · Thymus
vulgaris) is data and stays as written inside `<bdi dir="ltr">`, with no FA
entry. The sample counts "7 conflicts to resolve" and "3 conflicts to resolve"
use the existing FA template `{n|conflict|conflicts} to resolve`; the four
sample dates are formatted by convention 5.

## Knowledge object types

`object_type` is free text from the backend. These are the approved labels;
any other value is shown as it is (convention 7).

| object_type | Persian |
|---|---|
| `plant` | گیاه |
| `ingredient` | ماده |
| `compound` | ترکیب |
| `topic` | موضوع |
| `product` | محصول |
| `concept` | مفهوم |

## Sources list (Step 7A2a)

Approved for the live Sources list (7A3a). Badge labels for the five derived
statuses; Failed and Processing are the existing statuses above. The 401
message is the Knowledge sentence above, reused as written.

| English | Persian |
|---|---|
| Completed (badge) | تکمیل‌شده |
| Abstract only (badge) | فقط چکیده |
| Reference only (badge: a citation, no document) | فقط ارجاع |
| Claims (column header) | ادعاها |
| {n\|document\|documents} (meta line) | {n} سند |
| {n} KB / {n} MB (file size) | {n} کیلوبایت / {n} مگابایت |
| Open {name} (the Open link's accessible name) | باز کردن {name} |
| No sources yet. | هنوز منبعی وجود ندارد. |
| Add source (button) | افزودن منبع |
| Could not load sources ({error}). | بارگذاری منابع ناموفق بود ({error}). |
| This access token is not allowed to read sources (HTTP 403). | این توکن دسترسی اجازهٔ خواندن منابع را ندارد (HTTP 403). |

## Sources list controls (Step 7A2b)

Approved for search, the filter panel and sort (7A3b). Filter, Clear filters,
Type, Status, All, Remove filter, Other type, Exact type name, Sort: Name and
Sort: Recently updated are the Knowledge rows above, reused as written. "Most"
marks the two sorts that put the largest count first.

| English | Persian |
|---|---|
| Search sources (search field label) | جست‌وجوی منابع |
| Search by title, DOI, PMID or URL… (placeholder) | جست‌وجو با عنوان، DOI، PMID یا نشانی وب… |
| Sort: Most claims | مرتب‌سازی: بیشترین ادعا |
| Sort: Most evidence | مرتب‌سازی: بیشترین شواهد |
| No sources match this search and these filters. | هیچ منبعی با این جست‌وجو و فیلترها مطابقت ندارد. |
| All ({n}) (status option with its count) | همه ({n}) |
| Failed ({n}) | ناموفق ({n}) |
| Processing ({n}) | در حال پردازش ({n}) |
| Completed ({n}) | تکمیل‌شده ({n}) |
| Abstract only ({n}) | فقط چکیده ({n}) |
| Reference only ({n}) | فقط ارجاع ({n}) |

## Sources sample rows and counter (Step 7A3c)

Sample-only markup, hidden or replaced in live mode, translated so the screen
is complete in both modes. The table caption is also shown in live mode. The
sample counter is written by script every time the screen is shown, so its
rows are templates; "Status: Completed." is two nodes, the "Status" row above
and the status badge label, so both follow a language switch.

| English | Persian |
|---|---|
| Sort (sample Sort button, before a sort is chosen) | مرتب‌سازی |
| Everything the knowledge layer is allowed to derive truth from. 248 sources, 7 processing. | همهٔ آنچه لایهٔ دانش مجاز است حقیقت را از آن استخراج کند. ۲۴۸ منبع، ۷ در حال پردازش. |
| Sources, with processing status and what each has contributed to the knowledge layer (table caption) | منابع، همراه با وضعیت پردازش و آنچه هر یک به لایهٔ دانش افزوده است |
| Actions (hidden header of the Open column) | اقدامات |
| Not available (count cell) | در دسترس نیست |
| Paywalled (source meta line) | دسترسی پولی |
| Showing 7 of 248. Filtering and sorting run on the server; the browser never holds the whole collection. | نمایش ۷ از ۲۴۸. فیلتر و مرتب‌سازی در سمت سرور انجام می‌شود؛ مرورگر هرگز کل مجموعه را در اختیار ندارد. |
| List view | نمای فهرستی |
| Grid view | نمای شبکه‌ای |
| Sort by name, ascending (sample Sort button name) | مرتب‌سازی بر اساس نام، صعودی |
| Sort by name (A–Z) (its tooltip) | مرتب‌سازی بر اساس نام (الف تا ی) |
| Name A–Z (sample Sort button after one click) | نام (الف تا ی) |
| Name Z–A (after two clicks) | نام (ی تا الف) |
| Sorted by Name A–Z (its name after one click) | مرتب‌شده بر اساس نام (الف تا ی) |
| Sorted by Name Z–A (after two clicks) | مرتب‌شده بر اساس نام (ی تا الف) |
| Showing all {n} sources. (sample search counter) | نمایش همهٔ {n} منبع. |
| Showing {shown} of {n} sources. | نمایش {shown} از {n} منبع. |
| No sources match this search. | هیچ منبعی با این جست‌وجو مطابقت ندارد. |
| No sources with this status. | هیچ منبعی با این وضعیت وجود ندارد. |
| Show all sources (link in the counter) | نمایش همهٔ منابع |

Reused, no new row: Display mode (the List/Grid toggle group, as on Knowledge),
User uploaded, Supplier document and Lab report (source types), {n} KB and
{n} MB (file sizes), Status and the five status badge labels.

Not translated: sample source titles and file names (Toranjebin (Alhagi manna)
— Scientific Review 2025, the Mannitol paper, the supplier certificate, the
saffron lab report, the Persian Herbal Medicine Review .docx, and the
toranjebin.ir page title) are data and stay as written inside `<bdi dir="ltr">`,
with no FA entry. DOI, PMID, URLs and MIME types stay Latin inside
`<bdi class="identifier">` (convention 1).

## Source types

`source_type` is free text from the backend. These are the approved labels;
any other value is shown as it is (convention 7). `website` keeps its existing
entry.

| source_type | English | Persian |
|---|---|---|
| `scientific_paper` | Scientific paper | مقاله علمی |
| `review` | Review article | مقاله مروری |
| `book` | Book | کتاب |
| `pdf` | PDF file | فایل PDF |
| `government` | Government source | منبع دولتی |
| `dataset` | Dataset | مجموعه‌داده |
| `supplier_document` | Supplier document | سند تأمین‌کننده |
| `lab_report` | Lab report | گزارش آزمایشگاه |
| `user_upload` | User uploaded | بارگذاری‌شده توسط کاربر |
| `first_party` | First-party source | منبع خود سازمان |
| `news` | News | خبر |

## Source detail (Step 7B2a)

Approved for the live Source detail screen (7B2b). Strings already in `FA` are
reused as written: the status badges, Knowledge objects, Claims, Evidence,
Status, Updated, Loading…, Open {name}, the file sizes and the 401/403
sentences. «پردازش مجدد» is the locked term for Reprocess; Retry keeps
«تلاش دوباره». The DOI, PMID, ISBN and URL labels stay Latin as identifiers
(convention 1) and have no rows.

| English | Persian |
|---|---|
| Documents (count label, card heading) | اسناد |
| Source type (metadata label) | نوع منبع |
| Author (metadata label) | نویسنده |
| Publisher (metadata label) | ناشر |
| Publication date (metadata label; not "Published", the status) | تاریخ انتشار |
| Last activity (metadata label) | آخرین فعالیت |
| Document (column header) | سند |
| Conversion (column header) | تبدیل سند |
| Size (column header) | اندازه |
| This source has no documents yet. | این منبع هنوز سندی ندارد. |
| Showing the first {n} of {total} documents. (only when more than one page) | نمایش {n} سند اول از {total} سند. |
| Could not load documents ({error}). | بارگذاری اسناد ناموفق بود ({error}). |
| Pending (extraction and conversion status) | در انتظار |
| Extracting (extraction status) | در حال استخراج |
| Extracted (extraction status) | استخراج‌شده |
| Empty (conversion status: the converter returned no text) | بدون متن |
| Unsupported (conversion status) | پشتیبانی‌نشده |
| No conversion (document has no conversion record) | بدون تبدیل |
| Could not load conversions ({error}). | بارگذاری تبدیل‌های سند ناموفق بود ({error}). |
| Show text (per-document toggle) | نمایش متن |
| Hide text (per-document toggle) | پنهان کردن متن |
| Show text of {name} (toggle's accessible name) | نمایش متن {name} |
| Hide text of {name} (toggle's accessible name) | پنهان کردن متن {name} |
| This document has no text yet. | این سند هنوز متنی ندارد. |
| Could not load the text ({error}). | بارگذاری متن ناموفق بود ({error}). |
| Reprocess (button; never used for Retry) | پردازش مجدد |
| Reprocess {name} (button's accessible name) | پردازش مجدد {name} |
| Reprocess this document? The current extraction stays in force until the new one succeeds. (confirmation) | پردازش مجدد این سند انجام شود؟ استخراج فعلی تا زمانی معتبر است که استخراج جدید موفق شود. |
| Reprocessing queued (job {id}). ({id} is the job id) | پردازش مجدد در صف قرار گرفت (شناسهٔ کار: {id}). |
| Could not start reprocessing ({error}). | شروع پردازش مجدد ناموفق بود ({error}). |
| Your role is not allowed to reprocess documents (HTTP 403). | نقش شما اجازهٔ پردازش مجدد اسناد را ندارد (HTTP 403). |
| No source selected. Open one from Sources & Documents. (opened without ?id=) | هیچ منبعی انتخاب نشده است. یکی را از «منابع و اسناد» باز کنید. |
| This source was not found. (unknown id, or another organization's) | این منبع پیدا نشد. |
| Could not load this source ({error}). | بارگذاری این منبع ناموفق بود ({error}). |
| Source detail (screen heading when no source is shown) | جزئیات منبع |

## Source detail sample (Step 7B2c)

These translate the static sample markup of #screen-detail. The live
equivalent renders from backend fields instead, so these are sample-only.
Latin words inside a Persian value (Markdown, OCR, PDF) stay as written.
FSI/PDI around Latin words inside Persian values are added at render
time (7B2c-2).

### Labels

| English | Persian |
|---|---|
| Identity (card title) | مشخصات |
| Original file | فایل اصلی |
| Full text (as in Core knowledge terms) | متن کامل |
| Accessible (full-text badge) | در دسترس |
| Rights | حقوق |
| Unknown (rights badge) | نامشخص |
| What this source contributed (card title) | سهم این منبع |
| Canonical representation (card title) | بازنمایی مرجع |
| Converter | مبدل |
| Extraction level | سطح استخراج |
| Vision model | مدل بینایی |
| View Markdown (button) | مشاهدهٔ Markdown |
| Source detail sections (the tab list's accessible name) | بخش‌های جزئیات منبع |

### Values

| English | Persian |
|---|---|
| 3 — OCR (extraction level value) | ۳ — OCR |
| Level 4 not run | سطح ۴ اجرا نشد |
| Scientific paper · uploaded by Hamed · 2 Sep 2026 · processing version v3 (sample metadata line; live path uses separate fields) | مقاله علمی · بارگذاری‌شده توسط Hamed · ۱۱ شهریور ۱۴۰۵ · نسخهٔ پردازش v3 |

### Sentences

| English | Persian |
|---|---|
| 31 evidence records exist. 19 are verified; 12 are still pending review and count toward nothing. | ۳۱ شاهد ثبت شده است. ۱۹ مورد تأییدشده است؛ ۱۲ مورد هنوز در انتظار بررسی است و در هیچ شماری حساب نمی‌شود. |
| The original PDF stays authoritative. Markdown is derived, and is not knowledge. | PDF اصلی همچنان مرجع است. Markdown از آن برگرفته شده و دانش نیست. |

## Theme toggle (V5-theme-toggle-ui)

The topbar theme button follows the toggle-button pattern: its name stays
"Dark theme" and `aria-pressed` carries the state; the tooltip names what a
click will do. They replace the earlier single label "Toggle dark/light
theme". Theme is «تم».

| English | Persian |
|---|---|
| Dark theme (the button's fixed accessible name) | تم تاریک |
| Switch to dark theme (tooltip in the light theme) | تغییر به تم تاریک |
| Switch to light theme (tooltip in the dark theme) | تغییر به تم روشن |

## Processing screen (Step 7C-6)

Approved for the live Processing screen (7C-6), reached from a Source detail
document row as #screen-processing?id=<document_id>. Strings already in `FA`
are reused as written: Sources & Documents, Loading…, Queued, Retrying,
Succeeded, Failed, Cancelled, and Conversion («تبدیل سند», the 7B2a column
header, also the conversion stage name; D28). «پردازش» names the screen; the
status keeps «در حال پردازش». The backend's English stage details are rebuilt
from the templates below, never shown as sent. Format labels (DOCX, PDF) are
identifiers and have no rows.

| English | Persian |
|---|---|
| Processing (screen title and breadcrumb; not the status «در حال پردازش») | پردازش |
| Processing details (link in a Source detail document row) | جزئیات پردازش |
| Processing details of {name} (the link's accessible name) | جزئیات پردازش {name} |
| {format} · added {date} (document metadata line; {format} is a short label such as DOCX) | {format} · افزوده‌شده در {date} |
| Pipeline (card title) | مراحل پردازش |
| Upload (stage) | بارگذاری |
| Security validation (stage) | اعتبارسنجی امنیتی |
| Structure detection (stage) | تشخیص ساختار |
| OCR (stage; Latin acronym, as in 7B2c) | OCR |
| Semantic chunking (stage) | قطعه‌بندی معنایی |
| Evidence extraction (stage) | استخراج شواهد |
| Knowledge contribution (stage) | افزودن به لایهٔ دانش |
| No percentage is shown, because the worker does not report one. The stage is the truth available. | درصد پیشرفت نمایش داده نمی‌شود، چون پردازشگر آن را گزارش نمی‌کند. مرحلهٔ فعلی تنها اطلاع موجود است. |
| What has been found so far (card title) | آنچه تاکنون یافت شده است |
| Pages (metric) | صفحه‌ها |
| Tables detected (metric) | جدول‌های شناسایی‌شده |
| Images detected (metric) | تصویرهای شناسایی‌شده |
| OCR blocks (metric) | بلوک‌های OCR |
| Chunks created (metric) | قطعه‌های ساخته‌شده |
| Claims extracted (metric) | ادعاهای استخراج‌شده |
| Evidence candidates (metric) | شواهد نامزد |
| Stage not reached (metric with no value yet) | هنوز به این مرحله نرسیده است |
| {n} table / {n} tables (stage detail; a counted noun stays singular) | {n} جدول |
| {n} OCR block / {n} OCR blocks (stage detail) | {n} بلوک OCR |
| Not run (conversion failed) (structure or OCR after a failed conversion) | اجرا نشد (تبدیل سند ناموفق بود) |
| Not tracked in this backend version (evidence and knowledge; no backend signal) | در این نسخهٔ سامانه ردیابی نمی‌شود |
| Running (job status) | در حال اجرا |
| Dead letter (job status: failed for good, no more retries) | ناموفق نهایی |
| Job {id} · {status} · attempt {n} (job line) | کار {id} · {status} · تلاش {n} |
| No job record for this document. (job is None: URL jobs, documents with no job) | هیچ کاری برای این سند ثبت نشده است. |
| Last attempt failed; data from previous run (banner after a failed reprocess) | آخرین تلاش ناموفق بود؛ داده‌ها از اجرای قبلی است |
| No document selected. Open one from Source detail. (opened without ?id=) | هیچ سندی انتخاب نشده است. یکی را از «جزئیات منبع» باز کنید. |
| This document was not found. (unknown id, or another organization's) | این سند پیدا نشد. |
| Could not load processing ({error}). | بارگذاری پردازش ناموفق بود ({error}). |

## Processing sample and screen title (Step 7C-6a2)

The screen is labelled "Document processing" (E1): the FA key "Processing"
is the status «در حال پردازش», so the 7C-6a row "Processing (screen title and
breadcrumb)" is not used as a key. The sample strings below are the static
text nodes of the rewritten #screen-processing sample (D32); the job line's
id and the DOCX label are identifiers inside <bdi> and have no rows. Queued,
Retrying and Cancelled reuse the Statuses row above.

| English | Persian |
|---|---|
| Document processing (screen label: breadcrumb and screen picker; E1) | پردازش سند |
| · added 2 Sep 2026 (sample subtitle, after the DOCX label) | · افزوده‌شده در ۱۱ شهریور ۱۴۰۵ |
| 9 tables (sample structure detail) | ۹ جدول |
| 211 OCR blocks (sample OCR detail) | ۲۱۱ بلوک OCR |
| Job (sample job line, before the id) | کار |
| · Succeeded · attempt 1 (sample job line, after the id) | · موفق · تلاش ۱ |

## Conventions

1. Persian digits (۰–۹) and the Persian separators in all UI text. Identifiers,
   URLs, emails, code and form input keep Latin script. HTTP status codes
   (401, 403) are protocol identifiers: Latin digits, inside `<bdi>`.
2. A counted noun stays singular: «۳ ادعا», not «۳ ادعاها».
3. Formal register («شما») throughout.
4. Product and brand names stay as written: AI Core, AI Operating Layer,
   Crossref, PubMed.
5. Dates: the backend sends ISO 8601 in UTC. The page formats every date with
   `Intl.DateTimeFormat('fa-IR')`, which uses the Solar Hijri (Jalali)
   calendar. Pass `calendar: 'gregory'` explicitly where a Gregorian date is
   ever needed.
6. Dynamic text goes through `AIOL_I18N.set(node, template, args)` with a
   template entry in `FA`. Do not build Persian sentences by string
   concatenation in live code.
7. An `object_type` with no approved label renders as its English value inside
   `<bdi>`, never machine-translated. CI reports such runtime values but does
   not fail on them; static strings and code-level templates stay strict.
8. Error text from the browser or server (the `{error}` slot) is shown as it
   is, in English, inside `<bdi>`, as in convention 7.

## Provenance (Step 7D-2)

Terms for the live Provenance screen and its sample. Strength is the claim's
aggregate (ClaimEvidenceStrength), not one study's rating.

| English | Persian |
|---|---|
| Provenance | منشأ |
| Claim | ادعا |
| Claims shown: {shown} of {total} | ادعاهای نمایش‌داده‌شده: {shown} از {total} |
| Pending review | در انتظار بررسی |
| Rejected | ردشده |
| Disputed | مورد مناقشه |
| Deprecated | منسوخ |
| Verified | راستی‌آزمایی‌شده |
| Direct | مستقیم |
| Indirect | غیرمستقیم |
| Supports | حمایت می‌کند |
| Contradicts | نقض می‌کند |
| Mixed | دوپهلو |
| Neutral | خنثی |
| Aggregate strength: unverified | قوت کلی شواهد: تأییدنشده |
| Aggregate strength: insufficient | قوت کلی شواهد: ناکافی |
| Aggregate strength: weak | قوت کلی شواهد: ضعیف |
| Aggregate strength: moderate | قوت کلی شواهد: متوسط |
| No evidence is linked to this claim. | هیچ شاهدی به این ادعا پیوند داده نشده است. |
| This knowledge object has no claims yet. | این پرونده دانش هنوز هیچ ادعایی ندارد. |
| No knowledge object selected. Open one from Knowledge. | هیچ پرونده دانشی انتخاب نشده است. یکی را از «دانش» باز کنید. |
| This knowledge object was not found. | این پرونده دانش پیدا نشد. |
| Could not load provenance ({error}). | بارگذاری منشأ ناموفق بود ({error}). |
| Remove this evidence link? The evidence record, its document and its source are kept. | پیوند این شاهد حذف شود؟ خود شاهد، سند و منبع آن حفظ می‌شوند. |
| Evidence link removed. | پیوند شاهد حذف شد. |
| Your role is not allowed to remove evidence links (HTTP 403). | نقش شما اجازهٔ حذف پیوند شواهد را ندارد (HTTP 403). |
| Could not remove the link ({error}). | حذف پیوند ناموفق بود ({error}). |
| Remove this evidence link from the claim — the evidence record itself is kept | حذف پیوند این شاهد از ادعا — خود شاهد حفظ می‌شود |
| Remove this evidence link | حذف پیوند این شاهد |
| Toranjebin Scientific Review | مرور علمی ترنجبین |
| Where the statement “contains mannitol” actually comes from, in both directions. | گزارهٔ «حاوی مانیتول است» واقعاً از کجا آمده است، در هر دو جهت. |
| Knowledge back to source | از دانش تا منبع |
| (Toranjebin) | (ترنجبین) |
| Published · updated 4 Sep 2026 | منتشرشده · به‌روزرسانی ۱۳ شهریور ۱۴۰۵ |
| Contains mannitol | حاوی مانیتول |
| Approved · aggregate strength: moderate | تأییدشده · قوت کلی شواهد: متوسط |
| · compositional analysis | · تحلیل ترکیبی |
| Verified · direct · supports | راستی‌آزمایی‌شده · مستقیم · حمایت می‌کند |
| Canonical Markdown, chunk 118 | مارک‌داون مرجع، قطعهٔ ۱۱۸ |
| Toranjebin — Scientific Review 2025 | ترنجبین — مرور علمی ۲۰۲۵ |
| Full text accessible · | متن کامل در دسترس · |
| One claim, several sources | یک ادعا، چند منبع |
| Three support it; one contradicts it. That is shown, not averaged away. | سه منبع از آن حمایت می‌کنند و یکی آن را نقض می‌کند. این اختلاف نشان داده می‌شود، نه اینکه در میانگین گم شود. |
| Scientific Review 2025 | مرور علمی ۲۰۲۵ |
| Verified · direct | راستی‌آزمایی‌شده · مستقیم |
| Compositional analysis, | تحلیل ترکیبی، |
| Verified · direct · abstract only | راستی‌آزمایی‌شده · مستقیم · فقط چکیده |
| Pending review · counts toward nothing yet | در انتظار بررسی · هنوز در هیچ محاسبه‌ای شمرده نمی‌شود |
| Regional chemotype survey, 2023 | بررسی منطقه‌ای کموتیپ‌ها، ۲۰۲۳ |
| Verified · indirect · different species | راستی‌آزمایی‌شده · غیرمستقیم · گونهٔ دیگر |
| This removes the link between one evidence record and this claim — a real, immediate action already supported today. It never deletes the underlying evidence, the document, or the source. | این کار فقط پیوند میان یک شاهد و این ادعا را حذف می‌کند — اقدامی واقعی و فوری که همین امروز پشتیبانی می‌شود. خود شاهد، سند و منبع هرگز حذف نمی‌شوند. |
| This claim is marked | این ادعا به‌عنوان |
| conflicting | متعارض |
| . It is not presented as settled anywhere in the product. |  علامت خورده است و در هیچ جای محصول قطعی نمایش داده نمی‌شود. |
| Review the conflict | بررسی تعارض |

## Add source (Step 7E)

Terms for the live Add source screen (upload a file or queue a web page into
an existing source) and its sample cards. Format names stay Latin as identifiers.

| English | Persian |
|---|---|
| Add a source | افزودن منبع |
| Pick where it comes from. The system records the origin, not just the file. | مشخص کنید از کجا می‌آید. سامانه خاستگاه را ثبت می‌کند، نه فقط فایل را. |
| Web page | صفحهٔ وب |
| A public URL to fetch | یک نشانی عمومی برای دریافت |
| Add to source | افزودن به منبع |
| File | فایل |
| Web address | نشانی وب |
| Add web page | افزودن صفحهٔ وب |
| Choose a file first. | ابتدا یک فایل انتخاب کنید. |
| Enter a web address first. | ابتدا یک نشانی وب وارد کنید. |
| Uploading… | در حال بارگذاری… |
| Adding… | در حال افزودن… |
| Uploaded and queued for processing. | بارگذاری شد و در صف پردازش قرار گرفت. |
| Web page queued for processing. | صفحهٔ وب در صف پردازش قرار گرفت. |
| Upload failed ({error}). | بارگذاری ناموفق بود ({error}). |
| Could not add the web page ({error}). | افزودن صفحهٔ وب ناموفق بود ({error}). |
| Your role is not allowed to add documents (HTTP 403). | نقش شما اجازهٔ افزودن سند را ندارد (HTTP 403). |
| No sources yet. Create one with the form above first. | هنوز منبعی وجود ندارد. ابتدا با فرم بالا یکی بسازید. |

## Knowledge gap (Step 8A)

Terms for the live Knowledge gap screen. "Gap" is «شکاف», as in "Knowledge gap".

| English | Persian |
|---|---|
| Knowledge gaps | شکاف‌های دانش |
| Open gaps | شکاف‌های باز |
| Other open gaps on this knowledge object | دیگر شکاف‌های باز این پرونده دانش |
| No other open gaps on this knowledge object. | این پرونده دانش شکاف باز دیگری ندارد. |
| No open gaps. | هیچ شکاف بازی وجود ندارد. |
| This gap was not found. | این شکاف پیدا نشد. |
| Could not load the gap ({error}). | بارگذاری شکاف ناموفق بود ({error}). |
| Could not load gaps ({error}). | بارگذاری شکاف‌ها ناموفق بود ({error}). |
| Still open | هنوز باز |
| In progress | در حال انجام |
| Resolved | برطرف‌شده |
| Dismissed | کنارگذاشته‌شده |
| Low priority | اولویت پایین |
| Medium priority | اولویت متوسط |
| High priority | اولویت بالا |
| Critical priority | اولویت بحرانی |
| Content gap | شکاف محتوا |
| Entity gap | شکاف موجودیت |
| Claim gap | شکاف ادعا |
| Evidence gap | شکاف شواهد |
| Source gap | شکاف منبع |
| Access gap | شکاف دسترسی |
| Relation gap | شکاف رابطه |
| Freshness gap | شکاف به‌روز بودن |
| Conflict gap | شکاف تعارض |

## Categories & matrix, Coverage audit (Steps 8C, 8D)

Static strings of the two screens. Strings their scripts build at runtime are
not translated yet (V5-matrix-coverage-runtime-fa).

| English | Persian |
|---|---|
| Categories & Master Topic Matrix | دسته‌ها و ماتریس اصلی موضوعات |
| A category carries the section schema its topics should cover. Each cell of the matrix is read from the knowledge base — claims, evidence, conflicts, gaps — never typed in. An empty cell means the section has never been researched for that topic, not that it does not apply. | هر دسته طرح‌وارهٔ بخش‌هایی را دارد که موضوعاتش باید پوشش دهند. هر خانهٔ ماتریس از پایگاه دانش خوانده می‌شود — ادعاها، شواهد، تعارض‌ها، شکاف‌ها — و هرگز دستی وارد نمی‌شود. خانهٔ خالی یعنی آن بخش هرگز برای آن موضوع پژوهش نشده است، نه اینکه کاربرد ندارد. |
| Not connected to AI Core. Connect on the Dashboard or AI Center screen. | به AI Core وصل نیست. در صفحهٔ داشبورد یا مرکز هوش مصنوعی وصل شوید. |
| Category | دسته |
| Choose a category | یک دسته انتخاب کنید |
| Refresh | تازه‌سازی |
| New category | دستهٔ جدید |
| Starting schema | طرح‌وارهٔ آغازین |
| Medicinal plant (18 sections) | گیاه دارویی (۱۸ بخش) |
| Device (16 sections) | دستگاه (۱۶ بخش) |
| Generic (8 sections) | عمومی (۸ بخش) |
| Create category | ایجاد دسته |
| Proposals waiting for a decision | پیشنهادهای در انتظار تصمیم |
| A section discovered on one topic is proposed to its siblings. Nothing is written into a sibling's knowledge until you decide. | بخشی که در یک موضوع کشف شود به موضوعات هم‌دستهٔ آن پیشنهاد می‌شود. تا شما تصمیم نگیرید، چیزی در دانش آن موضوعات نوشته نمی‌شود. |
| Six dimensions, reported separately and never collapsed into one number: sources, processing, knowledge, evidence, sections and publication. A figure that cannot be known is shown as unknown with the reason — never as zero. If the newest run failed, the last successful audit stays on screen, marked stale. | شش بُعد، جداگانه گزارش می‌شوند و هرگز در یک عدد ادغام نمی‌شوند: منابع، پردازش، دانش، شواهد، بخش‌ها و انتشار. رقمی که دانستنش ممکن نیست، با دلیلش «نامعلوم» نشان داده می‌شود — هرگز صفر. اگر تازه‌ترین اجرا ناموفق باشد، آخرین ممیزی موفق روی صفحه می‌ماند و «کهنه» علامت می‌خورد. |
| Scope | دامنه |
| A topic | یک موضوع |
| A category | یک دسته |
| Which | کدام |
| Show | نمایش |
| Run the audit | اجرای ممیزی |
| History | تاریخچه |

## Knowledge detail (Step 8B)

Terms for the live Knowledge detail screen and its one remaining sample (Toranjebin). The AI visibility and Evidence by kind cards are hidden as debt, so they get no rows (D6).

| English | Persian |
|---|---|
| Knowledge detail | جزئیات دانش |
| Trace a statement | ردیابی یک گزاره |
| Archive / delete | بایگانی / حذف |
| Toranjebin · Alhagi manna · published · knowledge updated 4 Sep 2026 | ترنجبین · Alhagi manna · منتشرشده · به‌روزرسانی دانش ۱۳ شهریور ۱۴۰۵ |
| of which 318 verified | که ۳۱۸ مورد آن راستی‌آزمایی‌شده است |
| of which {n} verified | که {n} مورد آن راستی‌آزمایی‌شده است |
| 21 gaps open | ۲۱ شکاف باز |
| Archived | بایگانی‌شده |
| Aggregate strength: strong | قوت کلی شواهد: قوی |
| Aggregate strength: conflicting | قوت کلی شواهد: متعارض |
| Could not load the knowledge object ({error}). | بارگذاری پرونده دانش ناموفق بود ({error}). |

## AI executions (Step 9A)

Terms for the AI executions screen. Status labels stand for the API values (succeeded, running, failed, timeout, rate_limited, cancelled, abandoned); provider, model, stage and error codes stay as sent.

| English | Persian |
|---|---|
| Live operational view of every real AI-model invocation, read from AI Core. This screen has no fixture data: until it is connected it shows nothing, and every value shown comes from the API. | نمای عملیاتی زندهٔ هر فراخوانی واقعی مدل هوش مصنوعی، خوانده‌شده از AI Core. این صفحه هیچ دادهٔ نمونه‌ای ندارد: تا وصل نشود چیزی نشان نمی‌دهد، و هر مقداری که نشان داده می‌شود از API می‌آید. |
| Connection | اتصال |
| Not connected. Enter the AI Core URL and an access token. | وصل نیست. نشانی AI Core و یک توکن دسترسی وارد کنید. |
| Executions | اجراها |
| all statuses | همهٔ وضعیت‌ها |
| Failed / timeout / rate-limited | ناموفق / پایان مهلت / محدودیت نرخ |
| Abandoned (outcome unknown) | رهاشده (نتیجه نامعلوم) |
| Timeout | پایان مهلت |
| Rate limited | محدودیت نرخ |
| Abandoned | رهاشده |
| Provider | ارائه‌دهنده |
| Model | مدل |
| Apply filters | اعمال فیلترها |
| Started | آغاز |
| Provider / model | ارائه‌دهنده / مدل |
| Stage | مرحله |
| Tokens in / out | توکن‌های ورودی / خروجی |
| Provider cost | هزینهٔ ارائه‌دهنده |
| Duration | مدت |
| No AI executions yet. An execution is recorded only when a real AI model is actually invoked; fixture and not-configured providers record nothing. | هنوز هیچ اجرای هوش مصنوعی ثبت نشده است. اجرا فقط وقتی ثبت می‌شود که یک مدل واقعی هوش مصنوعی واقعاً فراخوانده شود؛ ارائه‌دهنده‌های نمونه و پیکربندی‌نشده چیزی ثبت نمی‌کنند. |
| Execution detail | جزئیات اجرا |
| Attempt chain | زنجیرهٔ تلاش‌ها |
| Bearer token (kept in memory only) | توکن Bearer (فقط در حافظه نگه داشته می‌شود) |
| Hidden (admin only) | پنهان (فقط مدیر) |
| {currency} {value} (estimated) | {value} {currency} (تخمینی) |
| Not reported | گزارش نشده |
| {n} ms | {n} میلی‌ثانیه |
| (deleted) | (حذف‌شده) |
| first attempt | تلاش نخست |
| Loading AI executions… | در حال بارگذاری اجراهای هوش مصنوعی… |
| Permission denied (HTTP {status}). The token is missing, expired, or not valid for this organization. | دسترسی رد شد (HTTP {status}). توکن وجود ندارد، منقضی شده یا برای این سازمان معتبر نیست. |
| Could not load AI executions: {error}. Check the URL, and that AI Core allows this origin (CORS_ALLOWED_ORIGINS). | بارگذاری اجراهای هوش مصنوعی ناموفق بود: {error}. نشانی را بررسی کنید و مطمئن شوید AI Core این مبدأ را مجاز می‌داند (CORS_ALLOWED_ORIGINS). |
| {from}–{to} of {total} | {from}–{to} از {total} |
| Execution | اجرا |
| Operation | عملیات |
| Model version | نسخهٔ مدل |
| Provider request id | شناسهٔ درخواست ارائه‌دهنده |
| Parent | والد |
| Attempt reason | دلیل تلاش |
| Error | خطا |

## Memory Center (Step 9B)

Terms for the Memory Center screen. Kind and change labels stand for API values; job keys, authors and content stay as sent. JSON, JSONL, CSV and ZIP stay Latin as identifiers.

| English | Persian |
|---|---|
| Everything the AI wrote while working: findings, open questions, checkpoints and handoffs — every version kept, with who wrote it and when. PostgreSQL is the canonical store. Reads are live from AI Core; exports are produced by the backend. | هر آنچه هوش مصنوعی هنگام کار نوشته است: یافته‌ها، پرسش‌های باز، نقطه‌های بازبینی و تحویل‌ها — همهٔ نسخه‌ها نگه داشته می‌شوند، با نویسنده و زمان نوشتن. PostgreSQL مخزن مرجع است. خواندن‌ها زنده از AI Core است؛ خروجی‌ها را بک‌اند تولید می‌کند. |
| Working memory | حافظهٔ کاری |
| Search | جست‌وجو |
| Kind | نوع |
| All kinds | همهٔ انواع |
| Job key | کلید کار |
| Newest first | تازه‌ترین نخست |
| Version | نسخه |
| Latest version only | فقط آخرین نسخه |
| Apply | اعمال |
| Versions | نسخه‌ها |
| Open a memory item to see its versions and compare them. | یک مورد حافظه را باز کنید تا نسخه‌هایش را ببینید و آن‌ها را مقایسه کنید. |
| Export | خروجی‌گیری |
| The export carries this organization's memory only, with provenance and no credentials. Owner or admin. | خروجی فقط حافظهٔ این سازمان را دارد، همراه با منشأ و بدون هیچ اعتبارنامه‌ای. فقط مالک یا مدیر. |
| Markdown | مارک‌داون |
| (everything) | (همه‌چیز) |
| text inside the memory | متنی درون حافظه |
| {n|memory item|memory items} | {n} مورد حافظه |
| Nothing matches. Memory appears once an AI job or an agent has run. | چیزی پیدا نشد. حافظه پس از اجرای یک کار هوش مصنوعی یا یک عامل پدید می‌آید. |
| Written by | نویسنده |
| When | زمان |
| Content | محتوا |
| Field | فیلد |
| Change | تغییر |
| Before | پیش از |
| After | پس از |
| Job state | وضعیت کار |
| AI handoff | تحویل هوش مصنوعی |
| Intermediate finding | یافتهٔ میانی |
| Open question | پرسش باز |
| Current synthesis | جمع‌بندی کنونی |
| Next action | اقدام بعدی |
| Conflict context | زمینهٔ تعارض |
| Processing checkpoint | نقطهٔ بازبینی پردازش |
| AI summary | خلاصهٔ هوش مصنوعی |
| Added | افزوده‌شده |
| Removed | حذف‌شده |
| Changed | تغییرکرده |
| Unchanged | بدون تغییر |
| {n|version|versions} | {n} نسخه |
| Compare | مقایسه |
| with | با |
| The two versions are identical | دو نسخه یکسان‌اند |
| Changed: | تغییرکرده: |
| Could not load memory ({error}). | بارگذاری حافظه ناموفق بود ({error}). |
| Could not compare the versions ({error}). | مقایسهٔ نسخه‌ها ناموفق بود ({error}). |
| Could not load the versions ({error}). | بارگذاری نسخه‌ها ناموفق بود ({error}). |
| Preparing the export… | در حال آماده‌سازی خروجی… |
| Exported as {format}. | خروجی با قالب {format} گرفته شد. |
| Only an owner or admin can export memory. | فقط مالک یا مدیر می‌تواند از حافظه خروجی بگیرد. |
| Could not export ({error}). | خروجی‌گیری ناموفق بود ({error}). |

## Chat settings (Step 9C)

Terms for the Chat settings screen. Option text inside the dropdowns stays English at runtime (the Persian layer skips select), but the rows are kept for the static scan. Topic names, types and policy names stay as sent.

| English | Persian |
|---|---|
| Controls for the knowledge chat on the public website. Choose which knowledge topics it may read, whether it may ask to research online, which AI resource pays for it, and the limits per person. The chat stays off until you enable it here, and every rule on this screen is enforced on the server — not in the browser. | تنظیمات گفت‌وگوی دانش در وب‌سایت عمومی. انتخاب کنید کدام موضوعات دانش را بخواند، آیا می‌تواند برای پژوهش آنلاین اجازه بخواهد، کدام منبع هوش مصنوعی هزینه‌اش را می‌پردازد، و محدودیت‌های هر نفر. گفت‌وگو تا وقتی اینجا روشنش نکنید خاموش می‌ماند، و هر قاعدهٔ این صفحه روی سرور اعمال می‌شود — نه در مرورگر. |
| Save settings | ذخیرهٔ تنظیمات |
| Chat on the website | گفت‌وگو در وب‌سایت |
| Off | خاموش |
| On | روشن |
| Online research | پژوهش آنلاین |
| Never — answer only from stored knowledge | هرگز — فقط از دانش ذخیره‌شده پاسخ بده |
| Ask the person every time | هر بار از کاربر بپرس |
| Allowed without asking each time | بدون پرسیدن در هر بار مجاز است |
| AI resource that pays for answers | منبع هوش مصنوعی که هزینهٔ پاسخ‌ها را می‌پردازد |
| None — the chat cannot call a model | هیچ — گفت‌وگو نمی‌تواند مدلی را فراخوانی کند |
| Answers per person per day | پاسخ برای هر نفر در روز |
| Longest answer (output tokens) | بلندترین پاسخ (توکن‌های خروجی) |
| Knowledge per answer (context tokens) | دانش در هر پاسخ (توکن‌های زمینه) |
| Cost ceiling per answer | سقف هزینهٔ هر پاسخ |
| Keep conversations for (days) | نگهداری گفت‌وگوها (روز) |
| Show sources under each answer | نمایش منابع زیر هر پاسخ |
| Yes | بله |
| No | خیر |
| Collect answer feedback | گردآوری بازخورد پاسخ |
| Knowledge topics the chat may read | موضوعات دانشی که گفت‌وگو می‌تواند بخواند |
| Select none to allow every topic in this workspace. Selecting some makes the list exact: the chat can read nothing else, and a question outside it is answered as a knowledge gap rather than guessed. | هیچ‌کدام را انتخاب نکنید تا همهٔ موضوعات این فضای کاری مجاز باشند. انتخاب برخی، فهرست را دقیق می‌کند: گفت‌وگو چیز دیگری نمی‌تواند بخواند، و به پرسشی خارج از آن به‌جای حدس زدن، به‌عنوان شکاف دانش پاسخ داده می‌شود. |
| no ceiling | بدون سقف |
| keep until deleted | نگهداری تا زمان حذف |
| This workspace has no knowledge topics yet. Add sources and build a topic first. | این فضای کاری هنوز موضوع دانشی ندارد. ابتدا منبع بیفزایید و یک موضوع بسازید. |
| Never configured: the website chat is OFF for this workspace. | هرگز پیکربندی نشده: گفت‌وگوی وب‌سایت برای این فضای کاری خاموش است. |
| The website chat is ON. | گفت‌وگوی وب‌سایت روشن است. |
| Saved, but the website chat is OFF. | ذخیره شد، اما گفت‌وگوی وب‌سایت خاموش است. |
| No AI resource is chosen, so questions are answered as "provider unavailable" rather than guessed. | هیچ منبع هوش مصنوعی انتخاب نشده است، پس به پرسش‌ها به‌جای حدس زدن، با «ارائه‌دهنده در دسترس نیست» پاسخ داده می‌شود. |
| The answer length and the knowledge budget are both required. | طول پاسخ و بودجهٔ دانش هر دو الزامی‌اند. |
| Saving… | در حال ذخیره… |
| Saved. The website chat uses these settings from the next question. | ذخیره شد. گفت‌وگوی وب‌سایت از پرسش بعدی این تنظیمات را به کار می‌برد. |

## AI Catalog (Step 9D)

Terms for the AI Catalog screen. Type and status labels are the filter options' own text (type values like RESEARCH_TOOL, status values like official_source_verified); resource names and URLs stay as sent.

| English | Persian |
|---|---|
| Every AI resource the system knows about — providers, APIs, models, applications, and research tools. Discovery entries stay "Discovered" until verified from an official source; API and pricing information stays empty until then. This screen reads live from AI Core — no sample data. | هر منبع هوش مصنوعی که سامانه می‌شناسد — ارائه‌دهنده‌ها، APIها، مدل‌ها، برنامه‌ها و ابزارهای پژوهشی. مدخل‌ها تا زمانی که از یک منبع رسمی راستی‌آزمایی نشوند «کشف‌شده» می‌مانند؛ اطلاعات API و قیمت تا آن زمان خالی می‌ماند. این صفحه زنده از AI Core می‌خواند — بدون دادهٔ نمونه. |
| Not connected. Connect via the Dashboard, AI executions, or AI Center screen — or enter your AI Core URL and token here. | وصل نیست. از صفحهٔ داشبورد، اجراهای هوش مصنوعی یا مرکز هوش مصنوعی وصل شوید — یا نشانی AI Core و توکن خود را اینجا وارد کنید. |
| All types | همهٔ انواع |
| Application | برنامه |
| Research tool | ابزار پژوهشی |
| Document tool | ابزار سند |
| Search tool | ابزار جست‌وجو |
| Academic tool | ابزار دانشگاهی |
| Parsing tool | ابزار تجزیه |
| Writing tool | ابزار نگارش |
| Education tool | ابزار آموزشی |
| Vision tool | ابزار بینایی |
| Audio tool | ابزار صوتی |
| Multimodal tool | ابزار چندوجهی |
| All statuses | همهٔ وضعیت‌ها |
| Discovered | کشف‌شده |
| Identified | شناسایی‌شده |
| Official source verified | منبع رسمی راستی‌آزمایی‌شده |
| Api capability checked | توانایی API بررسی‌شده |
| Credential method verified | روش اعتبارنامه راستی‌آزمایی‌شده |
| Capability verified | توانایی راستی‌آزمایی‌شده |
| Health checked | سلامت بررسی‌شده |
| Active | فعال |
| Application only | فقط برنامه |
| Model only | فقط مدل |
| Specialized research tool | ابزار پژوهشی تخصصی |
| No verified api | بدون API راستی‌آزمایی‌شده |
| Not verified | راستی‌آزمایی‌نشده |
| Blocked external dependency | وابستگی بیرونی مسدودشده |
| Disabled | غیرفعال |
| Import initial list | وارد کردن فهرست اولیه |
| {n|resource in catalog|resources in catalog} | {n} منبع در فهرست |
| No results matching the current filters. | با فیلترهای کنونی نتیجه‌ای پیدا نشد. |
| Connected to {base}. | به {base} وصل است. |
| Could not load the catalog ({error}). | بارگذاری فهرست ناموفق بود ({error}). |
| Imported {inserted} new, {present} already present. | {inserted} مورد تازه وارد شد، {present} مورد از پیش بود. |
| Could not import the list ({error}). | وارد کردن فهرست ناموفق بود ({error}). |

## AI Center (Step 9E)

Terms for the AI Center screen. Mode labels are the Create form's own options; provider, account, model, agent and job names, API values (health, verification) and server messages stay as sent. Option text inside dropdowns stays English at runtime (the Persian layer skips select).

| English | Persian |
|---|---|
| Providers, accounts, models, routing, long-running jobs with checkpoints and handoffs, shared memory and the discovery registry — read from and written to AI Core. No sample data: until connected this screen shows nothing. | ارائه‌دهنده‌ها، حساب‌ها، مدل‌ها، مسیریابی، کارهای طولانی با نقطه‌های بازبینی و تحویل، حافظهٔ مشترک و فهرست کشف — خواندن و نوشتن در AI Core. بدون دادهٔ نمونه: تا وصل نشود، این صفحه چیزی نشان نمی‌دهد. |
| Not connected. | وصل نیست. |
| Providers & accounts | ارائه‌دهنده‌ها و حساب‌ها |
| Routing | مسیریابی |
| Jobs & memory | کارها و حافظه |
| Agent network | شبکهٔ عامل‌ها |
| Shared memory | حافظهٔ مشترک |
| Discovery | کشف |
| AI Center sections | بخش‌های مرکز هوش مصنوعی |
| Providers | ارائه‌دهنده‌ها |
| Registered AI providers | ارائه‌دهنده‌های ثبت‌شدهٔ هوش مصنوعی |
| Adapter | آداپتور |
| Verification | راستی‌آزمایی |
| Credential method | روش اعتبارنامه |
| Add provider | افزودن ارائه‌دهنده |
| Official URL | نشانی رسمی |
| API base URL | نشانی پایهٔ API |
| None (registry only) | هیچ (فقط در فهرست) |
| anthropic | آنتروپیک |
| openai | اوپن‌ای‌آی |
| Accounts | حساب‌ها |
| Every account is tracked separately: credential, health, failures, limits. Unknown quota or balance is shown as "Unknown", never 0. Credentials are write-only. | هر حساب جداگانه پیگیری می‌شود: اعتبارنامه، سلامت، خطاها، محدودیت‌ها. سهمیه یا موجودی ناشناخته «نامعلوم» نشان داده می‌شود، هرگز ۰. اعتبارنامه‌ها فقط نوشتنی‌اند. |
| Provider accounts | حساب‌های ارائه‌دهنده |
| Account | حساب |
| Credential | اعتبارنامه |
| Health | سلامت |
| Failures | خطاها |
| Remaining tokens | توکن‌های باقی‌مانده |
| Add account | افزودن حساب |
| Label | برچسب |
| Plan | طرح |
| Set or rotate a credential | تنظیم یا چرخش اعتبارنامه |
| Secret (never shown again) | رمز (دیگر هرگز نشان داده نمی‌شود) |
| Save credential | ذخیرهٔ اعتبارنامه |
| e.g. Account A | مثلاً حساب A |
| Models and their limits | مدل‌ها و محدودیت‌هایشان |
| Limits are what the provider documents for your account. Providers change them, so enter them here rather than trusting a built-in table. Empty means "Unknown" and blocks nothing. A job item larger than a known input limit, or a job reserving more output than a known output limit, fails with CONTEXT_OVERFLOW or OUTPUT_EXCEEDS_MODEL_LIMIT before any call: it is never truncated. Without a max input, the room is the context window minus the output reserve. Requests and tokens per minute are recorded, not yet enforced. | محدودیت‌ها همان‌هایی‌اند که ارائه‌دهنده برای حساب شما مستند کرده است. ارائه‌دهنده‌ها آن‌ها را تغییر می‌دهند، پس به‌جای اعتماد به یک جدول درونی، آن‌ها را اینجا وارد کنید. خالی یعنی «نامعلوم» و جلوی چیزی را نمی‌گیرد. یک مورد کار بزرگ‌تر از محدودیت ورودی شناخته‌شده، یا کاری که بیش از محدودیت خروجی شناخته‌شده خروجی رزرو کند، پیش از هر فراخوانی با CONTEXT_OVERFLOW یا OUTPUT_EXCEEDS_MODEL_LIMIT ناموفق می‌شود: هرگز کوتاه نمی‌شود. بدون حداکثر ورودی، فضا برابر پنجرهٔ زمینه منهای رزرو خروجی است. درخواست‌ها و توکن‌ها در دقیقه ثبت می‌شوند، اما هنوز اعمال نمی‌شوند. |
| Registered models and their limits | مدل‌های ثبت‌شده و محدودیت‌هایشان |
| Context window | پنجرهٔ زمینه |
| Max input | حداکثر ورودی |
| Max output | حداکثر خروجی |
| RPM / TPM | درخواست / توکن در دقیقه |
| Register a model | ثبت یک مدل |
| Model name (as the provider spells it) | نام مدل (همان‌طور که ارائه‌دهنده می‌نویسد) |
| Context window (tokens) | پنجرهٔ زمینه (توکن) |
| Max input tokens | حداکثر توکن‌های ورودی |
| Max output tokens | حداکثر توکن‌های خروجی |
| Requests per minute | درخواست در دقیقه |
| Tokens per minute | توکن در دقیقه |
| Where the figures come from | این ارقام از کجا آمده‌اند |
| Provider documentation | مستندات ارائه‌دهنده |
| Provider API | API ارائه‌دهنده |
| Entered by an operator | واردشده توسط یک کاربر |
| Conservative estimate | برآورد محتاطانه |
| Register model | ثبت مدل |
| Edit limits | ویرایش محدودیت‌ها |
| Save limits | ذخیرهٔ محدودیت‌ها |
| claude-sonnet-4-6 | مثلاً claude-sonnet-4-6 |
| Routing policies | سیاست‌های مسیریابی |
| Modes: manual single, manual ordered chain, stage-based manual, automatic pool, automatic priority pool, hybrid. "Explain" shows which resource would be chosen now and why every other one is skipped. | حالت‌ها: دستی تکی، زنجیرهٔ دستی مرتب، دستی بر پایهٔ مرحله، استخر خودکار، استخر اولویت‌دار خودکار، ترکیبی. «توضیح» نشان می‌دهد اکنون کدام منبع انتخاب می‌شود و چرا هر منبع دیگر کنار گذاشته می‌شود. |
| Create a routing policy | ساخت یک سیاست مسیریابی |
| Mode | حالت |
| Manual — one model | دستی — یک مدل |
| Manual chain — try in order | زنجیرهٔ دستی — به ترتیب امتحان کن |
| Stage-based — a model per stage | بر پایهٔ مرحله — یک مدل برای هر مرحله |
| Automatic pool | استخر خودکار |
| Priority pool — try in order, skipping unhealthy | استخر اولویت‌دار — به ترتیب امتحان کن و ناسالم‌ها را رد کن |
| Hybrid | ترکیبی |
| First step: account | گام نخست: حساب |
| First step: model | گام نخست: مدل |
| Stage (stage-based only) | مرحله (فقط بر پایهٔ مرحله) |
| Cost ceiling per job | سقف هزینهٔ هر کار |
| Create policy | ساخت سیاست |
| Job status, checkpoint and handoff | وضعیت کار، نقطهٔ بازبینی و تحویل |
| Open job | باز کردن کار |
| Knowledge transfer packages | بسته‌های انتقال دانش |
| What workers handed back as structured findings, and what the validator and reconciler did with each claim. Nothing a worker returns becomes approved knowledge: accepted claims and evidence are drafts for review. A quote that cannot be found in the stored source text is rejected as a citation mismatch. Rejected items stay listed here with their reason. | آنچه کارگزاران به‌صورت یافته‌های ساختاریافته برگرداندند، و آنچه اعتبارسنج و تطبیق‌دهنده با هر ادعا کردند. هیچ‌چیزی که یک کارگزار برمی‌گرداند دانش تأییدشده نمی‌شود: ادعاها و شواهد پذیرفته‌شده پیش‌نویس‌هایی برای بررسی‌اند. نقل‌قولی که در متن ذخیره‌شدهٔ منبع پیدا نشود، به‌عنوان ناهمخوانی استناد رد می‌شود. موارد ردشده با دلیلشان اینجا فهرست می‌مانند. |
| Reconciled | تطبیق‌یافته |
| Partly reconciled | تا حدی تطبیق‌یافته |
| Nothing accepted | چیزی پذیرفته نشد |
| Invalid | نامعتبر |
| Received | دریافت‌شده |
| From | از |
| Claims accepted | ادعاهای پذیرفته‌شده |
| Outcomes | نتیجه‌ها |
| Semantic memory backend | بک‌اند حافظهٔ معنایی |
| Agent orchestration console | کنسول هماهنگی عامل‌ها |
| Every action below calls AI Core. Running a task goes through the canonical AI path (an AI job whose calls are recorded as AIExecutions) using only the AI accounts the agent declares; a handoff is stored with a shared-memory checkpoint and only the addressed agent can accept it. | هر کنش زیر AI Core را فرا می‌خواند. اجرای یک کار از مسیر مرجع هوش مصنوعی می‌گذرد (یک کار هوش مصنوعی که فراخوانی‌هایش به‌صورت AIExecution ثبت می‌شوند) و فقط از حساب‌هایی استفاده می‌کند که عامل اعلام کرده است؛ تحویل با یک نقطهٔ بازبینی حافظهٔ مشترک ذخیره می‌شود و فقط عامل مخاطب می‌تواند آن را بپذیرد. |
| 1. Register an agent | ۱. ثبت یک عامل |
| research | پژوهش |
| evidence | شاهد |
| knowledge | دانش |
| content | محتوا |
| reviewer | بازبین |
| planner | برنامه‌ریز |
| summarizer | خلاصه‌ساز |
| translator | مترجم |
| commerce | تجارت |
| custom | سفارشی |
| Capabilities (comma-separated) | توانایی‌ها (جداشده با ویرگول) |
| Allowed AI accounts | حساب‌های مجاز هوش مصنوعی |
| Register agent | ثبت عامل |
| 2. Grant memory access | ۲. اعطای دسترسی به حافظه |
| Agent | عامل |
| Memory profile | نمایهٔ حافظه |
| Access | دسترسی |
| read | خواندن |
| write | نوشتن |
| admin | مدیر |
| Grant | اعطا |
| 3. Start a session | ۳. آغاز یک نشست |
| Session key | کلید نشست |
| Goal | هدف |
| Start session | آغاز نشست |
| 4. Add a task | ۴. افزودن یک کار |
| Session ID | شناسهٔ نشست |
| Task type | نوع کار |
| Task key | کلید کار |
| Add task | افزودن کار |
| 5. Run a task with an agent | ۵. اجرای یک کار با یک عامل |
| Task ID | شناسهٔ کار |
| Routing policy | سیاست مسیریابی |
| Instruction | دستور |
| Continue from handoff ID (optional) | ادامه از شناسهٔ تحویل (اختیاری) |
| Run | اجرا |
| 6. Hand off to another agent | ۶. تحویل به عاملی دیگر |
| Completed task ID | شناسهٔ کار انجام‌شده |
| From agent | از عامل |
| To agent | به عامل |
| Create handoff | ساخت تحویل |
| 7. Accept a handoff | ۷. پذیرش یک تحویل |
| Handoff ID | شناسهٔ تحویل |
| Receiving agent | عامل دریافت‌کننده |
| Accept | پذیرش |
| extract | مثلاً extract |
| research, summarize | مثلاً research, summarize |
| Internal and external Agents that perform coordinated tasks. Agents use AI resources but are a separate concept from AI providers. | عامل‌های درونی و بیرونی که کارهای هماهنگ انجام می‌دهند. عامل‌ها از منابع هوش مصنوعی استفاده می‌کنند، اما مفهومی جدا از ارائه‌دهنده‌های هوش مصنوعی‌اند. |
| Session inspector | بازرس نشست |
| Tasks, handoffs and agent-to-agent messages of one orchestration session — read from AI Core. | کارها، تحویل‌ها و پیام‌های عامل به عامل یک نشست هماهنگی — خوانده‌شده از AI Core. |
| Inspect | بررسی |
| Shared memory — runtime view | حافظهٔ مشترک — نمای زمان اجرا |
| Configure in Settings › Shared memory. | در تنظیمات › حافظهٔ مشترک پیکربندی کنید. |
| is always the canonical store. | همیشه مخزن مرجع است. |
| Canonical store | مخزن مرجع |
| Semantic backend | بک‌اند معنایی |
| AI Resource Discovery Registry | فهرست کشف منابع هوش مصنوعی |
| A discovered name is not an integration. Entries start as "discovered" with proposed types labelled as inference; API, pricing and quota stay unknown until verified from an official source. | یک نام کشف‌شده یک یکپارچه‌سازی نیست. مدخل‌ها با وضعیت «کشف‌شده» و نوع‌های پیشنهادی برچسب‌خورده به‌عنوان استنباط آغاز می‌شوند؛ API، قیمت و سهمیه تا راستی‌آزمایی از یک منبع رسمی نامعلوم می‌مانند. |
| Import the initial discovery list | وارد کردن فهرست اولیهٔ کشف |
| discovered | کشف‌شده |
| identified | شناسایی‌شده |
| official_source_verified | منبع رسمی راستی‌آزمایی‌شده |
| approved | تأییدشده |
| active | فعال |
| application_only | فقط برنامه |
| no_verified_api | بدون API راستی‌آزمایی‌شده |
| not_verified | راستی‌آزمایی‌نشده |
| disabled | غیرفعال |
| AI resource discovery registry | فهرست کشف منابع هوش مصنوعی |
| Proposed types | نوع‌های پیشنهادی |
| Last verified | آخرین راستی‌آزمایی |
| API URL | نشانی API |
| No providers registered yet. | هنوز هیچ ارائه‌دهنده‌ای ثبت نشده است. |
| No accounts yet. | هنوز هیچ حسابی وجود ندارد. |
| No models registered yet. Routing still works; limits are then unknown. | هنوز هیچ مدلی ثبت نشده است. مسیریابی همچنان کار می‌کند؛ محدودیت‌ها در این حالت نامعلوم‌اند. |
| (no adapter) | (بدون آداپتور) |
| (disabled) | (غیرفعال) |
| Not set | تنظیم نشده |
| Set ••••{last4} | تنظیم‌شده ••••{last4} |
| Test connection | آزمایش اتصال |
| Enable | فعال‌سازی |
| Disable | غیرفعال‌سازی |
| Testing {label}… | در حال آزمایش {label}… |
| No routing policies yet. Create one with the form above. | هنوز هیچ سیاست مسیریابی‌ای وجود ندارد. با فرم بالا یکی بسازید. |
| Save | ذخیره |
| Remove ceiling | حذف سقف |
| Delete policy | حذف سیاست |
| Delete the policy "{name}"? A policy that has already run jobs is kept. | سیاست «{name}» حذف شود؟ سیاستی که پیش‌تر کار اجرا کرده است نگه داشته می‌شود. |
| {model} on account {account} | {model} روی حساب {account} |
| Move up | انتقال به بالا |
| Move down | انتقال به پایین |
| Remove | حذف |
| Add step | افزودن گام |
| Explain current choice | توضیح انتخاب کنونی |
| No usable resource — stop reason: {reason} | هیچ منبع قابل‌استفاده‌ای نیست — دلیل توقف: {reason} |
| Policy created. Add more steps to set a fallback order. | سیاست ساخته شد. برای تعیین ترتیب جایگزین، گام‌های بیشتری بیفزایید. |
| Policy saved. | سیاست ذخیره شد. |
| Policy deleted. | سیاست حذف شد. |
| Cost ceiling removed. | سقف هزینه حذف شد. |
| Step added. | گام افزوده شد. |
| Step removed. | گام حذف شد. |
| Order saved — position 0 is tried first. | ترتیب ذخیره شد — جایگاه ۰ اول امتحان می‌شود. |
| Add a provider account first, on the Providers & accounts tab. | ابتدا در زبانهٔ ارائه‌دهنده‌ها و حساب‌ها یک حساب ارائه‌دهنده بیفزایید. |
| The first step needs a model. | گام نخست به یک مدل نیاز دارد. |
| Edit limits — {name} | ویرایش محدودیت‌ها — {name} |
| Limits must be whole numbers of at least 1 ({field}). | محدودیت‌ها باید عدد صحیح و دست‌کم ۱ باشند ({field}). |
| Registering {name}… | در حال ثبت {name}… |
| Saving limits… | در حال ذخیرهٔ محدودیت‌ها… |
| Limits saved. | محدودیت‌ها ذخیره شد. |
| Model registered. | مدل ثبت شد. |
| Add a provider first. | ابتدا یک ارائه‌دهنده بیفزایید. |
| The model name is required. | نام مدل الزامی است. |
| Provider name is required. | نام ارائه‌دهنده الزامی است. |
| Provider added. | ارائه‌دهنده افزوده شد. |
| Provider and label are required. | ارائه‌دهنده و برچسب الزامی‌اند. |
| Account added. | حساب افزوده شد. |
| Account and secret are required. | حساب و رمز الزامی‌اند. |
| Credential saved (encrypted; it will not be shown again). | اعتبارنامه ذخیره شد (رمزنگاری‌شده؛ دیگر نشان داده نمی‌شود). |
| Could not load: {error} | بارگذاری ناموفق بود: {error} |
| Both fields are required. | هر دو فیلد الزامی‌اند. |
| Operator | کاربر |

## Command workspace (Step 9F)

Terms for the Command workspace screen. State labels stand for API values; command text, titles, server messages and scope values stay as sent. Option text inside dropdowns stays English at runtime (the Persian layer skips select).

| English | Persian |
|---|---|
| Type a research or knowledge command. It is saved to AI Core as you type, so closing this page loses nothing. Before anything runs you see what it will do and exactly what it will act on. Once a version has run it is kept as it was; editing starts the next version. Long work keeps going on the server after you leave, and you can continue it when you come back. | یک فرمان پژوهشی یا دانشی بنویسید. همان‌طور که تایپ می‌کنید در AI Core ذخیره می‌شود، پس بستن این صفحه چیزی را از دست نمی‌دهد. پیش از اجرای هر چیز، می‌بینید چه خواهد کرد و دقیقاً روی چه چیزی کار خواهد کرد. نسخه‌ای که اجرا شده همان‌طور که بود نگه داشته می‌شود؛ ویرایش، نسخهٔ بعدی را آغاز می‌کند. کارهای طولانی پس از رفتن شما روی سرور ادامه می‌یابند و وقتی برگردید می‌توانید آن‌ها را ادامه دهید. |
| New command | فرمان جدید |
| Drafts | پیش‌نویس‌ها |
| Waiting to continue | در انتظار ادامه |
| Completed with gaps | انجام‌شده با شکاف |
| Search your commands | جست‌وجو در فرمان‌های شما |
| Continue | ادامه |
| View result | دیدن نتیجه |
| Restart as a new version | آغاز دوباره به‌عنوان نسخهٔ جدید |
| Choose a command on the left, or start a new one. | یک فرمان را از سمت چپ انتخاب کنید، یا یک فرمان جدید آغاز کنید. |
| Command | فرمان |
| Scope, model and budget | دامنه، مدل و بودجه |
| What it should do | چه کاری باید بکند |
| Work it out from the text | از متن تشخیص بده |
| Research the evidence (uses a model) | پژوهش در شواهد (از یک مدل استفاده می‌کند) |
| Write a synthesis (uses a model) | نوشتن یک جمع‌بندی (از یک مدل استفاده می‌کند) |
| Research one matrix section (uses a model) | پژوهش در یک بخش ماتریس (از یک مدل استفاده می‌کند) |
| Find contradictions | یافتن تعارض‌ها |
| Evidence for one claim | شواهد برای یک ادعا |
| Claims from a document page | ادعاها از یک صفحهٔ سند |
| Unsupported statements | گزاره‌های بدون پشتوانه |
| Does a section apply across the category | آیا یک بخش در سراسر دسته کاربرد دارد |
| Reprocess a document | پردازش دوبارهٔ یک سند |
| Continue my previous task | ادامهٔ کار قبلی من |
| Section key | کلید بخش |
| Document id | شناسهٔ سند |
| Page | صفحه |
| Claim id | شناسهٔ ادعا |
| Context per call (tokens) | زمینه در هر فراخوانی (توکن) |
| Output per call (tokens) | خروجی در هر فراخوانی (توکن) |
| Most model calls | بیشترین فراخوانی مدل |
| Most it may cost | بیشترین هزینهٔ مجاز |
| If the budget is too small, process the most important parts and leave the rest visibly pending | اگر بودجه کم باشد، مهم‌ترین بخش‌ها را پردازش کن و بقیه را آشکارا در انتظار بگذار |
| Check the plan | بررسی برنامه |
| Run again as a new version | اجرای دوباره به‌عنوان نسخهٔ جدید |
| Archive | بایگانی |
| Delete permanently | حذف همیشگی |
| Keyboard: Ctrl+Enter checks the plan, then runs it. Ctrl+S saves now. | صفحه‌کلید: Ctrl+Enter برنامه را بررسی و سپس اجرا می‌کند. Ctrl+S همین حالا ذخیره می‌کند. |
| Result | نتیجه |
| Nothing has run yet. | هنوز چیزی اجرا نشده است. |
| Your commands | فرمان‌های شما |
| For example: Analyze all human studies on Toranjebin safety. | برای نمونه: همهٔ مطالعات انسانی دربارهٔ ایمنی ترنجبین را تحلیل کن. |
| e.g. safety | مثلاً safety |
| no limit | بدون محدودیت |
| No commands here yet. | هنوز فرمانی اینجا نیست. |
| Untitled | بی‌عنوان |
| Untitled command | فرمان بی‌عنوان |
| Continue your previous task? | کار قبلی خود را ادامه می‌دهید؟ |
| Version {n} | نسخهٔ {n} |
| Version {n} · has run, read-only — editing starts version {next} | نسخهٔ {n} · اجرا شده و فقط‌خواندنی است — ویرایش، نسخهٔ {next} را آغاز می‌کند |
| This browser has unsaved text from an earlier visit. | این مرورگر متن ذخیره‌نشده‌ای از بازدید قبلی دارد. |
| Use it | استفاده از آن |
| Saved to AI Core · revision {rev}. | در AI Core ذخیره شد · بازبینی {rev}. |
| Saved to AI Core · version {v}, revision {rev}. | در AI Core ذخیره شد · نسخهٔ {v}، بازبینی {rev}. |
| This draft was changed in another tab or device. | این پیش‌نویس در زبانه یا دستگاه دیگری تغییر کرده است. |
| Use the saved version | استفاده از نسخهٔ ذخیره‌شده |
| Keep mine | نسخهٔ خودم را نگه دار |
| Loaded the saved version. | نسخهٔ ذخیره‌شده بارگذاری شد. |
| Not saved yet ({error}). Your text is kept in this browser until it is. | هنوز ذخیره نشده ({error}). متن شما تا آن زمان در این مرورگر نگه داشته می‌شود. |
| Restore from archive | بازگرداندن از بایگانی |
| It will: {what} | کاری که خواهد کرد: {what} |
| It will: {what} (you chose this; the text suggested “{proposed}”) | کاری که خواهد کرد: {what} (شما این را انتخاب کردید؛ متن «{proposed}» را پیشنهاد می‌کرد) |
| Before it can run, set: {fields}. | پیش از اجرا، این‌ها را تنظیم کنید: {fields}. |
| Acts on: {scope} | روی این کار می‌کند: {scope} |
| started {d} | آغاز {d} |
| finished {d} | پایان {d} |
| (empty) | (خالی) |
| View | دیدن |
| Restore as a new draft | بازگرداندن به‌عنوان پیش‌نویس جدید |
| Compare with v{n} | مقایسه با v{n} |
| Restored v{n} as the current draft; history is unchanged. | v{n} به‌عنوان پیش‌نویس کنونی بازگردانده شد؛ تاریخچه تغییری نکرد. |
| Same text. | متن یکسان است. |
| Set {fields} first (open “Scope, model and budget”). | ابتدا {fields} را تنظیم کنید («دامنه، مدل و بودجه» را باز کنید). |
| Plan ready — check what it will act on, then run. | برنامه آماده است — بررسی کنید روی چه چیزی کار می‌کند، سپس اجرا کنید. |
| Running on the server. You can close this page; it will keep going. | روی سرور در حال اجراست. می‌توانید این صفحه را ببندید؛ کار ادامه می‌یابد. |
| Continuing from the last checkpoint; finished work is not redone. | ادامه از آخرین نقطهٔ بازبینی؛ کار انجام‌شده دوباره انجام نمی‌شود. |
| Running again as a new version; the earlier result is kept. | اجرای دوباره به‌عنوان نسخهٔ جدید؛ نتیجهٔ قبلی نگه داشته می‌شود. |
| Cancelled. | لغو شد. |
| Restored from the archive. | از بایگانی بازگردانده شد. |
| Archived. Find it with Show set to Archived. | بایگانی شد. با تنظیم «نمایش» روی «بایگانی‌شده» پیدایش کنید. |
| Delete this command and every one of its versions permanently? Archive keeps them instead. | این فرمان و همهٔ نسخه‌هایش برای همیشه حذف شوند؟ بایگانی آن‌ها را نگه می‌دارد. |
| Deleted permanently. | برای همیشه حذف شد. |
| Represented | بازنمایی‌شده |
| Merged as duplicates | ادغام‌شده به‌عنوان تکراری |
| Contested, both sides kept | مورد مناقشه، هر دو سو نگه داشته شد |
| Unresolved | حل‌نشده |
| Pending (not processed) | در انتظار (پردازش‌نشده) |
| Lost | ازدست‌رفته |
| No claims recorded on this page. | هیچ ادعایی در این صفحه ثبت نشده است. |
| No contradictions recorded. | هیچ تعارضی ثبت نشده است. |
| Every statement has a source. | هر گزاره منبعی دارد. |
| Turn into a cited publication | تبدیل به یک انتشار مستند |
| Published — open Publications | منتشر شد — انتشارات را باز کنید |

## AI Visibility and access (Step 10)

Terms for AI Visibility, its full report and AI access. Platform, agent and vendor names are identifiers and stay as sent; enum values without a label are shown as sent.

| English | Persian |
|---|---|
| AI visibility (AI Core) | دیده‌شدن در هوش مصنوعی (AI Core) |
| AI visibility report (AI Core) | گزارش دیده‌شدن در هوش مصنوعی (AI Core) |
| AI access (AI Core) | دسترسی هوش مصنوعی (AI Core) |
| Other platform | سکوی دیگر |
| Operator unknown | گرداننده نامشخص |
| {n\|observation\|observations} recorded. Each signal is counted on its own; there is no combined score. | {n} مشاهده ثبت شده است. هر نشانه جداگانه شمرده می‌شود؛ هیچ امتیاز ترکیبی وجود ندارد. |
| {n\|automated client\|automated clients} seen. Human visitors are never listed here. | {n} کلاینت خودکار دیده شده است. بازدیدکنندگان انسانی هرگز اینجا فهرست نمی‌شوند. |
| The latest {n} of {total\|observation\|observations}. Open one to read the question and the answer as recorded. | {n} مورد تازه از {total} مشاهده. یکی را باز کنید تا پرسش و پاسخ را همان‌طور که ثبت شده بخوانید. |
| {n\|rule\|rules}. The first rule that matches wins and evaluation stops; a client no rule matches is allowed and recorded as Not configured. | {n} قاعده. نخستین قاعده‌ای که منطبق شود اعمال می‌شود و ارزیابی متوقف می‌شود؛ کلاینتی که با هیچ قاعده‌ای منطبق نشود اجازه می‌یابد و به‌عنوان «پیکربندی‌نشده» ثبت می‌شود. |
| An agent not seen recently | عاملی که اخیراً دیده نشده است |
| Terms | شرایط |
| Any | هر |
| {n\|distinct client\|distinct clients}. There is no filter that hides unrecognised ones. | {n} کلاینت متمایز. هیچ فیلتری کلاینت‌های ناشناخته را پنهان نمی‌کند. |
| Human visitor | بازدیدکنندهٔ انسانی |
| Search crawler | خزندهٔ جست‌وجو |
| AI crawler (indexing) | خزندهٔ هوش مصنوعی (نمایه‌سازی) |
| AI answering a user | هوش مصنوعی در حال پاسخ به کاربر |
| Agent acting for a user | عامل از طرف کاربر |
| Unrecognised automated client | کلاینت خودکار ناشناخته |
| Any human visitor | هر بازدیدکنندهٔ انسانی |
| Any search crawler | هر خزندهٔ جست‌وجو |
| Any AI crawler | هر خزندهٔ هوش مصنوعی |
| Any AI answering a user | هر هوش مصنوعی در حال پاسخ به کاربر |
| Any agent acting for a user | هر عامل از طرف کاربر |
| Any unrecognised client | هر کلاینت ناشناخته |
| Any automated client | هر کلاینت خودکار |
| Training | آموزش مدل |
| Search indexing | نمایه‌سازی جست‌وجو |
| Answering | پاسخ‌دادن |
| Acting for a user | اقدام از طرف کاربر |
| Link preview | پیش‌نمایش پیوند |
| Not declared | اعلام‌نشده |
| Detected | شناسایی‌شده |
| Probable | محتمل |
| Free | رایگان |
| Paid | پولی |
| Forbidden | ممنوع |
| Not configured | پیکربندی‌نشده |
| Mentioned | نام برده شد |
| Cited | استناد شد |
| Recommended | پیشنهاد شد |
| Product shown | محصول نشان داده شد |
| URL present | نشانی وب آمد |
| Present | هست |
| Absent | نیست |
| Not checked | بررسی نشد |
| Direct question | پرسش مستقیم |
| Brand question | پرسش دربارهٔ برند |
| Product question | پرسش دربارهٔ محصول |
| Comparison | مقایسه |
| Citation check | بررسی استناد |
| Pasted by hand | چسباندن دستی |
| Platform API | API سکو |
| Automated browser | مرورگر خودکار |
| Imported | واردشده |
| How AI platforms answer about you | سکوهای هوش مصنوعی دربارهٔ شما چه پاسخی می‌دهند |
| Observations by signal | مشاهده‌ها بر پایهٔ نشانه |
| Signal | نشانه |
| Who is actually visiting your site | واقعاً چه کسی از سایت شما بازدید می‌کند |
| Automated clients seen | کلاینت‌های خودکار دیده‌شده |
| Actor type | نوع کنشگر |
| Confidence | اطمینان |
| Requests seen | درخواست‌های دیده‌شده |
| No automated clients seen yet. | هنوز هیچ کلاینت خودکاری دیده نشده است. |
| Could not load AI visibility ({error}). | بارگذاری دیده‌شدن در هوش مصنوعی ممکن نشد ({error}). |
| Observations | مشاهده‌ها |
| Observation | مشاهده |
| Platform observations, newest first | مشاهده‌های سکو، تازه‌ترین نخست |
| Platform | سکو |
| Question | پرسش |
| Tested | زمان آزمون |
| Test | آزمون |
| Collected | روش گردآوری |
| Not recorded | ثبت نشده |
| Answer as recorded | پاسخ همان‌طور که ثبت شد |
| No answer was recorded. | هیچ پاسخی ثبت نشد. |
| No observations recorded yet. | هنوز هیچ مشاهده‌ای ثبت نشده است. |
| Could not load the observations ({error}). | بارگذاری مشاهده‌ها ممکن نشد ({error}). |
| Rules, most specific first | قاعده‌ها، دقیق‌ترین نخست |
| Access rules in precedence order | قاعده‌های دسترسی به ترتیب اولویت |
| Applies to | اعمال بر |
| Purpose | هدف |
| Decision | تصمیم |
| Reason given to the agent | دلیلی که به عامل گفته می‌شود |
| No reason given | دلیلی داده نشده |
| No rules yet. | هنوز هیچ قاعده‌ای نیست. |
| Every agent seen | همهٔ عامل‌های دیده‌شده |
| Automated clients observed | کلاینت‌های خودکار مشاهده‌شده |
| Stated purpose | هدف اعلام‌شده |
| Identification | شناسایی |
| Could not load AI access ({error}). | بارگذاری دسترسی هوش مصنوعی ممکن نشد ({error}). |
| Two different questions, kept separate on purpose: how AI platforms answer about you, and which AI systems actually visit your site. | دو پرسش متفاوت، که عمداً جدا نگه داشته شده‌اند: سکوهای هوش مصنوعی دربارهٔ شما چه پاسخی می‌دهند، و کدام سامانه‌های هوش مصنوعی واقعاً از سایت شما بازدید می‌کنند. |
| 47 observations across 4 platforms, last 30 days. This is a sample of specific prompts on specific days — not a claim about every possible question, and not a score (ADR-064 forbids collapsing these into one number). | ۴۷ مشاهده در ۴ سکو، ۳۰ روز گذشته. این نمونه‌ای از پرسش‌های مشخص در روزهای مشخص است — نه ادعایی دربارهٔ هر پرسش ممکن، و نه یک امتیاز (ADR-064 فروکاستن این‌ها به یک عدد را ممنوع می‌کند). |
| The brand appeared in the answer. | نام برند در پاسخ آمد. |
| Whether a source link was attached was not examined in this batch. | در این دسته بررسی نشد که پیوند منبعی پیوست شده بود یا نه. |
| Named as a suggested option, not just mentioned. | به‌عنوان گزینهٔ پیشنهادی نام برده شد، نه فقط اشاره. |
| Checked for, and not present — a real negative finding, not a gap in the data. | بررسی شد و نبود — یک یافتهٔ منفی واقعی، نه شکافی در داده. |
| Not examined in this batch. | در این دسته بررسی نشد. |
| Click, and purchase that followed a click, have no columns here on purpose — a click happens in the platform's own interface, out of reach; a purchase belongs to commerce data, not to this observation (see the model's own documentation, ADR-062). Guessing either would be a fabricated number wearing a real one's clothes. | کلیک، و خریدی که پس از کلیک آمد، عمداً اینجا ستونی ندارند — کلیک در رابط خود سکو رخ می‌دهد و دور از دسترس است؛ خرید به دادهٔ تجارت تعلق دارد، نه به این مشاهده (مستندات خود مدل را ببینید، ADR-062). حدس زدن هر کدام عددی ساختگی در جامهٔ عددی واقعی خواهد بود. |
| 2,085 automated requests, last 30 days. Ordinary human visitors are never logged here — this exists to understand machine access, not to track people. | ۲٬۰۸۵ درخواست خودکار، ۳۰ روز گذشته. بازدیدکنندگان انسانی عادی هرگز اینجا ثبت نمی‌شوند — این بخش برای فهم دسترسی ماشین‌هاست، نه ردیابی مردم. |
| Traffic by detected actor type | ترافیک بر پایهٔ نوع کنشگر شناسایی‌شده |
| Signature | امضا |
| Requests (30d) | درخواست‌ها (۳۰ روز) |
| No known signature matched | هیچ امضای شناخته‌شده‌ای منطبق نشد |
| A User-Agent header is a claim a request makes about itself, not a verified identity — anyone can send . Every row above is | سرآیند User-Agent ادعایی است که درخواست دربارهٔ خودش می‌کند، نه هویتی تأییدشده — هر کسی می‌تواند این را بفرستد: . هر ردیف بالا |
| (header matched) or | است (سرآیند منطبق شد) یا |
| (weaker pattern); | (الگوی ضعیف‌تر)؛ |
| would need reverse-DNS confirmation, which is not built yet. Location and time-on-site ARE now collected, by an explicit owner decision recorded as ADR-079, which supersedes the earlier narrowing in ADR-046 (kept on file, unedited). See | به تأیید reverse-DNS نیاز دارد که هنوز ساخته نشده است. مکان و مدت ماندن در سایت اکنون گردآوری می‌شوند، با تصمیم صریح مالک که به‌عنوان ADR-079 ثبت شده و محدودسازی پیشین در ADR-046 را کنار می‌گذارد (که بدون ویرایش نگه داشته شده است). ببینید: |
| for what is stored and for how long. | برای اینکه چه چیزی و تا چه مدت نگه داشته می‌شود. |
| Full report | گزارش کامل |
| Visible to AI — full report | دیده‌شدن در هوش مصنوعی — گزارش کامل |
| Everything behind the two numbers on the dashboard, broken down by time, location, page and query — and exportable. | هر آنچه پشت دو عدد داشبورد است، به تفکیک زمان، مکان، صفحه و پرسش — و قابل خروجی‌گرفتن. |
| Who may read this site, for what purpose, and on what terms. Every automated client that has ever arrived is listed — including the ones nobody recognises. | چه کسی می‌تواند این سایت را بخواند، برای چه هدفی و با چه شرایطی. هر کلاینت خودکاری که تاکنون آمده فهرست شده است — از جمله آن‌هایی که هیچ کس نمی‌شناسد. |
| The first rule that matches wins and evaluation stops. There is no scoring and no "strictest wins" — you must be able to read this table and predict what happens to a given crawler. | نخستین قاعده‌ای که منطبق شود اعمال می‌شود و ارزیابی متوقف می‌شود. هیچ امتیازدهی و هیچ «سخت‌گیرانه‌ترین برنده است» در کار نیست — باید بتوانید این جدول را بخوانید و پیش‌بینی کنید با یک خزندهٔ مشخص چه می‌شود. |
| We do not permit corpus collection. | اجازهٔ گردآوری پیکره نمی‌دهیم. |
| Training use requires a licence. | استفاده برای آموزش مدل به مجوز نیاز دارد. |
| Commercial licence required — see terms. | مجوز تجاری لازم است — شرایط را ببینید. |
| No reason needed | دلیلی لازم نیست |
| Read the first two rows together: | دو ردیف نخست را با هم بخوانید: |
| block training everywhere, but answer a customer's live question freely. | آموزش مدل را همه‌جا مسدود کنید، اما به پرسش زندهٔ مشتری آزادانه پاسخ دهید. |
| That is the whole point of separating purpose from actor. A human visitor is never subject to any of these rules — there is no configuration here that can return 403 to a customer's browser. | هدف از جدا کردن هدف از کنشگر همین است. بازدیدکنندهٔ انسانی هرگز مشمول هیچ‌یک از این قاعده‌ها نیست — هیچ پیکربندی‌ای در اینجا نمی‌تواند به مرورگر مشتری 403 برگرداند. |
| returns HTTP 402 with a link to your terms. It records an intention; nothing in this product meters, invoices or collects anything, and there is deliberately no price field, because a number here would look like a working price. | HTTP 402 را همراه پیوندی به شرایط شما برمی‌گرداند. این یک قصد را ثبت می‌کند؛ هیچ چیز در این محصول اندازه‌گیری، صورتحساب یا دریافت نمی‌کند، و عمداً هیچ فیلد قیمتی نیست، چون عددی در اینجا شبیه قیمتی کارا به نظر می‌رسید. |
| 11 distinct clients in the last 30 days. There is no filter that hides unrecognised ones — the interesting agent is always the one nobody had heard of yet. | ۱۱ کلاینت متمایز در ۳۰ روز گذشته. هیچ فیلتری کلاینت‌های ناشناخته را پنهان نمی‌کند — عامل جالب همیشه همانی است که هنوز کسی نامش را نشنیده بود. |
| Automated clients observed, with their current access decision | کلاینت‌های خودکار مشاهده‌شده، با تصمیم دسترسی کنونی‌شان |
| Unrecognised client | کلاینت ناشناخته |
| A User-Agent header is a claim a request makes about itself. | سرآیند User-Agent ادعایی است که درخواست دربارهٔ خودش می‌کند. |
| means the header matched a published signature; | یعنی سرآیند با امضایی منتشرشده منطبق شد؛ |
| means a weaker pattern matched; | یعنی الگویی ضعیف‌تر منطبق شد؛ |
| would require reverse-DNS or published-IP confirmation and is not built, so nothing in this product can display it. Blocking by header therefore stops honest agents and does not stop dishonest ones — that is a real limit of this control and is stated here rather than in a footnote. | به تأیید reverse-DNS یا IP منتشرشده نیاز دارد و ساخته نشده است، پس هیچ چیز در این محصول نمی‌تواند آن را نشان دهد. بنابراین مسدود کردن بر پایهٔ سرآیند عامل‌های درستکار را متوقف می‌کند و نادرستکاران را نه — این محدودیتی واقعی در این کنترل است و به‌جای پانویس، همین‌جا گفته شده است. |

## Products (Step 11)

Terms for the Products screen. Product names, SKUs, categories and origins are shown as sent; enum values without a label are shown as sent.

| English | Persian |
|---|---|
| Products (AI Core) | محصولات (AI Core) |
| {from}–{to} of {total\|product\|products}. | {from}–{to} از {total} محصول. |
| No products yet. | هنوز هیچ محصولی نیست. |
| Not linked | پیوند نشده |
| Linked | پیوندشده |
| Offers | پیشنهادهای فروش |
| Not tracked | پیگیری نمی‌شود |
| Could not load the offers ({error}). | بارگذاری پیشنهادهای فروش ممکن نشد ({error}). |
| Could not load products ({error}). | بارگذاری محصولات ممکن نشد ({error}). |
| No offers yet. A product can be fully described with no offer. | هنوز هیچ پیشنهاد فروشی نیست. یک محصول می‌تواند بدون هیچ پیشنهاد فروشی کامل توصیف شود. |
| Offers for this product | پیشنهادهای فروش این محصول |
| Products, one row per SKU family | محصولات، یک ردیف برای هر خانوادهٔ کد کالا |
| Price | قیمت |
| Availability | موجودبودن |
| Stock | موجودی انبار |
| Condition | وضعیت کالا |
| Origin | خاستگاه |
| SKU | کد کالا |
| Brand | برند |
| Entered here | واردشده در اینجا |
| WooCommerce sync | همگام‌سازی WooCommerce |
| In stock | موجود |
| Out of stock | ناموجود |
| Pre-order | پیش‌سفارش |
| Backorder | سفارش معوق |
| Discontinued | توقف‌شده |
| New | جدید |
| Used | کارکرده |
| Refurbished | بازسازی‌شده |
| Product identity and commercial Offer are kept separate on purpose (DEC-0006): a Product is what it | هویت محصول و پیشنهاد فروش تجاری عمداً جدا نگه داشته شده‌اند (DEC-0006): محصول آن چیزی است که |
| is | هست |
| — brand, origin, ingredients, certifications; an Offer is where it can be | — برند، خاستگاه، ترکیبات، گواهی‌ها؛ پیشنهاد فروش جایی است که می‌توان آن را |
| bought | خرید |
| — price, stock, availability. A Product can exist, fully described, with zero offers. | — قیمت، موجودی، موجودبودن. یک محصول می‌تواند کاملاً توصیف‌شده و بدون هیچ پیشنهاد فروشی وجود داشته باشد. |
| Field set matches the canonical schema (MASTER_SPEC.md §26 products / §27 offers) — sku, brand, category, origin, ingredients, certifications for the product; price, currency, availability, stock, condition for each offer. Nothing here is a WooCommerce mirror; WooCommerce is one possible source that normalizes into this same shape. | مجموعهٔ فیلدها با طرح‌وارهٔ مرجع منطبق است (MASTER_SPEC.md §26 محصولات / §27 پیشنهادهای فروش) — کد کالا، برند، دسته، خاستگاه، ترکیبات و گواهی‌ها برای محصول؛ قیمت، واحد پول، موجودبودن، موجودی و وضعیت کالا برای هر پیشنهاد فروش. هیچ چیز اینجا آینهٔ WooCommerce نیست؛ WooCommerce یکی از منبع‌های ممکن است که به همین شکل یکسان می‌شود. |

## AI Center — Advanced (Step 9E-2)

Delete and revoke actions, the job panel and live progress, knowledge transfer packages, discovery rows, the Walrus line, routing step names, the Agent Network list, the session inspector and the agent orchestration console. Server messages, identifiers and unknown values are shown as sent.

| English | Persian |
|---|---|
| Delete | حذف |
| Revoke credential | باطل کردن اعتبارنامه |
| Delete provider {name}? This cannot be undone. | ارائه‌دهندهٔ {name} حذف شود؟ این کار برگشت‌پذیر نیست. |
| Deleted provider {name}. | ارائه‌دهندهٔ {name} حذف شد. |
| Revoke the credential of {label}? The account stays; calls through it stop until a new credential is set. | اعتبارنامهٔ {label} باطل شود؟ حساب باقی می‌ماند؛ فراخوانی‌ها از طریق آن تا تنظیم اعتبارنامهٔ تازه متوقف می‌شوند. |
| Credential revoked for {label}. | اعتبارنامهٔ {label} باطل شد. |
| Delete account {label}? Its credential will also be removed. | حساب {label} حذف شود؟ اعتبارنامهٔ آن هم پاک می‌شود. |
| Deleted account {label}. | حساب {label} حذف شد. |
| Delete model {name}? This cannot be undone. | مدل {name} حذف شود؟ این کار برگشت‌پذیر نیست. |
| Deleted model {name}. | مدل {name} حذف شد. |
| Your session expired. Please reconnect. | نشست شما منقضی شده است. لطفاً دوباره وصل شوید. |
| Your role is not allowed to delete (HTTP 403). | نقش شما اجازهٔ حذف ندارد (HTTP 403). |
| Move step {n} up | انتقال گام {n} به بالا |
| Move step {n} down | انتقال گام {n} به پایین |
| Remove step {n} | حذف گام {n} |
| Paused | متوقف‌شده |
| Pause requested | توقف درخواست شده |
| Blocked | مسدود |
| Cancel requested | لغو درخواست شده |
| Pause | توقف |
| Resume | ادامه |
| Stop reason | دلیل توقف |
| Total | مجموع |
| Loading job… | در حال بارگذاری کار… |
| Export this job’s memory | خروجی گرفتن از حافظهٔ این کار |
| Latest handoff package | آخرین بستهٔ تحویل |
| No handoff yet — the job has not switched resources. | هنوز تحویلی نیست — کار منبعش را عوض نکرده است. |
| Live progress unavailable. | پیشرفت زنده در دسترس نیست. |
| Connecting to live progress… | در حال اتصال به پیشرفت زنده… |
| Live: {state} — {completed} done, {pending} pending, {failed} failed of {total}. | زنده: {state} — از {total} مورد، {completed} انجام‌شده، {pending} در انتظار، {failed} ناموفق. |
| Live: {state} — {completed} done, {pending} pending, {failed} failed of {total}. Stream closed ({end}). | زنده: {state} — از {total} مورد، {completed} انجام‌شده، {pending} در انتظار، {failed} ناموفق. جریان بسته شد ({end}). |
| Stream closed ({end}). | جریان بسته شد ({end}). |
| Live progress unavailable: {error} | پیشرفت زنده در دسترس نیست: {error} |
| Memory exported. | از حافظه خروجی گرفته شد. |
| Export failed: {error} | خروجی گرفتن ناموفق بود: {error} |
| Nothing here yet. Import the initial discovery list. | هنوز چیزی اینجا نیست. فهرست اولیهٔ کشف را وارد کنید. |
| New claim | ادعای تازه |
| Duplicate | تکراری |
| Variant | گونهٔ دیگر |
| No new evidence | بدون شاهد تازه |
| {n} of {total} | {n} از {total} |
| Package {id} | بستهٔ {id} |
| Not used: {reason} | استفاده نشد: {reason} |
| Rejected — {reason} | رد شد — {reason} |
| Accepted | پذیرفته شد |
| Accepted — {evidence} new evidence, {links} new links | پذیرفته شد — {evidence} شاهد تازه، {links} پیوند تازه |
| Evidence {index} rejected: {code} | شاهد {index} رد شد: {code} |
| The package carried no claims. | این بسته هیچ ادعایی نداشت. |
| Open questions | پرسش‌های باز |
| Gaps | شکاف‌ها |
| Unknown entities (candidates) | موجودیت‌های ناشناخته (نامزدها) |
| Conflicts recorded | تعارض‌های ثبت‌شده |
| Could not load the package: {error} | بارگذاری بسته ممکن نشد: {error} |
| User | کاربر |
| AI execution | اجرای هوش مصنوعی |
| No package with this status. | هیچ بسته‌ای با این وضعیت نیست. |
| No packages yet. They arrive from AI jobs run with the ktp_v1 output contract. | هنوز هیچ بسته‌ای نیست. بسته‌ها از کارهای هوش مصنوعی می‌آیند که با قرارداد خروجی ktp_v1 اجرا شوند. |
| Verdicts | رأی‌ها |
| Walrus: {status} — {detail} | Walrus (حافظهٔ معنایی): {status} — {detail} |
| No agents registered. Create agents via the API (POST /api/v1/agent-network/agents). | هیچ عاملی ثبت نشده است. عامل‌ها را از طریق API بسازید (POST /api/v1/agent-network/agents). |
| Protocol | پروتکل |
| Capabilities | توانایی‌ها |
| Enter a session ID. | شناسهٔ یک نشست را وارد کنید. |
| Connect to AI Core first. | ابتدا به AI Core وصل شوید. |
| Goal: {goal} · status {status} | هدف: {goal} · وضعیت {status} |
| Tasks ({n}) | کارها ({n}) |
| Handoffs ({n}) | تحویل‌ها ({n}) |
| Messages ({n}) | پیام‌ها ({n}) |
| None. | هیچ. |
| Task | کار |
| To | به |
| Reason | دلیل |
| Delivered | تحویل‌شده |
| Acknowledged | تأییدشده |
| Connect to AI Core first (Connection card above). | ابتدا به AI Core وصل شوید (کارت اتصال در بالا). |
| Nothing registered yet | هنوز چیزی ثبت نشده |
| Could not load lists: {error} | بارگذاری فهرست‌ها ممکن نشد: {error} |
| Agent registered: {name} ({id}) | عامل ثبت شد: {name} ({id}) |
| Memory access granted ({level}). | دسترسی به حافظه داده شد ({level}). |
| Session started: {id} | نشست آغاز شد: {id} |
| Task added: {id} ({status}) | کار افزوده شد: {id} ({status}) |
| Task {status} ({reason}) — {n\|AI execution\|AI executions}: {ids} | کار {status} ({reason}) — {n} اجرای هوش مصنوعی: {ids} |
| Task {status} — {n\|AI execution\|AI executions}: {ids} | کار {status} — {n} اجرای هوش مصنوعی: {ids} |
| Handoff created: {id} — shared-memory checkpoint {checkpoint} | تحویل ساخته شد: {id} — نقطهٔ بازبینی حافظهٔ مشترک {checkpoint} |
| Handoff {status}. Run the next task with this agent and the handoff ID (step 5). | تحویل {status}. کار بعدی را با این عامل و شناسهٔ تحویل اجرا کنید (گام ۵). |
| Fill in: {fields} | پر کنید: {fields} |

## Device Intelligence (ADR-138)

Terms for the Device Intelligence admin screen. Categories describe installations, never people. macOS, reason codes, signal names, references and e-mail addresses stay as sent.

| English | Persian |
|---|---|
| Device Intelligence | هوش دستگاه |
| Installations of the official AIOL apps that proved, by signature, that they are the same installation as before. Evidence categories describe installations, never people, and nothing on this screen blocks anyone. Network and Windows installation identifiers appear only as short pseudonymous references. Read live from AI Core — no sample data. | نصب‌های برنامه‌های رسمی AIOL که با امضا ثابت کرده‌اند همان نصب قبلی هستند. دسته‌های شواهد دربارهٔ نصب‌ها هستند، نه افراد، و هیچ چیز در این صفحه کسی را مسدود نمی‌کند. شناسه‌های شبکه و نصب ویندوز فقط به‌صورت مرجع کوتاه مستعار نمایش داده می‌شوند. زنده از AI Core خوانده می‌شود — بدون دادهٔ نمونه. |
| Revoked | باطل‌شده |
| Installation | نصب |
| App version | نسخهٔ برنامه |
| Last seen | آخرین مشاهده |
| Evidence categories | دسته‌های شواهد |
| Web browser | مرورگر وب |
| Windows | ویندوز |
| Android | اندروید |
| iPhone / iPad | آیفون / آیپد |
| Same registered installation | همان نصب ثبت‌شده |
| Likely shared client environment | محیط مشترک احتمالی برنامه |
| Conflicting evidence | شواهد متعارض |
| Shared network only | فقط شبکهٔ مشترک |
| Insufficient evidence | شواهد ناکافی |
| Device credential revoked | اعتبارنامهٔ دستگاه باطل‌شده |
| {n|installation|installations} | {n} نصب |
| No installations yet. An installation appears after an official AIOL app signs in with installation verification on. | هنوز نصبی ثبت نشده است. یک نصب پس از ورود یک برنامهٔ رسمی AIOL با تأیید نصب روشن نمایش داده می‌شود. |
| Could not load installations ({error}). | بارگذاری نصب‌ها ناموفق بود ({error}). |
| Only owners and administrators can see installations. | فقط مالکان و مدیران می‌توانند نصب‌ها را ببینند. |
| Details | جزئیات |
| Installation detail | جزئیات نصب |
| Linked accounts | حساب‌های متصل |
| Recent observations | مشاهدات اخیر |
| Reason codes | کدهای دلیل |
| Algorithm version | نسخهٔ الگوریتم |
| Key storage (as reported by the app) | محل نگهداری کلید (به گزارش برنامه) |
| Network reference | مرجع شبکه |
| Windows installation reference | مرجع نصب ویندوز |
| Signals | نشانه‌ها |
| Event | رویداد |
| Registered | ثبت شد |
| Account linked | حساب متصل شد |
| Signature verified | امضا تأیید شد |
| Verification failed | تأیید ناموفق بود |
| Account unlinked | حساب جدا شد |
| Revoke installation | باطل کردن نصب |
| Revoke this installation? Its key will never be accepted again; the app creates a new one at its next sign-in. | این نصب باطل شود؟ کلید آن دیگر هرگز پذیرفته نمی‌شود و برنامه در ورود بعدی کلید تازه‌ای می‌سازد. |
| Installation revoked. | نصب باطل شد. |
| Could not revoke ({error}). | باطل کردن ناموفق بود ({error}). |

## Auth screens (Step 12A)

Login, sign-up and the login-code step, with the app-shell labels the code page shares. The product name AI Operating Layer and email addresses stay as written; live messages come from the page itself, chosen by HTTP status.

| English | Persian |
|---|---|
| Welcome back | خوش آمدید |
| Log in to your AI Operating Layer workspace. | به فضای کاری AI Operating Layer خود وارد شوید. |
| Work email | ایمیل کاری |
| Send login code | ارسال کد ورود |
| We'll email you a 6-digit code — no password to remember or leak. | یک کد ۶ رقمی برایتان ایمیل می‌کنیم — گذرواژه‌ای نیست که به خاطر بسپارید یا لو برود. |
| New to AI Operating Layer? | تازه با AI Operating Layer آشنا شده‌اید؟ |
| Create an account | ساختن حساب |
| Create your account | حساب خود را بسازید |
| Start turning product knowledge into AI-ready evidence. | دانش محصول را به شواهدی آماده برای هوش مصنوعی تبدیل کنید. |
| Full name | نام کامل |
| Company or workspace name | نام شرکت یا فضای کاری |
| Leave this empty | این را خالی بگذارید |
| I agree to the | موافقم با |
| Terms of Service | شرایط خدمات |
| and | و |
| Privacy Policy | سیاست حریم خصوصی |
| Create account | ساختن حساب |
| Already have an account? | حساب دارید؟ |
| Log in | ورود |
| Use a different email | استفاده از ایمیل دیگر |
| Check your email | ایمیل خود را بررسی کنید |
| Enter the 6-digit code we sent to . | کد ۶ رقمی فرستاده‌شده به این نشانی را وارد کنید: . |
| Enter the 6-digit code we sent to | کد ۶ رقمی فرستاده‌شده به این نشانی را وارد کنید: |
| Verify and continue | تأیید و ادامه |
| Resend code | ارسال دوبارهٔ کد |
| The code expires in 5 minutes. Three wrong attempts lock this email for 1 hour; three more lock it for 24 hours. Never share this code — we will never ask for it. | کد پس از ۵ دقیقه منقضی می‌شود. سه تلاش نادرست این ایمیل را ۱ ساعت قفل می‌کند؛ سه تلاش نادرست دیگر آن را ۲۴ ساعت قفل می‌کند. این کد را با هیچ کس در میان نگذارید — ما هرگز آن را از شما نمی‌خواهیم. |
| © 2026 AI Operating Layer | © ۲۰۲۶ AI Operating Layer |
| Privacy | حریم خصوصی |
| Security | امنیت |
| 6-digit verification code | کد تأیید ۶ رقمی |
| Digit 1 of 6 | رقم ۱ از ۶ |
| Digit 2 of 6 | رقم ۲ از ۶ |
| Digit 3 of 6 | رقم ۳ از ۶ |
| Digit 4 of 6 | رقم ۴ از ۶ |
| Digit 5 of 6 | رقم ۵ از ۶ |
| Digit 6 of 6 | رقم ۶ از ۶ |
| Inbox, 3 unread messages | صندوق پیام، ۳ پیام خوانده‌نشده |
| Account menu | منوی حساب |
| A separate, privileged surface — shown here only because this fixture has no real authorization boundary to hide it behind | سطحی جداگانه و دارای امتیاز ویژه — اینجا فقط به این دلیل نشان داده می‌شود که این نمونه هیچ مرز مجوز واقعی ندارد که پشت آن پنهان شود |
| Hide sidebar | پنهان کردن نوار کناری |
| Resend code ({time}) | ارسال دوبارهٔ کد ({time}) |
| Too many wrong codes. Sign-in is locked for 24 hours; contact support. | کدهای نادرست زیادی وارد شد. ورود به مدت ۲۴ ساعت قفل است؛ با پشتیبانی تماس بگیرید. |
| Too many wrong codes. Sign-in is locked for 1 hour. | کدهای نادرست زیادی وارد شد. ورود به مدت ۱ ساعت قفل است. |
| A code was sent recently. Try again later. | به تازگی کدی فرستاده شد. بعداً دوباره تلاش کنید. |
| Too many requests. Try again in a moment. | درخواست‌ها بیش از حد است. لحظه‌ای دیگر دوباره تلاش کنید. |
| Email delivery is not available; no code was sent. | ارسال ایمیل در دسترس نیست؛ هیچ کدی فرستاده نشد. |
| That code is wrong or has expired. Check the latest email and try again. | این کد نادرست است یا منقضی شده است. آخرین ایمیل را بررسی کنید و دوباره تلاش کنید. |
| AI Core did not answer as expected (HTTP {status}). | AI Core پاسخ مورد انتظار را نداد (HTTP {status}). |
| A code was sent recently. Enter it, or wait to request a new one. | به تازگی کدی فرستاده شد. آن را وارد کنید، یا برای درخواست کد تازه صبر کنید. |
| Could not reach AI Core ({error}). | دسترسی به AI Core ممکن نشد ({error}). |
| A new code was sent. | کد تازه‌ای فرستاده شد. |
| Enter all 6 digits. | هر ۶ رقم را وارد کنید. |
| Checking your code… | در حال بررسی کد شما… |
| Verified — signing you in… | تأیید شد — در حال ورود… |
| Incorrect code — {n\|attempt\|attempts} left before a temporary lock. | کد نادرست است — {n} تلاش تا قفل موقت باقی مانده است. |
| Enter your full name. | نام کامل خود را وارد کنید. |
| Enter your company or workspace name. | نام شرکت یا فضای کاری خود را وارد کنید. |
| Enter a valid work email. | یک ایمیل کاری معتبر وارد کنید. |
| The website must start with https:// | نشانی وب‌سایت باید با https:// آغاز شود |
| Please accept the Terms of Service and Privacy Policy. | لطفاً شرایط خدمات و سیاست حریم خصوصی را بپذیرید. |
| Sending your code… | در حال فرستادن کد شما… |
| Enter all six digits. | هر شش رقم را وارد کنید. |
| Account created. Opening your workspace… | حساب ساخته شد. در حال باز کردن فضای کاری شما… |
| Log in · AI Operating Layer | ورود · AI Operating Layer |
| Create your account · AI Operating Layer | ساختن حساب · AI Operating Layer |
| Enter your code · AI Operating Layer | وارد کردن کد · AI Operating Layer |
| A User-Agent header is a claim a request makes about itself, not a verified identity — anyone can send | سرآیند User-Agent ادعایی است که درخواست دربارهٔ خودش می‌کند، نه هویتی تأییدشده — هر کسی می‌تواند این را بفرستد: |
| . Every row above is | . هر ردیف بالا |

## Website (Step 12B)

Blog, page sections and newsletter subscribers. Post titles, section labels, addresses and sources are shown as sent; a server message is shown as sent.

| English | Persian |
|---|---|
| Saved as version {n}. | به‌عنوان نسخهٔ {n} ذخیره شد. |
| Published on {d}. | در {d} منتشر شد. |
| Moved back to draft. | به پیش‌نویس برگردانده شد. |
| Showing {label}. | {label} نمایش داده می‌شود. |
| Hiding {label}. | {label} پنهان می‌شود. |
| Heading saved. | عنوان ذخیره شد. |
| Order saved. | ترتیب ذخیره شد. |
| Erased. | پاک شد. |
| Exported. | خروجی گرفته شد. |
| Persian | فارسی |
| English | انگلیسی |
| No posts yet. Write the first one with “New post”. | هنوز هیچ نوشته‌ای نیست. نخستین را با «نوشتهٔ تازه» بنویسید. |
| No one has subscribed yet. | هنوز کسی مشترک نشده است. |
| Title | عنوان |
| Note | یادداشت |
| Section | بخش |
| Shown | نمایش |
| Heading override | عنوان جایگزین |
| Order | ترتیب |
| Email | ایمیل |
| Joined from | پیوستن از |
| Consent | رضایت |
| Page sections and their order | بخش‌های صفحه و ترتیب آن‌ها |
| Subscribed | مشترک |
| Unsubscribed | لغو اشتراک‌شده |
| Edit | ویرایش |
| Up | بالا |
| Down | پایین |
| Unsubscribe | لغو اشتراک |
| Erase | پاک کردن |
| Edit: {title} | ویرایش: {title} |
| New post | نوشتهٔ تازه |
| Update history | تاریخچهٔ به‌روزرسانی |
| Show {label} | نمایش {label} |
| Heading for {label} | عنوان برای {label} |
| The hero cannot be hidden | بخش اصلی بالای صفحه را نمی‌توان پنهان کرد |
| Default heading | عنوان پیش‌فرض |
| {n\|subscriber\|subscribers} | {n} مشترک |
| Erase {email} completely? This cannot be undone. | {email} به‌طور کامل پاک شود؟ این کار برگشت‌پذیر نیست. |
| Write and publish the articles on your public website, in English and Persian. A post needs an author and a body before it can be published; every edit is kept as a revision with a note, and that history is shown on the published article. | نوشته‌های وب‌سایت عمومی خود را به انگلیسی و فارسی بنویسید و منتشر کنید. هر نوشته پیش از انتشار به نویسنده و متن نیاز دارد؛ هر ویرایش با یک یادداشت به‌عنوان بازنگری نگه داشته می‌شود و این تاریخچه روی نوشتهٔ منتشرشده نشان داده می‌شود. |
| Address (slug) | نشانی (نامک) |
| Summary | خلاصه |
| Body (one paragraph per blank line) | متن (هر بند با یک خط خالی جدا شود) |
| Translation of (optional) | ترجمهٔ (اختیاری) |
| References (one per line: title \| publisher \| address) | منابع (هر خط یکی: عنوان \| ناشر \| نشانی) |
| What changed (kept in the update history) | چه چیزی تغییر کرد (در تاریخچهٔ به‌روزرسانی نگه داشته می‌شود) |
| Publish | انتشار |
| Unpublish | لغو انتشار |
| Close | بستن |
| why-indirect-stays-indirect | مثال: why-indirect-stays-indirect |
| Show, hide, reorder and retitle the sections of the public home page, separately for each language. The hero carries the page's only main heading and cannot be hidden. The site reads these settings when it is connected to AI Core. | بخش‌های صفحهٔ اصلی عمومی را برای هر زبان جداگانه نمایش دهید، پنهان کنید، جابه‌جا کنید یا عنوانشان را تغییر دهید. بخش اصلی بالای صفحه تنها عنوان اصلی صفحه را دارد و نمی‌توان آن را پنهان کرد. سایت این تنظیمات را هنگام اتصال به AI Core می‌خواند. |
| Home | صفحهٔ اصلی |
| Everyone who joined the newsletter from the public website. An address is stored only with explicit consent, which is recorded with its date and wording. Export as CSV, mark someone unsubscribed, or erase an address completely on request. | همهٔ کسانی که از وب‌سایت عمومی به خبرنامه پیوسته‌اند. هر نشانی فقط با رضایت صریح نگه داشته می‌شود که با تاریخ و متن آن ثبت می‌شود. خروجی CSV بگیرید، اشتراک کسی را لغو کنید، یا در صورت درخواست، نشانی را به‌طور کامل پاک کنید. |
| Export CSV | خروجی CSV |

## Settings (Step 13B)

The Settings messages added with the account, organization, reset and log-out wiring.

| English | Persian |
|---|---|
| Reset on this device. The preferences saved to your account are unchanged. | روی این دستگاه بازنشانی شد. ترجیحات ذخیره‌شده در حساب شما تغییری نکرد. |
| Organization | سازمان |
| Could not read your account from AI Core. | خواندن حساب شما از AI Core ممکن نشد. |
| Only an owner or admin can rename the organization. | فقط مالک یا مدیر می‌تواند نام سازمان را تغییر دهد. |
| Organization name | نام سازمان |
| Enter a name. | یک نام وارد کنید. |
| Saved. | ذخیره شد. |
| Not saved ({error}). | ذخیره نشد ({error}). |
| Role | نقش |
| Slug | نامک |
| Owner | مالک |
| Researcher | پژوهشگر |
| Editor | ویراستار |
| Analyst | تحلیلگر |
| Viewer | بیننده |
| Suspended | معلق |
| Light | روشن |
| Dark | تیره |
| Same as the device | مانند دستگاه |

## Settings (Step 13C)

The Settings screen: research engine card (static text), appearance, account, preferences, shared memory, background processing and the danger zone. Sentences split by an icon also have fragment keys; placeholders become Persian examples.

| English | Persian |
|---|---|
| Preferences for this account. Nothing here touches Knowledge Objects, sources, wallet or billing history — resetting a preference is never a data-deletion action (see "Reset all settings" below). | ترجیحات این حساب. هیچ چیز اینجا به اشیای دانش، منابع، کیف پول یا تاریخچهٔ صورتحساب دست نمی‌زند — بازنشانی یک ترجیح هرگز داده‌ای را حذف نمی‌کند («بازنشانی همهٔ تنظیمات» را در پایین ببینید). |
| Research engine (AI Core) | موتور پژوهش (AI Core) |
| Searches Crossref, PubMed and Europe PMC together. Discovery only creates | در Crossref، PubMed و Europe PMC با هم جست‌وجو می‌کند. کشف فقط |
| sources | منبع می‌سازد |
| ; nothing becomes evidence until a person reviews it. A source that was found is not a source that was read. | ؛ هیچ چیز تا وقتی کسی بازبینی‌اش نکند شاهد نمی‌شود. منبعی که پیدا شده، منبعی نیست که خوانده شده باشد. |
| Search with keywords | جست‌وجو با کلیدواژه‌ها |
| Keywords | کلیدواژه‌ها |
| One keyword | یک کلیدواژه |
| Several keywords (OR) | چند کلیدواژه (OR) |
| Exact phrase | عبارت دقیق |
| AND / OR query | پرسش AND / OR |
| Expanded by the research agent | گسترش‌یافته توسط عامل پژوهش |
| Query (AND, OR, NOT, "phrases", parentheses) | پرسش (AND, OR, NOT، «عبارت‌ها»، پرانتز) |
| Search all providers | جست‌وجو در همهٔ ارائه‌دهنده‌ها |
| Research question | پرسش پژوهشی |
| Subject (plant / product) | موضوع (گیاه / محصول) |
| Compounds (comma-separated, optional) | ترکیب‌ها (جداشده با ویرگول، اختیاری) |
| Related species (comma-separated, optional) | گونه‌های مرتبط (جداشده با ویرگول، اختیاری) |
| Outcome | پیامد |
| Population | جمعیت |
| Investigate | بررسی |
| Each route is searched separately and never merged: the subject itself, each compound in humans, mechanism, subject and compound together, the compounds in combination, preparations containing the subject, and related species. Only a study of the subject itself can be direct evidence for it. | هر مسیر جداگانه جست‌وجو می‌شود و هرگز ادغام نمی‌شود: خود موضوع، هر ترکیب در انسان، سازوکار، موضوع و ترکیب با هم، ترکیب‌ها در کنار هم، فراورده‌های دارای موضوع، و گونه‌های مرتبط. تنها پژوهشی روی خود موضوع می‌تواند شاهد مستقیم برای آن باشد. |
| Research questions | پرسش‌های پژوهشی |
| Appearance | نمای ظاهری |
| Theme | پوسته |
| Light / Dark | روشن / تیره |
| — also toggled from in the top bar | — همچنین با دکمهٔ نوار بالا تغییر می‌کند |
| — also toggled from | — همچنین با دکمهٔ |
| in the top bar | در نوار بالا تغییر می‌کند |
| Font | قلم |
| System default | پیش‌فرض سیستم |
| — also toggled from in the top bar; persists across logout/login until changed again | — همچنین با دکمهٔ نوار بالا تغییر می‌کند؛ پس از خروج و ورود دوباره هم تا تغییر بعدی باقی می‌ماند |
| in the top bar; persists across logout/login until changed again | در نوار بالا تغییر می‌کند؛ پس از خروج و ورود دوباره هم تا تغییر بعدی باقی می‌ماند |
| Site | سایت |
| Sign-in method | روش ورود |
| Email code | کد ایمیلی |
| Preferences saved to your account | ترجیحات ذخیره‌شده در حساب شما |
| Language, theme and notifications are stored in AI Core for your user and restored on any device after you connect. | زبان، پوسته و اعلان‌ها در AI Core برای کاربر شما ذخیره می‌شوند و پس از اتصال روی هر دستگاهی بازیابی می‌شوند. |
| Not connected to AI Core — changes apply to this page only. | به AI Core وصل نیست — تغییرها فقط روی همین صفحه اعمال می‌شوند. |
| Email notifications | اعلان‌های ایمیلی |
| Processing failures | خطاهای پردازش |
| AI budget and quota warnings | هشدارهای بودجه و سهمیهٔ هوش مصنوعی |
| Security alerts | هشدارهای امنیتی |
| Weekly summary | خلاصهٔ هفتگی |
| PostgreSQL (ai_working_memory) is the canonical, always-on memory store. No action can replace it. | PostgreSQL (ai_working_memory) انبار مرجع و همیشه‌فعال حافظه است. هیچ کاری نمی‌تواند جای آن را بگیرد. |
| PostgreSQL — locked | PostgreSQL — قفل‌شده |
| Not connected | وصل نیست |
| Memory profiles | نمایه‌های حافظه |
| Not connected to AI Core | به AI Core وصل نیست |
| Add memory profile | افزودن نمایهٔ حافظه |
| Name * | نام * |
| Project | پروژه |
| Tenant | مستأجر |
| Native only | فقط بومی |
| Native + Walrus (optional mirror) | بومی + Walrus (آینهٔ اختیاری) |
| Retention (days) | مدت نگهداری (روز) |
| Create profile | ساختن نمایه |
| Background AI processing | پردازش هوش مصنوعی در پس‌زمینه |
| A connected account is | حساب متصل |
| not | به‌طور خودکار |
| automatically eligible for background processing — you must enable each task type explicitly. | برای پردازش پس‌زمینه واجد شرایط نیست — باید هر نوع کار را صریحاً فعال کنید. |
| Configure a task type | پیکربندی یک نوع کار |
| Task type * | نوع کار * |
| Choose… | انتخاب کنید… |
| Source extraction | استخراج منبع |
| Evidence analysis | تحلیل شواهد |
| Knowledge generation | تولید دانش |
| Knowledge refresh | تازه‌سازی دانش |
| Keyword analysis | تحلیل کلیدواژه |
| Content generation | تولید محتوا |
| Translation | ترجمه |
| Summarization | خلاصه‌سازی |
| Embedding | بردارسازی |
| AI visibility | دیده‌شدن در هوش مصنوعی |
| Demand analysis | تحلیل تقاضا |
| Agent planning | برنامه‌ریزی عامل |
| Agent review | بازبینی عامل |
| Agent synthesis | ترکیب عامل |
| Routing policy (optional — overrides the job's) | سیاست مسیریابی (اختیاری — جایگزین سیاست کار می‌شود) |
| Use the job's routing policy | استفاده از سیاست مسیریابی کار |
| Max cost per run (blank = no limit) | بیشینهٔ هزینهٔ هر اجرا (خالی = بدون سقف) |
| Accounts allowed to run this work | حساب‌های مجاز برای اجرای این کار |
| Only the accounts you tick can be used. A connected account that is not ticked is never selected. | فقط حساب‌هایی که علامت می‌زنید استفاده می‌شوند. حساب متصلی که علامت نخورده هرگز انتخاب نمی‌شود. |
| Loading accounts… | در حال بارگذاری حساب‌ها… |
| Enable immediately | فعال‌سازی فوری |
| Save policy | ذخیرهٔ سیاست |
| Danger zone | منطقهٔ خطر |
| Reset all settings | بازنشانی همهٔ تنظیمات |
| Restores theme, language, sidebar and table preferences to defaults. | پوسته، زبان، نوار کناری و ترجیحات جدول را به پیش‌فرض برمی‌گرداند. |
| Does not | هرگز |
| touch Knowledge Objects, sources, research, wallet or billing history. | به اشیای دانش، منابع، پژوهش، کیف پول یا تاریخچهٔ صورتحساب دست نمی‌زند. |
| Reset | بازنشانی |
| Taranjabin | مثلاً: ترنجبین |
| Mannitol, Fructose | مثلاً: مانیتول، فروکتوز |
| Alhagi persarum | مثلاً: Alhagi persarum |
| laxative | مثلاً: ملین |
| human | مثلاً: انسان |
| Forever | برای همیشه |
| Using defaults — nothing saved yet. Any change you make is saved to your account. | پیش‌فرض‌ها استفاده می‌شوند — هنوز چیزی ذخیره نشده است. هر تغییری بدهید در حساب شما ذخیره می‌شود. |
| Saved to your account (last change {d}). | در حساب شما ذخیره شده است (آخرین تغییر {d}). |
| Saved to your account. | در حساب شما ذخیره شده است. |
| Could not load preferences: {error} | بارگذاری ترجیحات ممکن نشد: {error} |
| Saved to your account ({d}). | در حساب شما ذخیره شد ({d}). |
| No profiles yet. Add one below. | هنوز نمایه‌ای نیست. یکی در پایین بیفزایید. |
| Could not create the profile ({error}). | ساختن نمایه ممکن نشد ({error}). |
| No task types configured. Connected accounts do nothing in the background until you configure a task type. | هیچ نوع کاری پیکربندی نشده است. حساب‌های متصل تا وقتی نوع کاری را پیکربندی نکنید در پس‌زمینه کاری انجام نمی‌دهند. |
| Allowed accounts | حساب‌های مجاز |
| Max cost | بیشینهٔ هزینه |
| Enabled | فعال |
| No limit | بدون سقف |
| No AI accounts registered yet (AI Center › Providers & accounts). | هنوز هیچ حساب هوش مصنوعی ثبت نشده است (مرکز هوش مصنوعی › ارائه‌دهنده‌ها و حساب‌ها). |
| (no credential) | (بدون اعتبارنامه) |
| Choose a task type. | یک نوع کار انتخاب کنید. |

## Admin (Step 14)

Admin users, the user detail template, the platform overview and organizations, and the shared admin dialogs. Names, emails, organization names and slugs are shown as sent; code-split sentences also have fragment keys.

| English | Persian |
|---|---|
| Users & organizations | کاربران و سازمان‌ها |
| Search, edit, delete, or open any user's wallet and activity history. Search and sort are real in this fixture; a live backend paginates server-side the same way Sources & Documents does. | جست‌وجو، ویرایش، حذف، یا باز کردن کیف پول و تاریخچهٔ فعالیت هر کاربر. جست‌وجو و مرتب‌سازی در این نمونه واقعی‌اند؛ یک پشتیبان زنده مانند «منابع و اسناد» در سمت سرور صفحه‌بندی می‌کند. |
| Search users | جست‌وجوی کاربران |
| All platform users | همهٔ کاربران پلتفرم |
| Last login | آخرین ورود |
| Past due | سررسید گذشته |
| Showing all 5 users. | همهٔ ۵ کاربر نمایش داده می‌شوند. |
| of | از |
| Search by name, email or organization… | جست‌وجو با نام، ایمیل یا سازمان… |
| Open account details | باز کردن جزئیات حساب |
| Users pages | صفحه‌های کاربران |
| First page | صفحهٔ اول |
| Previous page | صفحهٔ قبلی |
| Go to page | رفتن به صفحه |
| Next page | صفحهٔ بعدی |
| Last page | صفحهٔ آخر |
| One user: name, email, role and status — and, for a platform administrator, the organization. Open a user from the Users screen after connecting to AI Core. | یک کاربر: نام، ایمیل، نقش و وضعیت — و برای مدیر پلتفرم، سازمان. پس از اتصال به AI Core، کاربری را از صفحهٔ کاربران باز کنید. |
| Platform overview | نمای کلی پلتفرم |
| Illustrative fixture — a real admin overview reads / read models ( ), not this static data. | نمونهٔ نمایشی — نمای کلی واقعی مدیریت این مدل‌ها را می‌خواند: / (مدل‌های خواندنی؛ )، نه این دادهٔ ثابت را. |
| Illustrative fixture — a real admin overview reads | نمونهٔ نمایشی — نمای کلی واقعی مدیریت این مدل‌ها را می‌خواند: |
| read models ( | (مدل‌های خواندنی؛ |
| ), not this static data. | )، نه این دادهٔ ثابت را. |
| Organizations | سازمان‌ها |
| Active users (30d) | کاربران فعال (۳۰ روز) |
| Failed jobs (24h) | کارهای ناموفق (۲۴ ساعت) |
| This surface is authorization-separated from the merchant dashboard by design — an ordinary user account has no route into anything under , the same boundary the real backend must enforce server-side (never a frontend-only check). | این بخش عمداً از داشبورد فروشنده از نظر مجوز جداست — یک حساب کاربری عادی هیچ راهی به چیزی زیر این نشانی ندارد: ، همان مرزی که پشتیبان واقعی باید در سمت سرور اعمال کند (هرگز فقط یک بررسی در رابط کاربری). |
| This surface is authorization-separated from the merchant dashboard by design — an ordinary user account has no route into anything under | این بخش عمداً از داشبورد فروشنده از نظر مجوز جداست — یک حساب کاربری عادی هیچ راهی به چیزی زیر این نشانی ندارد: |
| , the same boundary the real backend must enforce server-side (never a frontend-only check). | ، همان مرزی که پشتیبان واقعی باید در سمت سرور اعمال کند (هرگز فقط یک بررسی در رابط کاربری). |
| Every organization on the platform, with how many users each has. Platform administrators only. | همهٔ سازمان‌های پلتفرم، با تعداد کاربران هر کدام. فقط برای مدیران پلتفرم. |
| Square images work best — at least 200×200px. JPG or PNG, up to 5MB. | تصویرهای مربعی بهترند — دست‌کم 200×200px. JPG یا PNG، تا 5MB. |
| Upload photo | بارگذاری عکس |
| Remove photo | حذف عکس |
| Done | انجام شد |
| All set! | همه‌چیز آماده است! |
| Information saved successfully | اطلاعات با موفقیت ذخیره شد |
| Save your changes? | تغییرات ذخیره شوند؟ |
| Please check the details below before saving. | لطفاً پیش از ذخیره، جزئیات زیر را بررسی کنید. |
| Keep editing | ادامهٔ ویرایش |
| Yes, save changes | بله، تغییرات ذخیره شوند |
| Delete this account? | این حساب حذف شود؟ |
| This account will be moved to the trash. You can restore it from there until it is permanently deleted. | این حساب به سطل زباله منتقل می‌شود. تا پیش از حذف دائمی می‌توانید آن را از آنجا بازگردانید. |
| Sure | مطمئنم |
| Profile photo preview | پیش‌نمایش عکس نمایه |
| Search by name, email or organization | جست‌وجو با نام، ایمیل یا سازمان |
| Every user on the platform: {n\|user\|users}. | همهٔ کاربران پلتفرم: {n} کاربر. |
| Users of your organization: {n\|user\|users}. | کاربران سازمان شما: {n} کاربر. |
| Joined | پیوستن |
| Every user on the platform | همهٔ کاربران پلتفرم |
| Users of your organization | کاربران سازمان شما |
| No users match. | هیچ کاربری منطبق نیست. |
| Could not load the users ({error}). | بارگذاری کاربران ممکن نشد ({error}). |
| Open a user from the Users screen. | کاربری را از صفحهٔ کاربران باز کنید. |
| This user was not found. | این کاربر پیدا نشد. |
| Could not load the user ({error}). | بارگذاری کاربر ممکن نشد ({error}). |
| {n} active | {n} فعال |
| With recorded activity in the last 30 days | با فعالیت ثبت‌شده در ۳۰ روز گذشته |
| Sync {sync} · AI {ai} | همگام‌سازی {sync} · هوش مصنوعی {ai} |
| Could not load the platform overview ({error}). | بارگذاری نمای کلی پلتفرم ممکن نشد ({error}). |
| Search by name or address | جست‌وجو با نام یا نشانی |
| Created | ساخته‌شده |
| Every organization on the platform | همهٔ سازمان‌های پلتفرم |
| {n\|organization\|organizations} on the platform. | {n} سازمان در پلتفرم. |
| No organizations match. | هیچ سازمانی منطبق نیست. |
| Could not load the organizations ({error}). | بارگذاری سازمان‌ها ممکن نشد ({error}). |
| Only platform administrators can see this screen. | فقط مدیران پلتفرم می‌توانند این صفحه را ببینند. |
| Invited | دعوت‌شده |
| Deactivated | غیرفعال‌شده |
| Users (AI Core) | کاربران (AI Core) |
| User (AI Core) | کاربر (AI Core) |
| Platform overview (AI Core) | نمای کلی پلتفرم (AI Core) |
| Organizations (AI Core) | سازمان‌ها (AI Core) |

## Research engine and platform-admin grants (polish, phase 1)

Runtime text of the Research engine card (V5-settings-research-runtime-fa) and the Grant / Revoke platform-admin controls (V5-admin-grant). Provider names (Crossref, PubMed, Europe PMC), DOI and PMID stay as written; the evidence-graph edge lines are identifiers and stay English.

| English | Persian |
|---|---|
| Full text read | متن کامل خوانده شد |
| Metadata only | فقط فراداده |
| Restricted | محدود |
| Unavailable | در دسترس نیست |
| Query: {query} — {unique\|unique source\|unique sources}, {new} new, {merged\|duplicate hit\|duplicate hits} merged. | پرسش: {query} — {unique} منبع یکتا، {new} تازه، {merged} یافتهٔ تکراری ادغام شد. |
| Results | نتیجه‌ها |
| What the system holds | آنچه سیستم در اختیار دارد |
| Review | بازبینی |
| Source: {title} | منبع: {title} |
| Publisher / journal | ناشر / مجله |
| Existence | وجود |
| What was actually accessed | آنچه واقعاً دسترسی شد |
| nothing | هیچ |
| Abstract | چکیده |
| Review status | وضعیت بازبینی |
| Open-access copies: | نسخه‌های دسترسی آزاد: |
| Fetch full text | دریافت متن کامل |
| Fetching the open-access copy… | در حال دریافت نسخهٔ دسترسی آزاد… |
| Full text acquired and converted ({bytes} bytes). The system has now read this source. | متن کامل دریافت و تبدیل شد ({bytes} بایت). سیستم اکنون این منبع را خوانده است. |
| Not acquired: {reason}. Nothing was claimed. | دریافت نشد: {reason}. هیچ ادعایی ثبت نشد. |
| Not acquired: {error} | دریافت نشد: {error} |
| none known | هیچ موردی شناخته نیست |
| Where to get it: | از کجا تهیه شود: |
| Library search | جست‌وجو در کتابخانه |
| Scholar search | جست‌وجوی علمی |
| Obtain the full text | تهیهٔ متن کامل |
| Get the article legally through one of the links above, then upload the file here. Nothing is claimed as full text until the upload actually parses into an article. | مقاله را به‌طور قانونی از یکی از پیوندهای بالا تهیه کنید، سپس پرونده را اینجا بارگذاری کنید. تا وقتی بارگذاری واقعاً به یک مقاله تجزیه نشود، چیزی به‌عنوان متن کامل ادعا نمی‌شود. |
| Article file (PDF, DOCX, HTML, TXT) | پروندهٔ مقاله (PDF, DOCX, HTML, TXT) |
| Upload full text | بارگذاری متن کامل |
| Choose the article file first. | ابتدا پروندهٔ مقاله را انتخاب کنید. |
| Uploaded. Processing the file — this can take a moment for a scanned PDF. | بارگذاری شد. پرونده در حال پردازش است — برای یک PDF اسکن‌شده ممکن است کمی طول بکشد. |
| Full text attached ({bytes} bytes parsed). This source is now readable by the system. | متن کامل پیوست شد ({bytes} بایت تجزیه شد). این منبع اکنون برای سیستم خواندنی است. |
| Still processing the file… ({n}) | هنوز در حال پردازش پرونده… ({n}) |
| Not attached: {reason}. The source was left unchanged. | پیوست نشد: {reason}. منبع بدون تغییر ماند. |
| Not attached: {error} | پیوست نشد: {error} |
| Upload failed: {error} | بارگذاری ناموفق بود: {error} |
| Or record what you found | یا آنچه یافتید را ثبت کنید |
| Title only | فقط عنوان |
| Landing page only | فقط صفحهٔ ورود |
| Registration required | نیاز به ثبت‌نام |
| Access blocked | دسترسی مسدود |
| Note (optional) | یادداشت (اختیاری) |
| Record | ثبت |
| Choose what you found. | آنچه یافتید را انتخاب کنید. |
| Recorded. | ثبت شد. |
| Research history ({n}) | تاریخچهٔ پژوهش ({n}) |
| Query | پرسش |
| Route | مسیر |
| Matched on | منطبق بر |
| Reviewed evidence: {done} · awaiting review: {waiting} | شواهد بازبینی‌شده: {done} · در انتظار بازبینی: {waiting} |
| No research questions yet. | هنوز هیچ پرسش پژوهشی نیست. |
| Subject | موضوع |
| Evidence map: {question} | نقشهٔ شواهد: {question} |
| Extract candidates from what the system holds | استخراج نامزدها از آنچه سیستم در اختیار دارد |
| {created\|candidate\|candidates} created for review; {unreadable\|source\|sources} had no readable text. | {created} نامزد برای بازبینی ساخته شد؛ {unreadable} منبع متن خواندنی نداشت. |
| Directly supported | پشتیبانی مستقیم |
| Indirectly supported | پشتیبانی غیرمستقیم |
| Directly supported ({n}) | پشتیبانی مستقیم ({n}) |
| Indirectly supported ({n}) | پشتیبانی غیرمستقیم ({n}) |
| Basis | مبنا |
| Evidence routes — kept separate | مسیرهای شواهد — جدا نگه داشته می‌شوند |
| Reviewed | بازبینی‌شده |
| Awaiting review | در انتظار بازبینی |
| Counts as | به حساب می‌آید |
| direct evidence for {subject} | شاهد مستقیم برای {subject} |
| indirect | غیرمستقیم |
| How many independent findings | چند یافتهٔ مستقل |
| {sources\|source rests\|sources rest} on {findings\|independent finding\|independent findings}. | {sources} منبع بر {findings} یافتهٔ مستقل تکیه دارد. |
| Independent finding | یافتهٔ مستقل |
| Grouped as | گروه‌بندی به‌عنوان |
| Should the search stop? | آیا جست‌وجو باید متوقف شود؟ |
| Saturation reached | به اشباع رسید |
| Not saturated | به اشباع نرسید |
| {reason} — {run} of {max} rounds run; still to run: {routes} | {reason} — {run} از {max} دور اجرا شد؛ هنوز باید اجرا شود: {routes} |
| {reason} — {run} of {max} rounds run | {reason} — {run} از {max} دور اجرا شد |
| Round | دور |
| Seen | دیده‌شده |
| Duplicates | تکراری‌ها |
| Reopen the search | بازگشایی دوبارهٔ جست‌وجو |
| Stop here (budget reached) | توقف در اینجا (بودجه تمام شد) |
| Show the evidence graph | نمایش گراف شواهد |
| Subject, compounds, studies and outcome | موضوع، ترکیب‌ها، پژوهش‌ها و پیامد |
| Studies that tested {subject} itself: {n} | پژوهش‌هایی که خود {subject} را آزموده‌اند: {n} |
| documented by a reviewed source | مستند به یک منبع بازبینی‌شده |
| Disagreements between findings | اختلاف میان یافته‌ها |
| No recorded disagreements. Use "Find disagreements" after linking evidence to a claim. | هیچ اختلافی ثبت نشده است. پس از پیوند دادن شواهد به یک ادعا، «یافتن اختلاف‌ها» را به کار ببرید. |
| Differs on | تفاوت در |
| nothing recorded | چیزی ثبت نشده |
| Supporting | پشتیبان |
| Contradicting | متعارض |
| Why? A resolution needs a written reason. | چرا؟ هر حل‌وفصلی به دلیلی نوشته‌شده نیاز دارد. |
| Find disagreements | یافتن اختلاف‌ها |
| No claim on this question has both supporting and contradicting evidence yet. | هنوز هیچ ادعایی در این پرسش هم شاهد پشتیبان و هم شاهد متعارض ندارد. |
| {n\|disagreement\|disagreements} recorded. | {n} اختلاف ثبت شد. |
| Awaiting human review ({n}) | در انتظار بازبینی انسانی ({n}) |
| What did the study actually test? | این پژوهش واقعاً چه چیزی را آزمود؟ |
| Approve | تأیید |
| Reject | رد |
| Reviewed: {status}, {directness} ({route}) | بازبینی شد: {status}، {directness} ({route}) |
| Found but not read by the system ({n}) | یافته‌شده ولی خوانده‌نشده توسط سیستم ({n}) |
| Holds | در اختیار |
| Get it | تهیه |
| Missing: {routes} | کمبود: {routes} |
| Missing: none | کمبود: هیچ |
| Suggested manual searches | جست‌وجوهای دستی پیشنهادی |
| Library | کتابخانه |
| Find more | یافتن بیشتر |
| Find more: {route} | یافتن بیشتر: {route} |
| Searching Crossref, PubMed and Europe PMC… | در حال جست‌وجو در Crossref، PubMed و Europe PMC… |
| Search results | نتایج جست‌وجو |
| A subject is required. | یک موضوع لازم است. |
| Running the searches… | در حال اجرای جست‌وجوها… |
| No open knowledge gaps. | هیچ شکاف دانشی باز نیست. |
| Gap | شکاف |
| Priority | اولویت |
| Searching for this gap… | در حال جست‌وجو برای این شکاف… |
| under review | در حال بازبینی |
| resolved | حل‌شده |
| unresolvable | حل‌نشدنی |
| Grant admin… | اعطای مدیریت… |
| Grant platform admin to which user? Enter an email or a user ID. | مدیریت پلتفرم به کدام کاربر داده شود؟ یک ایمیل یا شناسهٔ کاربر وارد کنید. |
| Platform admin granted to {who}. | مدیریت پلتفرم به {who} داده شد. |
| No user or platform admin matches that. | هیچ کاربر یا مدیر پلتفرمی با این منطبق نیست. |
| You cannot revoke your own platform-admin grant. | نمی‌توانید مدیریت پلتفرم خودتان را باطل کنید. |
| Enter a valid email or user ID. | یک ایمیل یا شناسهٔ کاربر معتبر وارد کنید. |
| Platform admin | مدیر پلتفرم |
| Revoke | باطل کردن |
| Revoke platform admin from {email}? | مدیریت پلتفرم از {email} باطل شود؟ |
| Platform admin revoked from {who}. | مدیریت پلتفرم از {who} باطل شد. |
| Make admin | مدیر کردن |

## Self profile, product search and settings reset (debt, priority 1)

The Settings name and email editor (V5-settings-self-profile), the Products search (V5-products-search) and the account-wide settings reset (V5-settings-reset-backend). SKU follows the glossary (کد کالا); AI Core stays as written.

| English | Persian |
|---|---|
| Edit profile | ویرایش نمایه |
| Edit account | ویرایش حساب |
| Close editor | بستن ویرایشگر |
| Edit my profile | ویرایش نمایهٔ من |
| Your sign-in codes are sent to this email address. | کدهای ورود شما به این نشانی ایمیل فرستاده می‌شوند. |
| Connect to AI Core to change your name or email address. | برای تغییر نام یا نشانی ایمیل خود به AI Core وصل شوید. |
| Enter your name. | نام خود را وارد کنید. |
| Enter a valid email address. | یک نشانی ایمیل معتبر وارد کنید. |
| Nothing to save. | چیزی برای ذخیره نیست. |
| That email address is already registered. | این نشانی ایمیل قبلاً ثبت شده است. |
| Search products | جست‌وجوی محصولات |
| Search by name or SKU… | جست‌وجو با نام یا کد کالا… |
| No products match {query}. | هیچ محصولی با {query} منطبق نیست. |
| Resetting… | در حال بازنشانی… |
| Reset. Your saved preferences are back to their defaults. | بازنشانی شد. ترجیحات ذخیره‌شدهٔ شما به پیش‌فرض برگشت. |
| Not reset ({error}). Nothing was changed. | بازنشانی نشد ({error}). چیزی تغییر نکرد. |
