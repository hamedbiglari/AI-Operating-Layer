<?php
/**
 * Destroys every trace of the adapter's local state, including the
 * credential. Uninstall - not deactivation - is the point at which secrets
 * are removed, so that toggling the plugin off does not force a merchant to
 * re-provision.
 *
 * Mappings are NOT deleted from Cloud Core here: they are Core's rows, in
 * Core's tenant, and an uninstall of one WordPress site has no authority to
 * mutate them. A merchant who wants them gone revokes the installation in
 * Core.
 */

declare(strict_types=1);

if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

require_once plugin_dir_path(__FILE__) . 'includes/class-aiol-credentials.php';
require_once plugin_dir_path(__FILE__) . 'includes/class-aiol-cache.php';

delete_option(AIOL_Credentials::OPTION_ENDPOINT);
delete_option(AIOL_Credentials::OPTION_TOKEN);
delete_option(AIOL_Credentials::OPTION_IDENTITY);
delete_option('aiol_last_sync');
delete_option('aiol_log');
delete_option('aiol_actor_log');
delete_option('aiol_deferred_offer_sync');
delete_option('aiol_settings');
delete_option('aiol_cache_keys');

// Legacy AI Access Toolkit leftovers: absorbing the plugin means a site
// upgrading from it is not left with orphaned rows.
delete_option('aat_settings');
delete_option('aat_bot_visit_log');
delete_transient('aat_llms_txt_cache');

AIOL_Cache::flush_all();
