<?php
/**
 * Phase 13 dashboard (ADR-076…081).
 *
 * The merchant-facing answer to four questions:
 *
 *   Who is reading my site — people or machines, and which machines?
 *   Which content is read most, and which is read least?
 *   What did people and machines search for that I could not answer?
 *   Am I connected, what version is running, and what has been happening?
 *
 * EVERY NUMBER ON THIS PAGE COMES FROM CLOUD CORE.
 *
 * Nothing is computed here. This file renders what `/telemetry/*` returns
 * and nothing else — if it started summing columns, WordPress would have
 * become a second source of analytics truth, which is the specific
 * failure §137 and §149 both name.
 *
 * TWO RENDERING RULES THAT ARE NOT COSMETIC
 *
 *   1. A NULL renders as "Not available", never as 0. The API returns
 *      `dwell_ms: null` for a view nobody measured and `mean_dwell_ms:
 *      null` for a page with no samples; printing 0 there would turn an
 *      absence of measurement into a measurement of absence.
 *   2. A status is never colour alone. Every badge carries an icon and a
 *      word, because colour is not an accessible signal and because a
 *      screenshot in a support thread has to be readable in greyscale.
 *
 * Icons come from `AIOL_Icon`, i.e. from `frontend/icons/icon-paths.json`.
 * There is no inline `<svg>` and no dashicon in this file.
 *
 * @var array $health
 * @var array $content_stats
 * @var array $agents
 * @var array $search_terms
 * @var array $log_entries
 * @var string $sort_by
 * @var string $sort_dir
 * @var array $page_views
 * @var array $errors
 * @var int $buffered
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

/** NULL-safe integer rendering. See rule 1 above. */
$num = static function ($value): string {
    if ($value === null) {
        return '<span class="aiol-na">' . esc_html__('Not available', 'ai-operating-layer') . '</span>';
    }
    return '<span class="aiol-num">' . esc_html(number_format_i18n((int) $value)) . '</span>';
};

/** Milliseconds -> "2m 41s", or "Not available" when nothing measured. */
$duration = static function ($ms): string {
    if ($ms === null) {
        return '<span class="aiol-na">' . esc_html__('Not available', 'ai-operating-layer') . '</span>';
    }
    $seconds = (int) round(((float) $ms) / 1000);
    $minutes = intdiv($seconds, 60);
    $rest    = $seconds % 60;
    return esc_html($minutes > 0 ? "{$minutes}m {$rest}s" : "{$rest}s");
};

$badge = static function (string $variant, string $icon, string $text): string {
    return '<span class="aiol-badge aiol-badge--' . esc_attr($variant) . '">'
        . AIOL_Icon::render($icon, ['decorative' => true])
        . '<span>' . esc_html($text) . '</span></span>';
};

$state_badge = static function (string $state) use ($badge): string {
    switch ($state) {
        case AIOL_Status::OK:
            return $badge('success', 'status-completed', AIOL_Status::label($state));
        case AIOL_Status::DEGRADED:
            return $badge('warning', 'status-warning', AIOL_Status::label($state));
        case AIOL_Status::FAILED:
            return $badge('danger', 'status-failed', AIOL_Status::label($state));
        default:
            return $badge('unknown', 'status-unknown', AIOL_Status::label($state));
    }
};

$tier_badge = static function (?string $tier) use ($badge): string {
    switch ($tier) {
        case AIOL_Access_Gate::FREE:
            return $badge('success', 'status-completed', __('Free', 'ai-operating-layer'));
        case AIOL_Access_Gate::PAID:
            return $badge('info', 'cost', __('Paid', 'ai-operating-layer'));
        case AIOL_Access_Gate::FORBIDDEN:
            return $badge('danger', 'lock', __('Forbidden', 'ai-operating-layer'));
        default:
            // "Not decided" is deliberately distinct from "Free". Nobody
            // chose this, and the dashboard must not report an unmade
            // decision as a permission.
            return $badge('unknown', 'status-unknown', __('Not decided', 'ai-operating-layer'));
    }
};

$sort_link = static function (string $field, string $label) use ($sort_by, $sort_dir): string {
    $next = ($sort_by === $field && $sort_dir === 'desc') ? 'asc' : 'desc';
    $url  = add_query_arg(
        ['page' => 'ai-operating-layer', 'tab' => 'dashboard', 'sort_by' => $field, 'sort_dir' => $next]
    );
    $marker = $sort_by === $field
        ? AIOL_Icon::render('action-sort', ['decorative' => true])
        : '';
    $aria = $sort_by === $field ? ($sort_dir === 'asc' ? 'ascending' : 'descending') : 'none';
    return '<th scope="col" aria-sort="' . esc_attr($aria) . '">'
        . '<a href="' . esc_url($url) . '">' . esc_html($label) . $marker . '</a></th>';
};

$overall = (string) ($health['overall'] ?? 'unknown');
?>
<div class="wrap aiol-dashboard" dir="<?php echo is_rtl() ? 'rtl' : 'ltr'; ?>">

    <?php if (!empty($errors)) : ?>
        <div class="notice notice-warning">
            <p>
                <strong><?php esc_html_e('Some sections could not be loaded from Cloud Core:', 'ai-operating-layer'); ?></strong>
            </p>
            <ul style="list-style:disc;margin-inline-start:1.5em">
                <?php foreach ($errors as $error) : ?>
                    <li><?php echo esc_html((string) $error); ?></li>
                <?php endforeach; ?>
            </ul>
            <p class="aiol-hint">
                <?php
                esc_html_e(
                    'Every other section on this page loaded independently and still shows what it could — one failure does not blank the whole dashboard.',
                    'ai-operating-layer'
                );
                ?>
            </p>
        </div>
    <?php endif; ?>

    <?php if (isset($_GET['aiol_status']) && $_GET['aiol_status'] === 'log_cleared') : ?>
        <div class="notice notice-success is-dismissible">
            <p><?php esc_html_e('Log history cleared. Cloud Core\'s recorded traffic, agents and access decisions were not affected.', 'ai-operating-layer'); ?></p>
        </div>
    <?php endif; ?>

    <h1>
        <?php echo AIOL_Icon::render('dashboard', ['decorative' => true, 'size' => 'lg']); ?>
        <?php esc_html_e('AI Operating Layer', 'ai-operating-layer'); ?>
    </h1>

    <!-- ================= Connection strip ================= -->
    <section class="aiol-card" aria-labelledby="aiol-connection-h">
        <h2 id="aiol-connection-h">
            <?php echo AIOL_Icon::render('connection', ['decorative' => true]); ?>
            <?php esc_html_e('Connection', 'ai-operating-layer'); ?>
        </h2>

        <dl class="aiol-kv">
            <dt><?php esc_html_e('Cloud Core', 'ai-operating-layer'); ?></dt>
            <dd>
                <?php
                echo empty($health['core_reachable'])
                    ? $state_badge(AIOL_Status::FAILED)
                    : $state_badge(AIOL_Status::OK);
                ?>
            </dd>

            <dt><?php esc_html_e('Database', 'ai-operating-layer'); ?></dt>
            <dd><?php echo $state_badge((string) ($health['database'] ?? 'unknown')); ?></dd>

            <dt><?php esc_html_e('Queue (Redis)', 'ai-operating-layer'); ?></dt>
            <dd><?php echo $state_badge((string) ($health['redis'] ?? 'unknown')); ?></dd>

            <dt><?php esc_html_e('Rate limiting', 'ai-operating-layer'); ?></dt>
            <dd><?php echo $state_badge((string) ($health['rate_limiting'] ?? 'unknown')); ?></dd>

            <dt><?php esc_html_e('Overall', 'ai-operating-layer'); ?></dt>
            <dd><?php echo $state_badge($overall); ?></dd>

            <dt><?php esc_html_e('Plugin version', 'ai-operating-layer'); ?></dt>
            <dd><bdi class="aiol-identifier">v<?php echo esc_html(AIOL_VERSION); ?></bdi></dd>

            <dt><?php esc_html_e('Cloud Core version', 'ai-operating-layer'); ?></dt>
            <dd><bdi class="aiol-identifier">v<?php echo esc_html((string) ($health['core_version'] ?? '—')); ?></bdi></dd>

            <dt><?php esc_html_e('Telemetry API', 'ai-operating-layer'); ?></dt>
            <dd><bdi class="aiol-identifier">v<?php echo esc_html((string) ($health['api_version'] ?? '—')); ?></bdi></dd>

            <dt><?php esc_html_e('Last event received', 'ai-operating-layer'); ?></dt>
            <dd>
                <?php
                $last = $health['last_event_at'] ?? null;
                echo $last
                    ? esc_html(human_time_diff(strtotime((string) $last)) . ' ' . __('ago', 'ai-operating-layer'))
                    : '<span class="aiol-na">' . esc_html__('Nothing received yet', 'ai-operating-layer') . '</span>';
                ?>
            </dd>
        </dl>

        <?php if ($overall === AIOL_Status::DEGRADED) : ?>
            <p class="aiol-callout aiol-callout--warning">
                <?php echo AIOL_Icon::render('status-warning', ['decorative' => true]); ?>
                <?php
                esc_html_e(
                    'Overall status is the worst of its parts and is never rounded up. The system is serving requests and is also missing a protection; both halves of that need saying.',
                    'ai-operating-layer'
                );
                ?>
            </p>
        <?php endif; ?>
    </section>

    <!-- ================= Agents awaiting a decision ================= -->
    <?php $awaiting = (int) ($health['agents_awaiting_decision'] ?? 0); ?>
    <?php if ($awaiting > 0) : ?>
        <p class="aiol-callout aiol-callout--warning">
            <?php echo AIOL_Icon::render('shield', ['decorative' => true]); ?>
            <?php
            printf(
                /* translators: %d: number of AI agents with no access decision. */
                esc_html(_n(
                    '%d automated client has no access decision yet. It is being allowed through, and that is recorded as "Not configured" rather than as "Allowed", because nobody chose it.',
                    '%d automated clients have no access decision yet. They are being allowed through, and that is recorded as "Not configured" rather than as "Allowed", because nobody chose it.',
                    $awaiting,
                    'ai-operating-layer'
                )),
                $awaiting
            );
            ?>
        </p>
    <?php endif; ?>

    <!-- ================= Content, sortable ================= -->
    <section class="aiol-card" aria-labelledby="aiol-content-h">
        <h2 id="aiol-content-h">
            <?php echo AIOL_Icon::render('analytics', ['decorative' => true]); ?>
            <?php esc_html_e('Content, by how often it was read', 'ai-operating-layer'); ?>
        </h2>
        <p class="aiol-hint">
            <?php
            esc_html_e(
                'Sort ascending to see what nothing is reading — that half of the list is usually the more actionable one. Sorting and paging happen on the server, so the order is the same on page 7 as on page 1.',
                'ai-operating-layer'
            );
            ?>
        </p>

        <div class="aiol-table-wrap">
            <table class="aiol-table widefat">
                <caption class="screen-reader-text">
                    <?php esc_html_e('Content ranked by view count, split by who viewed it', 'ai-operating-layer'); ?>
                </caption>
                <thead>
                    <tr>
                        <th scope="col"><?php esc_html_e('Content', 'ai-operating-layer'); ?></th>
                        <?php
                        echo $sort_link('total_views', __('Total', 'ai-operating-layer'));
                        echo $sort_link('human_views', __('Human', 'ai-operating-layer'));
                        echo $sort_link('ai_crawler_views', __('AI crawler', 'ai-operating-layer'));
                        echo $sort_link('ai_answer_views', __('AI answering', 'ai-operating-layer'));
                        echo $sort_link('agent_views', __('Agent', 'ai-operating-layer'));
                        ?>
                        <th scope="col"><?php esc_html_e('Mean time on page', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Countries', 'ai-operating-layer'); ?></th>
                    </tr>
                </thead>
                <tbody>
                <?php if (empty($content_stats)) : ?>
                    <tr>
                        <td colspan="8">
                            <p class="aiol-empty">
                                <?php echo AIOL_Icon::render('analytics', ['decorative' => true, 'size' => 'lg']); ?>
                                <strong><?php esc_html_e('No traffic recorded yet', 'ai-operating-layer'); ?></strong>
                                <?php
                                esc_html_e(
                                    'Views appear here once the adapter has sent its first batch and Cloud Core has rolled up a day. This is normally within an hour of enabling telemetry.',
                                    'ai-operating-layer'
                                );
                                ?>
                            </p>
                        </td>
                    </tr>
                <?php else : ?>
                    <?php foreach ($content_stats as $row) : ?>
                        <tr>
                            <td data-label="<?php esc_attr_e('Content', 'ai-operating-layer'); ?>">
                                <span class="aiol-cell-title">
                                    <?php
                                    echo $row['content_title'] !== null
                                        ? esc_html((string) $row['content_title'])
                                        : '<span class="aiol-na">' . esc_html__('Untitled', 'ai-operating-layer') . '</span>';
                                    ?>
                                </span>
                                <bdi class="aiol-identifier"><?php echo esc_html((string) $row['path']); ?></bdi>
                            </td>
                            <td data-label="<?php esc_attr_e('Total', 'ai-operating-layer'); ?>"><?php echo $num($row['total_views'] ?? null); ?></td>
                            <td data-label="<?php esc_attr_e('Human', 'ai-operating-layer'); ?>"><?php echo $num($row['human_views'] ?? null); ?></td>
                            <td data-label="<?php esc_attr_e('AI crawler', 'ai-operating-layer'); ?>"><?php echo $num($row['ai_crawler_views'] ?? null); ?></td>
                            <td data-label="<?php esc_attr_e('AI answering', 'ai-operating-layer'); ?>"><?php echo $num($row['ai_answer_views'] ?? null); ?></td>
                            <td data-label="<?php esc_attr_e('Agent', 'ai-operating-layer'); ?>"><?php echo $num($row['agent_views'] ?? null); ?></td>
                            <td data-label="<?php esc_attr_e('Mean time on page', 'ai-operating-layer'); ?>">
                                <?php echo $duration($row['mean_dwell_ms'] ?? null); ?>
                                <?php if (!empty($row['dwell_samples'])) : ?>
                                    <span class="aiol-hint">
                                        <?php
                                        printf(
                                            /* translators: %s: number of measured samples. */
                                            esc_html__('from %s measured views', 'ai-operating-layer'),
                                            esc_html(number_format_i18n((int) $row['dwell_samples']))
                                        );
                                        ?>
                                    </span>
                                <?php endif; ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Countries', 'ai-operating-layer'); ?>"><?php echo $num($row['distinct_countries'] ?? null); ?></td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>

        <p class="aiol-hint">
            <?php
            esc_html_e(
                '"AI crawler" and "AI answering" are never added together. One is a copy being taken for later; the other is a customer\'s question being answered right now.',
                'ai-operating-layer'
            );
            ?>
        </p>
    </section>

    <!-- ================= Recent requests (raw log) ================= -->
    <section class="aiol-card" aria-labelledby="aiol-traffic-h">
        <h2 id="aiol-traffic-h">
            <?php echo AIOL_Icon::render('log', ['decorative' => true]); ?>
            <?php esc_html_e('Recent requests', 'ai-operating-layer'); ?>
        </h2>
        <p class="aiol-hint">
            <?php
            esc_html_e(
                'Every individual observation, newest first — the raw record the tables above are rolled up from. This is the same data GET /telemetry/page-views returns; nothing here is computed by this page.',
                'ai-operating-layer'
            );
            ?>
        </p>

        <div class="aiol-table-wrap">
            <table class="aiol-table widefat">
                <caption class="screen-reader-text">
                    <?php esc_html_e('Individual page-view observations with actor, location and dwell', 'ai-operating-layer'); ?>
                </caption>
                <thead>
                    <tr>
                        <th scope="col"><?php esc_html_e('Time', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Actor', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Signature', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Identification', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Country', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('IP', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Page', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Dwell', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Access', 'ai-operating-layer'); ?></th>
                    </tr>
                </thead>
                <tbody>
                <?php if (empty($page_views)) : ?>
                    <tr>
                        <td colspan="9">
                            <span class="aiol-na"><?php esc_html_e('No requests recorded yet.', 'ai-operating-layer'); ?></span>
                        </td>
                    </tr>
                <?php else : ?>
                    <?php foreach ($page_views as $view) : ?>
                        <tr>
                            <td data-label="<?php esc_attr_e('Time', 'ai-operating-layer'); ?>">
                                <?php
                                $occurred = $view['occurred_at'] ?? null;
                                echo $occurred
                                    ? esc_html(human_time_diff(strtotime((string) $occurred)) . ' ' . __('ago', 'ai-operating-layer'))
                                    : '<span class="aiol-na">—</span>';
                                ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Actor', 'ai-operating-layer'); ?>">
                                <?php echo esc_html(AIOL_Actors::type_label((string) ($view['actor_type'] ?? 'unknown'))); ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Signature', 'ai-operating-layer'); ?>">
                                <?php
                                echo !empty($view['ai_agent_id'])
                                    ? '<bdi class="aiol-identifier">' . esc_html((string) ($view['agent_signature'] ?? $view['ai_agent_id'])) . '</bdi>'
                                    : '<span class="aiol-na">' . esc_html__('—', 'ai-operating-layer') . '</span>';
                                ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Identification', 'ai-operating-layer'); ?>">
                                <?php
                                $conf = (string) ($view['confidence'] ?? 'unknown');
                                echo $conf === 'unknown'
                                    ? '<span class="aiol-na">' . esc_html__('n/a', 'ai-operating-layer') . '</span>'
                                    : esc_html(AIOL_Actors::confidence_label($conf));
                                ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Country', 'ai-operating-layer'); ?>">
                                <?php
                                echo !empty($view['geo_country'])
                                    ? esc_html((string) $view['geo_country'])
                                    : '<span class="aiol-na">' . esc_html__('Not available', 'ai-operating-layer') . '</span>';
                                ?>
                            </td>
                            <td data-label="<?php esc_attr_e('IP', 'ai-operating-layer'); ?>">
                                <?php
                                // The default report never carries the full address (a
                                // separate OWNER/ADMIN-only endpoint does) — this column
                                // is always the truncated /24 or /48, and only that.
                                echo !empty($view['ip_truncated'])
                                    ? '<bdi class="aiol-identifier">' . esc_html((string) $view['ip_truncated']) . '</bdi>'
                                    : '<span class="aiol-na">' . esc_html__('Not available', 'ai-operating-layer') . '</span>';
                                ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Page', 'ai-operating-layer'); ?>">
                                <bdi class="aiol-identifier"><?php echo esc_html((string) ($view['path'] ?? '')); ?></bdi>
                            </td>
                            <td data-label="<?php esc_attr_e('Dwell', 'ai-operating-layer'); ?>">
                                <?php echo $duration($view['dwell_ms'] ?? null); ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Access', 'ai-operating-layer'); ?>">
                                <?php
                                $decision = (string) ($view['access_decision'] ?? 'not_configured');
                                $map = [
                                    'allowed'           => ['success', 'status-completed', __('Allowed', 'ai-operating-layer')],
                                    'blocked'           => ['danger', 'lock', __('Blocked', 'ai-operating-layer')],
                                    'payment_required'  => ['info', 'cost', __('Payment required', 'ai-operating-layer')],
                                    'not_configured'    => ['unknown', 'status-unknown', __('Not decided', 'ai-operating-layer')],
                                ];
                                [$variant, $icon, $label] = $map[$decision] ?? $map['not_configured'];
                                echo $badge($variant, $icon, $label);
                                ?>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>

        <p class="aiol-hint">
            <?php
            printf(
                /* translators: %s: number of events waiting to be sent. */
                esc_html__('%s observation(s) on this site are buffered locally and have not yet been sent to Cloud Core.', 'ai-operating-layer'),
                esc_html(number_format_i18n($buffered))
            );
            ?>
        </p>
    </section>

    <!-- ================= Agents and access ================= -->
    <section class="aiol-card" aria-labelledby="aiol-agents-h">
        <h2 id="aiol-agents-h">
            <?php echo AIOL_Icon::render('agent', ['decorative' => true]); ?>
            <?php esc_html_e('Every automated client that has visited', 'ai-operating-layer'); ?>
        </h2>
        <p class="aiol-hint">
            <?php
            esc_html_e(
                'There is no filter that hides unrecognised clients. The interesting one is always the one nobody had heard of yet.',
                'ai-operating-layer'
            );
            ?>
        </p>

        <div class="aiol-table-wrap">
            <table class="aiol-table widefat">
                <caption class="screen-reader-text">
                    <?php esc_html_e('Automated clients observed, with their current access decision', 'ai-operating-layer'); ?>
                </caption>
                <thead>
                    <tr>
                        <th scope="col"><?php esc_html_e('Client', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Type', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Stated purpose', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Identification', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Requests', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Access', 'ai-operating-layer'); ?></th>
                    </tr>
                </thead>
                <tbody>
                <?php foreach ($agents as $agent) : ?>
                    <tr>
                        <td data-label="<?php esc_attr_e('Client', 'ai-operating-layer'); ?>">
                            <bdi class="aiol-identifier"><?php echo esc_html((string) $agent['signature']); ?></bdi>
                            <span class="aiol-hint">
                                <?php
                                echo !empty($agent['vendor'])
                                    ? esc_html((string) $agent['vendor'])
                                    : '<span class="aiol-na">' . esc_html__('Operator unknown', 'ai-operating-layer') . '</span>';
                                ?>
                            </span>
                        </td>
                        <td data-label="<?php esc_attr_e('Type', 'ai-operating-layer'); ?>">
                            <?php echo esc_html(AIOL_Actors::type_label((string) $agent['actor_type'])); ?>
                        </td>
                        <td data-label="<?php esc_attr_e('Stated purpose', 'ai-operating-layer'); ?>">
                            <?php
                            echo ($agent['declared_purpose'] ?? 'unknown') === 'unknown'
                                ? '<span class="aiol-na">' . esc_html__('Not declared', 'ai-operating-layer') . '</span>'
                                : esc_html((string) $agent['declared_purpose']);
                            ?>
                        </td>
                        <td data-label="<?php esc_attr_e('Identification', 'ai-operating-layer'); ?>">
                            <?php
                            $conf = (string) ($agent['confidence'] ?? 'unknown');
                            echo $badge(
                                $conf === 'detected' ? 'info' : ($conf === 'verified' ? 'success' : 'warning'),
                                'status-unknown',
                                AIOL_Actors::confidence_label($conf)
                            );
                            ?>
                        </td>
                        <td data-label="<?php esc_attr_e('Requests', 'ai-operating-layer'); ?>"><?php echo $num($agent['observation_count'] ?? null); ?></td>
                        <td data-label="<?php esc_attr_e('Access', 'ai-operating-layer'); ?>"><?php echo $tier_badge($agent['tier'] ?? null); ?></td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>

        <p class="aiol-callout">
            <?php echo AIOL_Icon::render('info', ['decorative' => true]); ?>
            <?php
            esc_html_e(
                'A User-Agent header is a claim a request makes about itself, not a verified identity. "Detected" means the header matched a published signature; "Verified" would need reverse-DNS confirmation and is not built, so nothing here can show it. Blocking by header stops honest agents and does not stop dishonest ones.',
                'ai-operating-layer'
            );
            ?>
        </p>
    </section>

    <!-- ================= Search demand ================= -->
    <section class="aiol-card" aria-labelledby="aiol-search-h">
        <h2 id="aiol-search-h">
            <?php echo AIOL_Icon::render('action-search', ['decorative' => true]); ?>
            <?php esc_html_e('What was searched for', 'ai-operating-layer'); ?>
        </h2>

        <div class="aiol-table-wrap">
            <table class="aiol-table widefat">
                <caption class="screen-reader-text">
                    <?php esc_html_e('Search terms by volume, with how often they returned nothing', 'ai-operating-layer'); ?>
                </caption>
                <thead>
                    <tr>
                        <th scope="col"><?php esc_html_e('Term', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Searched', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Found nothing', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Last searched', 'ai-operating-layer'); ?></th>
                    </tr>
                </thead>
                <tbody>
                <?php foreach ($search_terms as $term) : ?>
                    <tr>
                        <td data-label="<?php esc_attr_e('Term', 'ai-operating-layer'); ?>"><bdi><?php echo esc_html((string) $term['query_text']); ?></bdi></td>
                        <td data-label="<?php esc_attr_e('Searched', 'ai-operating-layer'); ?>"><?php echo $num($term['search_count'] ?? null); ?></td>
                        <td data-label="<?php esc_attr_e('Found nothing', 'ai-operating-layer'); ?>"><?php echo $num($term['zero_result_count'] ?? null); ?></td>
                        <td data-label="<?php esc_attr_e('Last searched', 'ai-operating-layer'); ?>">
                            <?php echo esc_html((string) ($term['last_searched_at'] ?? '')); ?>
                        </td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>

        <p class="aiol-hint">
            <?php
            esc_html_e(
                '"Found nothing" counts searches that ran and returned zero results — each one is a content gap with a date on it. A term nobody measured is blank, not zero; the two are not merged. These are candidates, not filed knowledge gaps: a gap list full of typos is a gap list nobody reads.',
                'ai-operating-layer'
            );
            ?>
        </p>
    </section>

    <!-- ================= Log ================= -->
    <section class="aiol-card" aria-labelledby="aiol-log-h">
        <h2 id="aiol-log-h">
            <?php echo AIOL_Icon::render('log', ['decorative' => true]); ?>
            <?php esc_html_e('Adapter log', 'ai-operating-layer'); ?>
        </h2>

        <div class="aiol-table-wrap">
            <table class="aiol-table widefat">
                <caption class="screen-reader-text"><?php esc_html_e('Recent adapter log entries', 'ai-operating-layer'); ?></caption>
                <thead>
                    <tr>
                        <th scope="col"><?php esc_html_e('Time (UTC)', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Level', 'ai-operating-layer'); ?></th>
                        <th scope="col"><?php esc_html_e('Message', 'ai-operating-layer'); ?></th>
                    </tr>
                </thead>
                <tbody>
                <?php if (empty($log_entries)) : ?>
                    <tr><td colspan="3"><span class="aiol-na"><?php esc_html_e('The log is empty.', 'ai-operating-layer'); ?></span></td></tr>
                <?php else : ?>
                    <?php foreach ($log_entries as $entry) : ?>
                        <tr>
                            <td data-label="<?php esc_attr_e('Time (UTC)', 'ai-operating-layer'); ?>"><?php echo esc_html((string) ($entry['time'] ?? '')); ?></td>
                            <td data-label="<?php esc_attr_e('Level', 'ai-operating-layer'); ?>">
                                <?php
                                $level = (string) ($entry['level'] ?? 'info');
                                echo $badge(
                                    $level === 'error' ? 'danger' : 'info',
                                    $level === 'error' ? 'status-failed' : 'info',
                                    $level
                                );
                                ?>
                            </td>
                            <td data-label="<?php esc_attr_e('Message', 'ai-operating-layer'); ?>"><?php echo esc_html((string) ($entry['message'] ?? '')); ?></td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>

        <form method="post" class="aiol-actions">
            <?php wp_nonce_field('aiol_clear_log'); ?>
            <input type="hidden" name="aiol_action" value="clear_log">
            <button type="submit" class="button button-secondary aiol-button--danger">
                <?php echo AIOL_Icon::render('action-delete', ['decorative' => true]); ?>
                <?php esc_html_e('Clear log history', 'ai-operating-layer'); ?>
            </button>
        </form>

        <p class="aiol-hint">
            <?php
            esc_html_e(
                'Clearing removes this site\'s own adapter log and its unsent telemetry buffer. It does not delete page views, agents or access decisions held in Cloud Core — those are the analytics record, and a log-clearing button that quietly erased them would be a destructive action wearing a harmless label. Credential-shaped strings are stripped before anything is written.',
                'ai-operating-layer'
            );
            ?>
        </p>
    </section>
</div>
