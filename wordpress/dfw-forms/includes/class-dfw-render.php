<?php
/**
 * Shared rendering logic for DFW form embeds.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class DFW_Render {

    /**
     * Render a DFW form embed.
     *
     * @param array $args {
     *     @type string $slug         Form slug (required).
     *     @type string $server       DFW server URL.
     *     @type string $theme        'light' or 'dark'.
     *     @type string $accent_color Hex color.
     *     @type int    $min_height   Minimum iframe height in px.
     *     @type string $loading_text Loading indicator text.
     *     @type string $on_submit    JS callback function name.
     *     @type string $on_load      JS callback function name.
     *     @type string $mode         'js' (default) or 'iframe'.
     * }
     * @return string HTML output.
     */
    public static function render( $args ) {
        $defaults = array(
            'slug'         => '',
            'server'       => '',
            'theme'        => '',
            'accent_color' => '',
            'min_height'   => 300,
            'loading_text' => __( 'Loading form...', 'dfw-forms' ),
            'on_submit'    => '',
            'on_load'      => '',
            'mode'         => 'js',
        );

        $args = wp_parse_args( $args, $defaults );

        if ( empty( $args['slug'] ) || empty( $args['server'] ) ) {
            if ( current_user_can( 'edit_posts' ) ) {
                return '<p style="color:#dc3545;">'
                    . esc_html__( 'DFW Form: Please configure the form slug and server URL.', 'dfw-forms' )
                    . '</p>';
            }
            return '';
        }

        $server = esc_url( rtrim( $args['server'], '/' ) );
        $slug   = sanitize_title( $args['slug'] );

        if ( 'iframe' === $args['mode'] ) {
            return self::render_iframe( $slug, $server, $args );
        }

        return self::render_js( $slug, $server, $args );
    }

    /**
     * JS embed mode — outputs a div + script tag using dfw-embed.js.
     */
    private static function render_js( $slug, $server, $args ) {
        $unique_id = wp_unique_id( 'dfw-form-' );

        $data_attrs = sprintf(
            ' data-form="%s" data-server="%s" data-target="#%s"',
            esc_attr( $slug ),
            esc_attr( $server ),
            esc_attr( $unique_id )
        );

        if ( ! empty( $args['theme'] ) ) {
            $data_attrs .= sprintf( ' data-theme="%s"', esc_attr( $args['theme'] ) );
        }
        if ( ! empty( $args['accent_color'] ) ) {
            $data_attrs .= sprintf( ' data-accent-color="%s"', esc_attr( $args['accent_color'] ) );
        }
        if ( $args['min_height'] > 0 ) {
            $data_attrs .= sprintf( ' data-min-height="%d"', (int) $args['min_height'] );
        }
        if ( ! empty( $args['loading_text'] ) ) {
            $data_attrs .= sprintf( ' data-loading-text="%s"', esc_attr( $args['loading_text'] ) );
        }
        if ( ! empty( $args['on_submit'] ) ) {
            $data_attrs .= sprintf( ' data-on-submit="%s"', esc_attr( $args['on_submit'] ) );
        }
        if ( ! empty( $args['on_load'] ) ) {
            $data_attrs .= sprintf( ' data-on-load="%s"', esc_attr( $args['on_load'] ) );
        }

        $script_url = $server . '/static/django_forms_workflows/js/dfw-embed.js';

        return sprintf(
            '<div id="%s" class="dfw-form-wrapper"></div>' . "\n"
            . '<script src="%s"%s></script>',
            esc_attr( $unique_id ),
            esc_url( $script_url ),
            $data_attrs
        );
    }

    /**
     * iframe fallback mode — outputs a plain iframe tag.
     */
    private static function render_iframe( $slug, $server, $args ) {
        $embed_url = $server . '/forms/' . rawurlencode( $slug ) . '/embed/';

        $params = array();
        if ( ! empty( $args['theme'] ) ) {
            $params['theme'] = $args['theme'];
        }
        if ( ! empty( $args['accent_color'] ) ) {
            $params['accent_color'] = $args['accent_color'];
        }
        if ( $params ) {
            $embed_url .= '?' . http_build_query( $params );
        }

        $min_height = max( (int) $args['min_height'], 100 );

        return sprintf(
            '<iframe src="%s" style="width:100%%;border:none;min-height:%dpx;" title="%s" loading="lazy" allowtransparency="true"></iframe>',
            esc_url( $embed_url ),
            $min_height,
            /* translators: %s: form slug */
            esc_attr( sprintf( __( 'Form: %s', 'dfw-forms' ), $slug ) )
        );
    }
}
