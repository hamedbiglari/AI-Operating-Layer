<?php
/**
 * Dashboard empty state: not connected to Cloud Core.
 *
 * A merchant who opens the Dashboard submenu before ever configuring a
 * connection must not see an empty table (which reads as "no traffic
 * yet") or a wall of WP_Error strings (which reads as "broken"). Both are
 * false: the true state is "there is nothing to show because there is no
 * connection", and the only useful next action is the settings screen.
 * This view says exactly that and stops — it does not call any
 * AIOL_Client method, because none of them are meaningful without a
 * connection.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}
?>
<div class="wrap aiol-dashboard" dir="<?php echo is_rtl() ? 'rtl' : 'ltr'; ?>">
    <h1>
        <?php echo AIOL_Icon::render('dashboard', ['decorative' => true, 'size' => 'lg']); ?>
        <?php esc_html_e('AI Operating Layer', 'ai-operating-layer'); ?>
    </h1>

    <div class="aiol-card aiol-empty-state">
        <?php echo AIOL_Icon::render('connection', ['decorative' => true, 'size' => 'lg']); ?>
        <h2><?php esc_html_e('Not connected yet', 'ai-operating-layer'); ?></h2>
        <p>
            <?php
            esc_html_e(
                'Traffic, AI agents, access decisions and search demand appear here once this site is connected to Cloud Core. Nothing has been recorded because nothing has been sent yet.',
                'ai-operating-layer'
            );
            ?>
        </p>
        <a class="button button-primary" href="<?php echo esc_url(admin_url('admin.php?page=ai-operating-layer')); ?>">
            <?php esc_html_e('Go to connection settings', 'ai-operating-layer'); ?>
        </a>
    </div>
</div>
