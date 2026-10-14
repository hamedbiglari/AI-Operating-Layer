<?php
/**
 * Per-post mapping meta box.
 *
 * Deliberately minimal: one identifier and one type. The plugin never infers
 * the Core object from a title or slug — a wrong inference would attach one
 * product's evidence to another, which is exactly the class of error the
 * whole evidence-scope design exists to prevent.
 *
 * @var WP_Post $post
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

$aiol_object_id   = AIOL_Mappings::object_id((int) $post->ID);
$aiol_object_type = AIOL_Mappings::object_type((int) $post->ID);
$aiol_state       = AIOL_Mappings::state((int) $post->ID);
$aiol_state_error = AIOL_Mappings::error((int) $post->ID);

$aiol_state_labels = [
    'not_configured' => __('Not linked', 'ai-operating-layer'),
    'pending'        => __('Will sync on save', 'ai-operating-layer'),
    'synced'         => __('Synced with Cloud Core', 'ai-operating-layer'),
    'failed'         => __('Sync failed', 'ai-operating-layer'),
];
?>
<div class="aiol-wrap">
    <p style="margin-top:0">
        <strong><?php esc_html_e('Status:', 'ai-operating-layer'); ?></strong>
        <?php echo esc_html($aiol_state_labels[$aiol_state] ?? $aiol_state); ?>
    </p>

    <?php if ($aiol_state === 'failed' && $aiol_state_error !== '') : ?>
        <p class="aiol-error-text" role="alert"><span><?php echo esc_html($aiol_state_error); ?></span></p>
    <?php endif; ?>

    <p class="aiol-field">
        <label for="aiol_object_type"><?php esc_html_e('Cloud Core object type', 'ai-operating-layer'); ?></label>
        <select id="aiol_object_type" name="aiol_object_type" style="width:100%">
            <?php foreach (AIOL_Mappings::allowed_object_types() as $aiol_type) : ?>
                <option value="<?php echo esc_attr($aiol_type); ?>" <?php selected($aiol_object_type, $aiol_type); ?>>
                    <?php echo esc_html($aiol_type === 'product'
                        ? __('Product', 'ai-operating-layer')
                        : __('Knowledge object', 'ai-operating-layer')); ?>
                </option>
            <?php endforeach; ?>
        </select>
    </p>

    <p class="aiol-field">
        <label for="aiol_object_id"><?php esc_html_e('Cloud Core object ID', 'ai-operating-layer'); ?></label>
        <input type="text" id="aiol_object_id" name="aiol_object_id" style="width:100%"
               aria-describedby="aiol_object_id_hint"
               value="<?php echo esc_attr($aiol_object_id); ?>">
        <span class="aiol-hint" id="aiol_object_id_hint">
            <?php esc_html_e('Copy the ID from Cloud Core. Leave empty to unlink this post. Cloud Core remains the source of truth for its content.', 'ai-operating-layer'); ?>
        </span>
    </p>
</div>
