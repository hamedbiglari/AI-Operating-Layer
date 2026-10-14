<?php
/**
 * Settings & status view.
 *
 * Accessibility notes that are structural, not decorative:
 *  - one <h1>, sections under <h2>; heading order never skips a level
 *  - status uses icon + word + colour (three signals, never colour alone)
 *  - notices use role="status" / role="alert" so they are announced
 *  - the hint under each field is linked by aria-describedby, not a placeholder
 *  - every SVG icon is aria-hidden with the meaning carried by adjacent text
 *
 * @var AIOL_Admin $this
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

$aiol_conn      = $this->connection_state();
$aiol_state     = $aiol_conn['state'];
$aiol_identity  = $aiol_conn['identity'] ?? [];
$aiol_error     = $aiol_conn['error'] ?? '';
$aiol_retryable = $aiol_conn['retry_safe'] ?? false;
$aiol_configured = $aiol_state !== AIOL_Status::NOT_CONFIGURED;

$aiol_form_error = get_transient('aiol_form_error');
delete_transient('aiol_form_error');

$aiol_notice = isset($_GET['aiol_status']) ? sanitize_key(wp_unslash($_GET['aiol_status'])) : '';

/** Inline SVG icons — never emoji (anti-pattern list). */
function aiol_icon(string $name): string
{
    $paths = [
        'ok'       => '<path d="M20 6 9 17l-5-5"/>',
        'warn'     => '<path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
        'fail'     => '<path d="M18 6 6 18M6 6l12 12"/>',
        'info'     => '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/>',
    ];
    $d = $paths[$name] ?? $paths['info'];
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        . 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' . $d . '</svg>';
}

function aiol_pill(string $state): string
{
    $map = [
        AIOL_Status::OK             => ['ok', 'ok'],
        AIOL_Status::DEGRADED       => ['degraded', 'warn'],
        AIOL_Status::FAILED         => ['failed', 'fail'],
        AIOL_Status::NOT_CONFIGURED => ['muted', 'info'],
    ];
    [$variant, $icon] = $map[$state] ?? ['muted', 'info'];
    return sprintf(
        '<span class="aiol-pill aiol-pill--%s">%s<span>%s</span></span>',
        esc_attr($variant),
        aiol_icon($icon),
        esc_html(AIOL_Status::label($state))
    );
}
?>
<div class="wrap aiol-wrap">
    <h1><?php esc_html_e('AI Operating Layer', 'ai-operating-layer'); ?></h1>

    <p class="description" style="max-width:70ch">
        <?php esc_html_e(
            'Cloud Core is the source of truth for your products, knowledge, evidence and trust. This plugin connects WordPress to it — it publishes references, never business data of its own.',
            'ai-operating-layer'
        ); ?>
    </p>

    <?php if ($aiol_notice === 'connected') : ?>
        <div class="notice notice-success is-dismissible" role="status">
            <p><?php esc_html_e('Connected to Cloud Core and the credential was verified.', 'ai-operating-layer'); ?></p>
        </div>
    <?php elseif ($aiol_notice === 'disconnected') : ?>
        <div class="notice notice-info is-dismissible" role="status">
            <p><?php esc_html_e('Disconnected. The stored token has been removed from this site. Mappings in Cloud Core are unchanged.', 'ai-operating-layer'); ?></p>
        </div>
    <?php elseif ($aiol_notice === 'unverified' && $aiol_form_error) : ?>
        <div class="notice notice-error" role="alert">
            <p><strong><?php esc_html_e('Settings saved, but the credential did not authenticate.', 'ai-operating-layer'); ?></strong></p>
            <p><?php echo esc_html($aiol_form_error['message']); ?></p>
        </div>
    <?php elseif ($aiol_notice === 'error' && $aiol_form_error) : ?>
        <div class="notice notice-error" role="alert">
            <p><?php echo esc_html($aiol_form_error['message']); ?></p>
        </div>
    <?php endif; ?>

    <?php if (!$aiol_configured) : ?>
        <!-- EMPTY STATE: explains why it is empty AND the single next action. -->
        <div class="aiol-empty">
            <h2><?php esc_html_e('Not connected yet', 'ai-operating-layer'); ?></h2>
            <p>
                <?php esc_html_e(
                    'To connect, open your Cloud Core installation settings, issue an installation token, and paste it below along with your Cloud Core URL.',
                    'ai-operating-layer'
                ); ?>
            </p>
        </div>
    <?php else : ?>
        <h2><?php esc_html_e('Status', 'ai-operating-layer'); ?></h2>
        <div class="aiol-grid">
            <section class="aiol-card" aria-labelledby="aiol-h-connection">
                <h3 class="aiol-card__title" id="aiol-h-connection"><?php esc_html_e('Connection', 'ai-operating-layer'); ?></h3>
                <dl class="aiol-status-list">
                    <div>
                        <dt><?php esc_html_e('Cloud Core', 'ai-operating-layer'); ?></dt>
                        <dd><?php echo aiol_pill($aiol_state); // phpcs:ignore WordPress.Security.EscapeOutput -- built from escaped parts ?></dd>
                    </div>
                    <div>
                        <dt><?php esc_html_e('Endpoint', 'ai-operating-layer'); ?></dt>
                        <dd><code><?php echo esc_html($this_endpoint ?? get_option(AIOL_Credentials::OPTION_ENDPOINT, '')); ?></code></dd>
                    </div>
                    <div>
                        <dt><?php esc_html_e('Token', 'ai-operating-layer'); ?></dt>
                        <dd><code><?php echo esc_html((new AIOL_Credentials())->masked_token()); ?></code></dd>
                    </div>
                </dl>
                <?php if ($aiol_error !== '') : ?>
                    <p class="aiol-error-text" role="alert">
                        <?php echo aiol_icon('fail'); // phpcs:ignore WordPress.Security.EscapeOutput -- static markup ?>
                        <span>
                            <?php echo esc_html($aiol_error); ?>
                            <?php if ($aiol_retryable) : ?>
                                <br><?php esc_html_e('Retrying is safe — nothing was changed.', 'ai-operating-layer'); ?>
                            <?php endif; ?>
                        </span>
                    </p>
                <?php endif; ?>
            </section>

            <section class="aiol-card" aria-labelledby="aiol-h-identity">
                <h3 class="aiol-card__title" id="aiol-h-identity"><?php esc_html_e('This installation', 'ai-operating-layer'); ?></h3>
                <?php if ($aiol_identity) : ?>
                    <dl class="aiol-status-list">
                        <div>
                            <dt><?php esc_html_e('Organization', 'ai-operating-layer'); ?></dt>
                            <dd><code><?php echo esc_html((string) ($aiol_identity['organization_id'] ?? '—')); ?></code></dd>
                        </div>
                        <div>
                            <dt><?php esc_html_e('Adapter type', 'ai-operating-layer'); ?></dt>
                            <dd><?php echo esc_html((string) ($aiol_identity['adapter_type'] ?? '—')); ?></dd>
                        </div>
                        <div>
                            <dt><?php esc_html_e('Permissions', 'ai-operating-layer'); ?></dt>
                            <dd><?php echo esc_html(implode(', ', array_map('strval', (array) ($aiol_identity['scopes'] ?? [])))); ?></dd>
                        </div>
                    </dl>
                    <p class="aiol-hint">
                        <?php esc_html_e('Your organization is determined by Cloud Core from this token. WordPress cannot choose or change it.', 'ai-operating-layer'); ?>
                    </p>
                <?php else : ?>
                    <p class="aiol-hint"><?php esc_html_e('Identity unavailable while Cloud Core is unreachable.', 'ai-operating-layer'); ?></p>
                <?php endif; ?>
            </section>
        </div>
    <?php endif; ?>

    <h2><?php esc_html_e('Connection settings', 'ai-operating-layer'); ?></h2>
    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="aiol-card">
        <input type="hidden" name="action" value="aiol_save_connection">
        <?php wp_nonce_field('aiol_settings'); ?>

        <div class="aiol-field<?php echo ($aiol_form_error && in_array($aiol_form_error['code'], ['aiol_endpoint_empty','aiol_endpoint_scheme','aiol_endpoint_invalid'], true)) ? ' aiol-field--error' : ''; ?>">
            <label for="aiol_endpoint"><?php esc_html_e('Cloud Core URL', 'ai-operating-layer'); ?> <span aria-hidden="true">*</span></label>
            <input type="url" id="aiol_endpoint" name="aiol_endpoint" required
                   aria-describedby="aiol_endpoint_hint"
                   value="<?php echo esc_attr($aiol_form_error['endpoint'] ?? get_option(AIOL_Credentials::OPTION_ENDPOINT, '')); ?>">
            <span class="aiol-hint" id="aiol_endpoint_hint">
                <?php esc_html_e('For example https://core.example.com — the address of your Cloud Core server.', 'ai-operating-layer'); ?>
            </span>
        </div>

        <div class="aiol-field<?php echo ($aiol_form_error && in_array($aiol_form_error['code'], ['aiol_token_empty','aiol_token_shape','unauthorized'], true)) ? ' aiol-field--error' : ''; ?>">
            <label for="aiol_token"><?php esc_html_e('Installation token', 'ai-operating-layer'); ?> <span aria-hidden="true">*</span></label>
            <input type="password" id="aiol_token" name="aiol_token" required autocomplete="off"
                   aria-describedby="aiol_token_hint"
                   value="">
            <span class="aiol-hint" id="aiol_token_hint">
                <?php esc_html_e('Issued in Cloud Core under Installations. It begins with "aiol_". It is stored on this site and never shown again — if you lose it, rotate the credential in Cloud Core.', 'ai-operating-layer'); ?>
            </span>
        </div>

        <p>
            <button type="submit" class="button button-primary">
                <?php echo $aiol_configured
                    ? esc_html__('Update connection', 'ai-operating-layer')
                    : esc_html__('Connect to Cloud Core', 'ai-operating-layer'); ?>
            </button>
        </p>
    </form>

    <?php if ($aiol_configured) : ?>
        <h2><?php esc_html_e('Disconnect', 'ai-operating-layer'); ?></h2>
        <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="aiol-card"
              onsubmit="return confirm('<?php echo esc_js(__('Remove the stored token from this site? Mappings already in Cloud Core are not deleted.', 'ai-operating-layer')); ?>');">
            <input type="hidden" name="action" value="aiol_disconnect">
            <?php wp_nonce_field('aiol_settings'); ?>
            <p class="aiol-hint" style="margin-top:0">
                <?php esc_html_e('Removes the token from this site only. Your data in Cloud Core is untouched.', 'ai-operating-layer'); ?>
            </p>
            <button type="submit" class="button"><?php esc_html_e('Disconnect', 'ai-operating-layer'); ?></button>
        </form>
    <?php endif; ?>

    <?php
    if ($aiol_configured) {
        [$aiol_rows, $aiol_list_error, $aiol_list_error_code] = $this->fetch_mappings();
        require AIOL_PLUGIN_DIR . 'admin/view-mappings.php';
    }

    $aiol_diagnostics_service = $this->diagnostics();
    if ($aiol_diagnostics_service instanceof AIOL_Diagnostics) {
        $aiol_diag          = $aiol_diagnostics_service->run();
        $aiol_dimensions    = AIOL_Diagnostics::dimensions($aiol_diag);
        $aiol_actor_summary = AIOL_Actors::summary();
        require AIOL_PLUGIN_DIR . 'admin/view-diagnostics.php';
    }
    ?>
</div>