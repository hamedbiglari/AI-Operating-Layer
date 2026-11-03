# CAPTCHA / PoW / sign-in email Persian strings: owner review (not wired)

Proposed FA strings for the CAPTCHA/PoW screens and the sign-in email - FOR OWNER REVIEW, NOT WIRED.

Machine-drafted from code points. Latin digits/placeholders stay as {time} {ip} {link}.

## 1. Security check

```text
بررسی امنیتی
```

Code points: `0628 0631 0631 0633 06CC 0020 0627 0645 0646 06CC 062A 06CC`

## 2. The security check did not load. Preparing another check…

```text
بررسی امنیتی بارگیری نشد. در حال آماده‌سازی بررسی دیگری…
```

Code points: `0628 0631 0631 0633 06CC 0020 0627 0645 0646 06CC 062A 06CC 0020 0628 0627 0631 06AF 06CC 0631 06CC 0020 0646 0634 062F 002E 0020 062F 0631 0020 062D 0627 0644 0020 0622 0645 0627 062F 0647 200C 0633 0627 0632 06CC 0020 0628 0631 0631 0633 06CC 0020 062F 06CC 06AF 0631 06CC 2026`

## 3. Preparing a security check… This can take up to a minute on a phone.

```text
در حال آماده‌سازی بررسی امنیتی… این کار روی تلفن ممکن است تا یک دقیقه طول بکشد.
```

Code points: `062F 0631 0020 062D 0627 0644 0020 0622 0645 0627 062F 0647 200C 0633 0627 0632 06CC 0020 0628 0631 0631 0633 06CC 0020 0627 0645 0646 06CC 062A 06CC 2026 0020 0627 06CC 0646 0020 06A9 0627 0631 0020 0631 0648 06CC 0020 062A 0644 0641 0646 0020 0645 0645 06A9 0646 0020 0627 0633 062A 0020 062A 0627 0020 06CC 06A9 0020 062F 0642 06CC 0642 0647 0020 0637 0648 0644 0020 0628 06A9 0634 062F 002E`

## 4. The security check failed. Try again.

```text
بررسی امنیتی ناموفق بود. دوباره تلاش کنید.
```

Code points: `0628 0631 0631 0633 06CC 0020 0627 0645 0646 06CC 062A 06CC 0020 0646 0627 0645 0648 0641 0642 0020 0628 0648 062F 002E 0020 062F 0648 0628 0627 0631 0647 0020 062A 0644 0627 0634 0020 06A9 0646 06CC 062F 002E`

## 5. [email subject] A sign-in code was requested for your account

```text
برای حساب شما کد ورود درخواست شد
```

Code points: `0628 0631 0627 06CC 0020 062D 0633 0627 0628 0020 0634 0645 0627 0020 06A9 062F 0020 0648 0631 0648 062F 0020 062F 0631 062E 0648 0627 0633 062A 0020 0634 062F`

## 6. [email] Someone asked for a sign-in code for this account.

```text
کسی برای این حساب کد ورود درخواست کرد.
```

Code points: `06A9 0633 06CC 0020 0628 0631 0627 06CC 0020 0627 06CC 0646 0020 062D 0633 0627 0628 0020 06A9 062F 0020 0648 0631 0648 062F 0020 062F 0631 062E 0648 0627 0633 062A 0020 06A9 0631 062F 002E`

## 7. [email] Time: {time} (UTC)

```text
زمان: {time} (UTC)
```

Code points: `0632 0645 0627 0646 003A 0020 007B 0074 0069 006D 0065 007D 0020 0028 0055 0054 0043 0029`

## 8. [email] From IP address: {ip}

```text
از نشانی IP: {ip}
```

Code points: `0627 0632 0020 0646 0634 0627 0646 06CC 0020 0049 0050 003A 0020 007B 0069 0070 007D`

## 9. [email] If this was you, you can ignore this message.

```text
اگر خودتان بودید، می‌توانید این پیام را نادیده بگیرید.
```

Code points: `0627 06AF 0631 0020 062E 0648 062F 062A 0627 0646 0020 0628 0648 062F 06CC 062F 060C 0020 0645 06CC 200C 062A 0648 0627 0646 06CC 062F 0020 0627 06CC 0646 0020 067E 06CC 0627 0645 0020 0631 0627 0020 0646 0627 062F 06CC 062F 0647 0020 0628 06AF 06CC 0631 06CC 062F 002E`

## 10. [email] If this was not you: nobody can sign in without the code we sent to this address. Do not share it.

```text
اگر شما نبودید: هیچ‌کس بدون کدی که به این نشانی فرستادیم نمی‌تواند وارد شود. آن را با کسی در میان نگذارید.
```

Code points: `0627 06AF 0631 0020 0634 0645 0627 0020 0646 0628 0648 062F 06CC 062F 003A 0020 0647 06CC 0686 200C 06A9 0633 0020 0628 062F 0648 0646 0020 06A9 062F 06CC 0020 06A9 0647 0020 0628 0647 0020 0627 06CC 0646 0020 0646 0634 0627 0646 06CC 0020 0641 0631 0633 062A 0627 062F 06CC 0645 0020 0646 0645 06CC 200C 062A 0648 0627 0646 062F 0020 0648 0627 0631 062F 0020 0634 0648 062F 002E 0020 0622 0646 0020 0631 0627 0020 0628 0627 0020 06A9 0633 06CC 0020 062F 0631 0020 0645 06CC 0627 0646 0020 0646 06AF 0630 0627 0631 06CC 062F 002E`

## 11. [email] Review your account: {link}

```text
بررسی حساب: {link}
```

Code points: `0628 0631 0631 0633 06CC 0020 062D 0633 0627 0628 003A 0020 007B 006C 0069 006E 006B 007D`
