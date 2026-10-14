<?php
/**
 * Machine-readable representations — llms.txt and Markdown.
 * Absorbed from the legacy toolkit (capability map #5, #6, #20, #22).
 *
 * WHAT A REPRESENTATION IS, AND IS NOT
 *
 * These endpoints serve WordPress's OWN content in a machine-friendly
 * shape. That is a legitimate adapter job: it is transport, not authority.
 *
 * They are NOT Business Truth, and every response says so in a header
 * comment rather than leaving it to be inferred. Specifically:
 *
 *   - no price, stock, evidence or trust data appears here, ever; those
 *     live in Cloud Core and reach the public only through
 *     `AIOL_Schema`, which renders what Core asserts
 *   - a post's presence here means "this text is published on this
 *     WordPress site", not "Cloud Core has verified this"
 *
 * INVALIDATION (widened from legacy)
 *
 * The legacy version hooked `save_post`, `deleted_post` and `trashed_post`.
 * That misses the cases that matter most: unpublishing (a post going
 * private or draft stayed listed until the cache expired) and restoring
 * from trash. Both now invalidate, as does a mapping change, because a
 * remapped post's representation is stale by definition.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Representations
{
    public const QUERY_LLMS   = 'aiol_llms_txt';
    public const QUERY_FORMAT = 'aiol_format';
    private const CACHE_KEY   = 'llms_txt';
    private const CACHE_TTL   = 3600;
    private const MAX_ITEMS   = 200;

    private AIOL_Cache $cache;

    public function __construct(AIOL_Cache $cache)
    {
        $this->cache = $cache;
    }

    public function register(): void
    {
        add_action('init', [$this, 'add_rewrite_rules']);
        add_filter('query_vars', [$this, 'add_query_vars']);
        add_action('template_redirect', [$this, 'handle_request'], 5);

        // Widened invalidation — see class docstring.
        foreach (['save_post', 'deleted_post', 'trashed_post', 'untrashed_post'] as $hook) {
            add_action($hook, [$this, 'invalidate']);
        }
        add_action('transition_post_status', [$this, 'invalidate']);
        // Fires with (post_id, new_object_id, previous_object_id); we
        // ignore the args and invalidate wholesale, which is correct for a
        // site-wide index.
        add_action('aiol_mapping_changed', [$this, 'invalidate'], 10, 3);
    }

    public function add_rewrite_rules(): void
    {
        add_rewrite_rule('^llms\.txt$', 'index.php?' . self::QUERY_LLMS . '=1', 'top');
    }

    public function add_query_vars(array $vars): array
    {
        $vars[] = self::QUERY_LLMS;
        $vars[] = self::QUERY_FORMAT;
        return $vars;
    }

    public static function is_llms_txt_enabled(): bool
    {
        $settings = get_option('aiol_settings', []);
        return !is_array($settings) || ($settings['llms_txt'] ?? true);
    }

    public static function is_markdown_enabled(): bool
    {
        $settings = get_option('aiol_settings', []);
        return !is_array($settings) || ($settings['markdown'] ?? true);
    }

    public function handle_request(): void
    {
        if (get_query_var(self::QUERY_LLMS)) {
            if (!self::is_llms_txt_enabled()) {
                return; // fall through to a normal 404
            }
            $this->serve(self::llms_txt_body($this->cached_index()), 'text/plain');
        }

        if (get_query_var(self::QUERY_FORMAT) === 'md' && is_singular()) {
            if (!self::is_markdown_enabled()) {
                return;
            }
            $post = get_post();
            if (!$post instanceof WP_Post) {
                return;
            }
            $this->serve(self::markdown($post), 'text/markdown');
        }
    }

    private function serve(string $body, string $content_type): void
    {
        if (!headers_sent()) {
            header('Content-Type: ' . $content_type . '; charset=utf-8');
            header('X-Robots-Tag: noindex');
        }
        echo $body; // phpcs:ignore WordPress.Security.EscapeOutput -- plain-text body, not HTML
        exit;
    }

    /** @return array<int, array{title:string,url:string,excerpt:string}> */
    private function cached_index(): array
    {
        $cached = $this->cache->get(self::CACHE_KEY);
        if (is_array($cached)) {
            return $cached;
        }
        $items = self::build_index();
        $this->cache->set(self::CACHE_KEY, $items, self::CACHE_TTL);
        return $items;
    }

    private static function build_index(): array
    {
        $posts = get_posts([
            'post_type'        => ['post', 'page'],
            'post_status'      => 'publish',   // enforced here, not only by routing
            'numberposts'      => self::MAX_ITEMS,
            'orderby'          => 'modified',
            'order'            => 'DESC',
            'suppress_filters' => false,
        ]);

        $items = [];
        foreach ($posts as $post) {
            // Defence in depth: a filter could have widened the query.
            if ($post->post_status !== 'publish' || !empty($post->post_password)) {
                continue;
            }
            $items[] = [
                'title'   => get_the_title($post),
                'url'     => get_permalink($post),
                'excerpt' => wp_trim_words(wp_strip_all_tags((string) $post->post_excerpt ?: (string) $post->post_content), 25),
            ];
        }
        return $items;
    }

    /**
     * Pure formatter — unit-testable without WordPress.
     *
     * @param array<int, array{title:string,url:string,excerpt:string}> $items
     */
    public static function llms_txt_body(array $items, string $site_name = '', string $site_url = ''): string
    {
        $lines = [];
        $lines[] = '# ' . ($site_name !== '' ? $site_name : 'Site');
        if ($site_url !== '') {
            $lines[] = '';
            $lines[] = '> ' . $site_url;
        }
        $lines[] = '';
        // The honesty header. Without it a consumer could reasonably read
        // this file as a verified product/knowledge feed.
        $lines[] = '<!-- This file lists content published on this WordPress site.';
        $lines[] = '     It is a representation of that content, not verified business data.';
        $lines[] = '     Prices, availability, evidence and trust claims are NOT published here. -->';
        $lines[] = '';
        $lines[] = '## Content';
        $lines[] = '';

        foreach ($items as $item) {
            $title = trim((string) ($item['title'] ?? ''));
            $url   = trim((string) ($item['url'] ?? ''));
            if ($title === '' || $url === '') {
                continue;
            }
            $excerpt = trim((string) ($item['excerpt'] ?? ''));
            $lines[] = $excerpt !== ''
                ? sprintf('- [%s](%s): %s', $title, $url, $excerpt)
                : sprintf('- [%s](%s)', $title, $url);
        }

        return implode("\n", $lines) . "\n";
    }

    /** Markdown for one post. Published-only is enforced here too. */
    public static function markdown(WP_Post $post): string
    {
        if ($post->post_status !== 'publish' || !empty($post->post_password)) {
            return "# Not available\n\nThis content is not publicly published.\n";
        }

        $body = wp_strip_all_tags(strip_shortcodes((string) $post->post_content));
        $body = preg_replace("/\n{3,}/", "\n\n", $body) ?? $body;

        $out   = [];
        $out[] = '# ' . get_the_title($post);
        $out[] = '';
        $out[] = '<!-- Representation of published WordPress content. Not verified business data. -->';
        $out[] = '';
        $out[] = trim($body);
        $out[] = '';
        $out[] = '---';
        $out[] = '';
        $out[] = 'Source: ' . get_permalink($post);
        return implode("\n", $out) . "\n";
    }

    /** Accepts and ignores hook arguments - see register(). */
    public function invalidate($unused_a = null, $unused_b = null, $unused_c = null): void
    {
        $this->cache->forget(self::CACHE_KEY);
    }
}
