<?php
/**
 * DFW Forms uninstall — remove plugin options.
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
    exit;
}

delete_option( 'dfw_forms_server_url' );
