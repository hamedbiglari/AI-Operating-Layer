<?php
declare(strict_types=1);

if (!class_exists('T')) {
    final class T
    {
        public static int $passed = 0;
        public static array $failed = [];

        public static function is($actual, $expected, string $label): void
        {
            if ($actual === $expected) { self::$passed++; return; }
            self::$failed[] = sprintf("%s\n    expected: %s\n    actual:   %s",
                $label, var_export($expected, true), var_export($actual, true));
        }
        public static function true($actual, string $label): void { self::is($actual, true, $label); }
        public static function null($actual, string $label): void { self::is($actual, null, $label); }
        public static function report(string $suite): int
        {
            $total = self::$passed + count(self::$failed);
            if (self::$failed === []) { printf("%s: %d passed\n", $suite, $total); return 0; }
            printf("%s: %d/%d FAILED\n", $suite, count(self::$failed), $total);
            foreach (self::$failed as $f) { echo "  - $f\n"; }
            return 1;
        }
    }
}
