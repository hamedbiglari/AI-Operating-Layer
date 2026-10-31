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
| Cloud Core did not accept the access token (HTTP 401). It may have expired. | Cloud Core توکن دسترسی را نپذیرفت (HTTP 401). ممکن است منقضی شده باشد. |
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
4. Product and brand names stay as written: Cloud Core, AI Operating Layer,
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
| Not connected to Cloud Core. Connect on the Dashboard or AI Center screen. | به Cloud Core وصل نیست. در صفحهٔ داشبورد یا مرکز هوش مصنوعی وصل شوید. |
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
| Live operational view of every real AI-model invocation, read from Cloud Core. This screen has no fixture data: until it is connected it shows nothing, and every value shown comes from the API. | نمای عملیاتی زندهٔ هر فراخوانی واقعی مدل هوش مصنوعی، خوانده‌شده از Cloud Core. این صفحه هیچ دادهٔ نمونه‌ای ندارد: تا وصل نشود چیزی نشان نمی‌دهد، و هر مقداری که نشان داده می‌شود از API می‌آید. |
| Connection | اتصال |
| Not connected. Enter the Cloud Core URL and an access token. | وصل نیست. نشانی Cloud Core و یک توکن دسترسی وارد کنید. |
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
| Could not load AI executions: {error}. Check the URL, and that Cloud Core allows this origin (CORS_ALLOWED_ORIGINS). | بارگذاری اجراهای هوش مصنوعی ناموفق بود: {error}. نشانی را بررسی کنید و مطمئن شوید Cloud Core این مبدأ را مجاز می‌داند (CORS_ALLOWED_ORIGINS). |
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
| Everything the AI wrote while working: findings, open questions, checkpoints and handoffs — every version kept, with who wrote it and when. PostgreSQL is the canonical store. Reads are live from Cloud Core; exports are produced by the backend. | هر آنچه هوش مصنوعی هنگام کار نوشته است: یافته‌ها، پرسش‌های باز، نقطه‌های بازبینی و تحویل‌ها — همهٔ نسخه‌ها نگه داشته می‌شوند، با نویسنده و زمان نوشتن. PostgreSQL مخزن مرجع است. خواندن‌ها زنده از Cloud Core است؛ خروجی‌ها را بک‌اند تولید می‌کند. |
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
