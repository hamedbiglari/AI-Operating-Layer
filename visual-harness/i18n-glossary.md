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
