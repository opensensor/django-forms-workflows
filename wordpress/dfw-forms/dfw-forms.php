<?php
/**
 * Plugin Name: DFW Forms
 * Plugin URI:  https://github.com/opensensor/django-forms-workflows
 * Description: Embed Django Forms Workflows forms on your WordPress site via shortcode or Gutenberg block.
 * Version:     1.0.0
 * Author:      Matt Davis
 * Author URI:  https://opensensor.io
 * License:     LGPL-3.0-only
 * Text Domain: dfw-forms
 * Domain Path: /languages
 * Requires at least: 6.0
 * Requires PHP: 7.4
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'DFW_FORMS_VERSION', '1.0.0' );
define( 'DFW_FORMS_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'DFW_FORMS_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

// Load plugin classes.
require_once DFW_FORMS_PLUGIN_DIR . 'includes/class-dfw-render.php';
require_once DFW_FORMS_PLUGIN_DIR . 'includes/class-dfw-settings.php';
require_once DFW_FORMS_PLUGIN_DIR . 'includes/class-dfw-shortcode.php';

/**
 * Set default options on activation.
 */
function dfw_forms_activate() {
    add_option( 'dfw_forms_server_url', '' );
}
register_activation_hook( __FILE__, 'dfw_forms_activate' );

/**
 * Initialize the plugin: load textdomain, register shortcode, register block.
 */
function dfw_forms_init() {
    load_plugin_textdomain( 'dfw-forms', false, dirname( plugin_basename( __FILE__ ) ) . '/languages' );

    DFW_Shortcode::register();

    // Register the Gutenberg block.
    if ( function_exists( 'register_block_type' ) ) {
        register_block_type( DFW_FORMS_PLUGIN_DIR . 'blocks/dfw-form' );
    }
}
add_action( 'init', 'dfw_forms_init' );

/**
 * Register settings page.
 */
add_action( 'admin_menu', array( 'DFW_Settings', 'add_page' ) );
add_action( 'admin_init', array( 'DFW_Settings', 'register' ) );

/**
 * Enqueue admin assets on the settings page.
 */
function dfw_forms_admin_assets( $hook ) {
    if ( 'settings_page_dfw-forms' !== $hook ) {
        return;
    }
    wp_enqueue_style(
        'dfw-forms-admin',
        DFW_FORMS_PLUGIN_URL . 'assets/css/admin.css',
        array(),
        DFW_FORMS_VERSION
    );
    wp_enqueue_script(
        'dfw-forms-admin',
        DFW_FORMS_PLUGIN_URL . 'assets/js/admin.js',
        array(),
        DFW_FORMS_VERSION,
        true
    );
}
add_action( 'admin_enqueue_scripts', 'dfw_forms_admin_assets' );

/**
 * Pass the server URL to the Gutenberg block editor script.
 */
function dfw_forms_enqueue_block_editor_assets() {
    $server_url = esc_url( rtrim( get_option( 'dfw_forms_server_url', '' ), '/' ) );
    wp_add_inline_script(
        'dfw-form-edit-script',
        'window.dfwFormsEditor = ' . wp_json_encode( array( 'serverUrl' => $server_url ) ) . ';',
        'before'
    );
}
add_action( 'enqueue_block_editor_assets', 'dfw_forms_enqueue_block_editor_assets' );
