#!/usr/bin/env bash
# Runs every PHP test that does not require WordPress. Exits non-zero on failure.
set -u
cd "$(dirname "$0")"
fail=0
for f in test-*.php; do
  php "$f" || fail=1
done
echo "--- lint ---"
for f in $(find .. -name "*.php"); do
  php -l "$f" | grep -v "No syntax errors" && fail=1
done
[ $fail -eq 0 ] && echo "ALL PHP CHECKS PASSED"
exit $fail
