<?php
/**
 * [dfw_form] shortcode handler.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class DFW_Shortcode {

    /**
     * Register the shortcode.
     */
    public static function register() {
        add_shortcode( 'dfw_form', array( __CLASS__, 'handle' ) );
    }

    /**
     * Render the shortcode.
     *
     * @param array $atts Shortcode attributes.
     * @return string HTML output.
     */
    public static function handle( $atts ) {
        $atts = shortcode_atts( array(
            'slug'         => '',
            'server'       => '',
            'theme'        => '',
            'accent_color' => '',
            'min_height'   => '300',
            'loading_text' => '',
            'on_submit'    => '',
            'on_load'      => '',
            'mode'         => 'js',
        ), $atts, 'dfw_form' );

        // Use the global server URL if not overridden.
        if ( empty( $atts['server'] ) ) {
            $atts['server'] = get_option( 'dfw_forms_server_url', '' );
        }

        // Sanitize all inputs.
        $args = array(
            'slug'         => sanitize_title( $atts['slug'] ),
            'server'       => esc_url( rtrim( $atts['server'], '/' ) ),
            'theme'        => in_array( $atts['theme'], array( 'light', 'dark' ), true ) ? $atts['theme'] : '',
            'accent_color' => preg_match( '/^#[0-9a-fA-F]{3,8}$/', $atts['accent_color'] ) ? $atts['accent_color'] : '',
            'min_height'   => absint( $atts['min_height'] ),
            'loading_text' => sanitize_text_field( $atts['loading_text'] ),
            'on_submit'    => self::sanitize_callback_name( $atts['on_submit'] ),
            'on_load'      => self::sanitize_callback_name( $atts['on_load'] ),
            'mode'         => in_array( $atts['mode'], array( 'js', 'iframe' ), true ) ? $atts['mode'] : 'js',
        );

        return DFW_Render::render( $args );
    }

    /**
     * Sanitize a JavaScript callback function name.
     * Only allows valid JS identifiers (letters, digits, underscores, dots, dollar signs).
     *
     * @param string $name Callback function name.
     * @return string Sanitized name, or empty string if invalid.
     */
    private static function sanitize_callback_name( $name ) {
        $name = trim( $name );
        if ( empty( $name ) ) {
            return '';
        }
        if ( preg_match( '/^[a-zA-Z_$][a-zA-Z0-9_$.]*$/', $name ) ) {
            return $name;
        }
        return '';
    }
}
