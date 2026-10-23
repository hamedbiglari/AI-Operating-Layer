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

## Conventions

1. Persian digits (۰–۹) and the Persian separators in all UI text. Identifiers,
   URLs, emails, code and form input keep Latin script.
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
