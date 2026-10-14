<?php
/**
 * Diagnostics & actor observation view.
 *
 * The heading below is not decoration. The legacy plugin showed a single
 * "AI Readiness Score: 72/100", which reads as an authoritative rating and
 * is not one. Everything on this screen is explicitly framed as an internal
 * technical diagnostic of THIS WordPress site, with dimensions the adapter
 * cannot measure shown as "Not measured here" rather than as a zero.
 *
 * @var array $aiol_diag
 * @var array $aiol_dimensions
 * @var array $aiol_actor_summary
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

$aiol_status_meta = [
    AIOL_Diagnostics::PASS    => ['ok', 'ok', __('Pass', 'ai-operating-layer')],
    AIOL_Diagnostics::WARNING => ['degraded', 'warn', __('Needs attention', 'ai-operating-layer')],
    AIOL_Diagnostics::FAIL    => ['failed', 'fail', __('Problem', 'ai-operating-layer')],
    AIOL_Diagnostics::UNKNOWN => ['muted', 'info', __('Not determined', 'ai-operating-layer')],
];
?>
<h2 id="aiol-diagnostics-heading"><?php esc_html_e('Site diagnostics', 'ai-operating-layer'); ?></h2>

<div class="notice notice-info inline" role="note" style="margin:0 0 16px">
    <p>
        <strong><?php esc_html_e('Internal diagnostic.', 'ai-operating-layer'); ?></strong>
        <?php esc_html_e(
            'These are technical checks of this WordPress site. They are not a rating, not a score, and say nothing about how any AI system actually treats your content.',
            'ai-operating-layer'
        ); ?>
    </p>
</div>

<div class="aiol-grid">
    <section class="aiol-card" aria-labelledby="aiol-h-checks">
        <h3 class="aiol-card__title" id="aiol-h-checks"><?php esc_html_e('Technical checks', 'ai-operating-layer'); ?></h3>
        <dl class="aiol-status-list">
            <?php foreach ($aiol_diag as $aiol_check) :
                [$aiol_variant, $aiol_icon, $aiol_word] = $aiol_status_meta[$aiol_check['status']] ?? $aiol_status_meta[AIOL_Diagnostics::UNKNOWN];
                ?>
                <div>
                    <dt>
                        <?php echo esc_html($aiol_check['label']); ?>
                        <span class="aiol-hint" style="display:block"><?php echo esc_html($aiol_check['detail']); ?></span>
                    </dt>
                    <dd>
                        <?php printf(
                            '<span class="aiol-pill aiol-pill--%s">%s<span>%s</span></span>',
                            esc_attr($aiol_variant),
                            aiol_icon($aiol_icon), // phpcs:ignore WordPress.Security.EscapeOutput
                            esc_html($aiol_word)
                        ); ?>
                    </dd>
                </div>
            <?php endforeach; ?>
        </dl>
    </section>

    <section class="aiol-card" aria-labelledby="aiol-h-dims">
        <h3 class="aiol-card__title" id="aiol-h-dims"><?php esc_html_e('Coverage dimensions', 'ai-operating-layer'); ?></h3>
        <dl class="aiol-status-list">
            <?php
            $aiol_dim_labels = [
                'technical_discoverability' => __('Technical discoverability', 'ai-operating-layer'),
                'machine_readability'       => __('Machine readability', 'ai-operating-layer'),
                'knowledge_coverage'        => __('Knowledge coverage', 'ai-operating-layer'),
                'evidence_coverage'         => __('Evidence coverage', 'ai-operating-layer'),
                'trust_coverage'            => __('Trust coverage', 'ai-operating-layer'),
                'commerce_readiness'        => __('Commerce readiness', 'ai-operating-layer'),
                'ai_visibility'             => __('AI visibility', 'ai-operating-layer'),
            ];
            foreach ($aiol_dimensions as $aiol_key => $aiol_dim) :
                [$aiol_variant, $aiol_icon, $aiol_word] = $aiol_status_meta[$aiol_dim['state']] ?? $aiol_status_meta[AIOL_Diagnostics::UNKNOWN];
                ?>
                <div>
                    <dt>
                        <?php echo esc_html($aiol_dim_labels[$aiol_key] ?? $aiol_key); ?>
                        <?php if ($aiol_dim['detail'] !== '') : ?>
                            <span class="aiol-hint" style="display:block"><?php echo esc_html($aiol_dim['detail']); ?></span>
                        <?php endif; ?>
                    </dt>
                    <dd>
                        <?php printf(
                            '<span class="aiol-pill aiol-pill--%s">%s<span>%s</span></span>',
                            esc_attr($aiol_variant),
                            aiol_icon($aiol_icon), // phpcs:ignore WordPress.Security.EscapeOutput
                            esc_html($aiol_word)
                        ); ?>
                    </dd>
                </div>
            <?php endforeach; ?>
        </dl>
        <p class="aiol-hint">
            <?php esc_html_e(
                'Dimensions shown as "Not determined" are measured in Cloud Core or in a later phase — this adapter cannot see them, so it does not guess.',
                'ai-operating-layer'
            ); ?>
        </p>
    </section>
</div>

<h2 id="aiol-actors-heading"><?php esc_html_e('Observed access', 'ai-operating-layer'); ?></h2>

<?php if ($aiol_actor_summary === []) : ?>
    <div class="aiol-empty">
        <h3><?php esc_html_e('No machine access observed yet', 'ai-operating-layer'); ?></h3>
        <p><?php esc_html_e(
            'Crawlers and AI clients that visit this site will be listed here. Ordinary human visits are deliberately not logged.',
            'ai-operating-layer'
        ); ?></p>
    </div>
<?php else : ?>
    <div class="aiol-card">
        <dl class="aiol-status-list">
            <?php foreach ($aiol_actor_summary as $aiol_type => $aiol_count) : ?>
                <div>
                    <dt><?php echo esc_html(AIOL_Actors::type_label((string) $aiol_type)); ?></dt>
                    <dd><?php echo esc_html(number_format_i18n((int) $aiol_count)); ?></dd>
                </div>
            <?php endforeach; ?>
        </dl>
        <p class="aiol-hint">
            <?php esc_html_e(
                'Identified from the User-Agent header, which any client can set. These are self-reported claims, not verified identities — and no IP addresses are stored.',
                'ai-operating-layer'
            ); ?>
        </p>
    </div>
<?php endif; ?>
