<?php
/**
 * DFW Form block — server-side render.
 *
 * @var array    $attributes Block attributes.
 * @var string   $content    Block inner content (empty for dynamic blocks).
 * @var WP_Block $block      Block instance.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

$slug         = sanitize_title( $attributes['slug'] ?? '' );
$theme        = in_array( $attributes['theme'] ?? '', array( 'light', 'dark' ), true ) ? $attributes['theme'] : '';
$accent_color = preg_match( '/^#[0-9a-fA-F]{3,8}$/', $attributes['accentColor'] ?? '' ) ? $attributes['accentColor'] : '';
$min_height   = absint( $attributes['minHeight'] ?? 300 );
$mode         = in_array( $attributes['mode'] ?? 'js', array( 'js', 'iframe' ), true ) ? $attributes['mode'] : 'js';
$server       = esc_url( rtrim( get_option( 'dfw_forms_server_url', '' ), '/' ) );

echo DFW_Render::render( array(
    'slug'         => $slug,
    'server'       => $server,
    'theme'        => $theme,
    'accent_color' => $accent_color,
    'min_height'   => $min_height,
    'mode'         => $mode,
) );
