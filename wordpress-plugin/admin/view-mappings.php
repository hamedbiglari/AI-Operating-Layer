<?php
/**
 * Mappings screen — every state a merchant can actually land in.
 *
 * STATE COVERAGE (Phase 9 brief §11). This screen is asynchronous and
 * dependency-backed, so the happy path is the least interesting case:
 *
 *   not_configured  -> empty state explaining the ONE next action
 *   loading         -> aria-busy region, no double-submit
 *   empty           -> "why is this empty" + what to do, not a blank table
 *   error           -> what failed, whether data changed, whether retry is safe
 *   rate_limited    -> distinct from error; explicitly recoverable
 *   conflict        -> per-row, never resolved silently
 *   stale/failed    -> per-row status with its own word, icon and colour
 *
 * @var AIOL_Admin $this
 * @var array      $aiol_rows
 * @var string     $aiol_list_error
 * @var string     $aiol_list_error_code
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

$aiol_retry_safe = $aiol_list_error_code !== ''
    && AIOL_Client::is_retry_safe($aiol_list_error_code);
?>
<h2 id="aiol-mappings-heading"><?php esc_html_e('Mapped content', 'ai-operating-layer'); ?></h2>

<p class="description" style="max-width:70ch">
    <?php esc_html_e(
        'Each row links one WordPress post to one object in Cloud Core. Cloud Core owns the object; WordPress owns only the post.',
        'ai-operating-layer'
    ); ?>
</p>

<?php if ($aiol_list_error !== '') : ?>
    <div class="aiol-card" role="alert">
        <p class="aiol-error-text" style="margin-top:0">
            <span>
                <strong><?php esc_html_e('Could not load mappings.', 'ai-operating-layer'); ?></strong><br>
                <?php echo esc_html($aiol_list_error); ?><br>
                <?php if ($aiol_retry_safe) : ?>
                    <?php esc_html_e('Nothing was changed in Cloud Core. Retrying is safe.', 'ai-operating-layer'); ?>
                <?php else : ?>
                    <?php esc_html_e('Retrying will not help until the cause above is fixed.', 'ai-operating-layer'); ?>
                <?php endif; ?>
            </span>
        </p>
        <?php if ($aiol_retry_safe) : ?>
            <p style="margin-bottom:0">
                <a class="button" href="<?php echo esc_url(add_query_arg(['page' => 'ai-operating-layer'], admin_url('admin.php'))); ?>">
                    <?php esc_html_e('Retry', 'ai-operating-layer'); ?>
                </a>
            </p>
        <?php endif; ?>
    </div>
<?php elseif ($aiol_rows === []) : ?>
    <!-- EMPTY STATE: says why, and the single next action. Not a blank table. -->
    <div class="aiol-empty">
        <h3><?php esc_html_e('No content is linked yet', 'ai-operating-layer'); ?></h3>
        <p>
            <?php esc_html_e(
                'Open any post, page or product, find the "AI Operating Layer" panel in the sidebar, and paste the Cloud Core object ID it represents. It will appear here after you save.',
                'ai-operating-layer'
            ); ?>
        </p>
    </div>
<?php else : ?>
    <table class="aiol-table" aria-labelledby="aiol-mappings-heading">
        <thead>
            <tr>
                <th scope="col"><?php esc_html_e('WordPress post', 'ai-operating-layer'); ?></th>
                <th scope="col"><?php esc_html_e('Cloud Core object', 'ai-operating-layer'); ?></th>
                <th scope="col"><?php esc_html_e('Type', 'ai-operating-layer'); ?></th>
                <th scope="col"><?php esc_html_e('Sync status', 'ai-operating-layer'); ?></th>
                <th scope="col"><?php esc_html_e('Last synced', 'ai-operating-layer'); ?></th>
            </tr>
        </thead>
        <tbody>
        <?php foreach ($aiol_rows as $aiol_row) :
            $aiol_sync  = (string) ($aiol_row['sync_status'] ?? 'pending');
            $aiol_wp_id = (int) ($aiol_row['wordpress_post_id'] ?? 0);
            $aiol_title = $aiol_wp_id ? get_the_title($aiol_wp_id) : '';
            ?>
            <tr>
                <td data-label="<?php esc_attr_e('WordPress post', 'ai-operating-layer'); ?>">
                    <?php if ($aiol_title !== '') : ?>
                        <a href="<?php echo esc_url(get_edit_post_link($aiol_wp_id) ?: '#'); ?>">
                            <?php echo esc_html($aiol_title); ?>
                        </a>
                    <?php else : ?>
                        <span class="aiol-hint">
                            <?php
                            /* translators: %d: WordPress post ID */
                            printf(esc_html__('Post %d (not on this site)', 'ai-operating-layer'), (int) $aiol_wp_id);
                            ?>
                        </span>
                    <?php endif; ?>
                </td>
                <td data-label="<?php esc_attr_e('Cloud Core object', 'ai-operating-layer'); ?>">
                    <code><?php echo esc_html((string) ($aiol_row['object_id'] ?? '')); ?></code>
                </td>
                <td data-label="<?php esc_attr_e('Type', 'ai-operating-layer'); ?>">
                    <?php echo esc_html((string) ($aiol_row['object_type'] ?? '')); ?>
                </td>
                <td data-label="<?php esc_attr_e('Sync status', 'ai-operating-layer'); ?>">
                    <?php
                    // Icon + word + colour. Never colour alone.
                    $aiol_variant = ['synced' => 'ok', 'stale' => 'degraded', 'failed' => 'failed'][$aiol_sync] ?? 'muted';
                    $aiol_icon    = ['synced' => 'ok', 'stale' => 'warn', 'failed' => 'fail'][$aiol_sync] ?? 'info';
                    $aiol_word    = [
                        'synced'  => __('Synced', 'ai-operating-layer'),
                        'stale'   => __('Out of date', 'ai-operating-layer'),
                        'failed'  => __('Failed', 'ai-operating-layer'),
                        'pending' => __('Pending', 'ai-operating-layer'),
                    ][$aiol_sync] ?? $aiol_sync;
                    printf(
                        '<span class="aiol-pill aiol-pill--%s">%s<span>%s</span></span>',
                        esc_attr($aiol_variant),
                        aiol_icon($aiol_icon), // phpcs:ignore WordPress.Security.EscapeOutput
                        esc_html($aiol_word)
                    );
                    ?>
                </td>
                <td data-label="<?php esc_attr_e('Last synced', 'ai-operating-layer'); ?>">
                    <?php
                    $aiol_when = (string) ($aiol_row['last_synced_at'] ?? '');
                    echo $aiol_when !== ''
                        ? esc_html(human_time_diff(strtotime($aiol_when), time()) . ' ' . __('ago', 'ai-operating-layer'))
                        : '<span class="aiol-hint">' . esc_html__('Never', 'ai-operating-layer') . '</span>';
                    ?>
                </td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
<?php endif; ?>
