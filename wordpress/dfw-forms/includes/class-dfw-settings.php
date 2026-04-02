<?php
/**
 * DFW Forms settings page (Settings > DFW Forms).
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class DFW_Settings {

    /**
     * Register plugin settings.
     */
    public static function register() {
        register_setting( 'dfw_forms_settings', 'dfw_forms_server_url', array(
            'type'              => 'string',
            'sanitize_callback' => array( __CLASS__, 'sanitize_server_url' ),
            'default'           => '',
        ) );

        add_settings_section(
            'dfw_forms_main',
            __( 'Server Configuration', 'dfw-forms' ),
            array( __CLASS__, 'section_description' ),
            'dfw-forms'
        );

        add_settings_field(
            'dfw_forms_server_url',
            __( 'DFW Server URL', 'dfw-forms' ),
            array( __CLASS__, 'render_server_url_field' ),
            'dfw-forms',
            'dfw_forms_main'
        );
    }

    /**
     * Sanitize the server URL: validate as URL and strip trailing slashes.
     */
    public static function sanitize_server_url( $value ) {
        $value = trim( $value );
        if ( empty( $value ) ) {
            return '';
        }
        $url = esc_url_raw( rtrim( $value, '/' ) );
        if ( empty( $url ) ) {
            add_settings_error(
                'dfw_forms_server_url',
                'invalid_url',
                __( 'Please enter a valid URL for the DFW server.', 'dfw-forms' )
            );
            return get_option( 'dfw_forms_server_url', '' );
        }
        return $url;
    }

    /**
     * Add the settings page under Settings menu.
     */
    public static function add_page() {
        add_options_page(
            __( 'DFW Forms Settings', 'dfw-forms' ),
            __( 'DFW Forms', 'dfw-forms' ),
            'manage_options',
            'dfw-forms',
            array( __CLASS__, 'render_page' )
        );
    }

    /**
     * Section description text.
     */
    public static function section_description() {
        echo '<p>' . esc_html__(
            'Enter the base URL of your Django Forms Workflows server (e.g., https://forms.example.com). This is used to load form embeds on your site.',
            'dfw-forms'
        ) . '</p>';
    }

    /**
     * Render the server URL input field.
     */
    public static function render_server_url_field() {
        $value = get_option( 'dfw_forms_server_url', '' );
        printf(
            '<input type="url" id="dfw_forms_server_url" name="dfw_forms_server_url" value="%s" class="regular-text" placeholder="https://forms.example.com" />',
            esc_attr( $value )
        );
        echo '<p class="description">'
            . esc_html__( 'The base URL of your DFW server, without a trailing slash.', 'dfw-forms' )
            . '</p>';
        echo '<p style="margin-top:8px;">';
        echo '<button type="button" id="dfw-test-connection" class="button button-secondary">'
            . esc_html__( 'Test Connection', 'dfw-forms' )
            . '</button> ';
        echo '<span id="dfw-test-result" style="margin-left:8px;"></span>';
        echo '</p>';
    }

    /**
     * Render the full settings page.
     */
    public static function render_page() {
        if ( ! current_user_can( 'manage_options' ) ) {
            return;
        }
        ?>
        <div class="wrap">
            <h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
            <form action="options.php" method="post">
                <?php
                settings_fields( 'dfw_forms_settings' );
                do_settings_sections( 'dfw-forms' );
                submit_button();
                ?>
            </form>

            <hr>
            <h2><?php esc_html_e( 'Usage', 'dfw-forms' ); ?></h2>

            <h3><?php esc_html_e( 'Shortcode', 'dfw-forms' ); ?></h3>
            <p><?php esc_html_e( 'Add a form to any page or post using the shortcode:', 'dfw-forms' ); ?></p>
            <pre><code>[dfw_form slug="your-form-slug"]</code></pre>

            <p><?php esc_html_e( 'Available attributes:', 'dfw-forms' ); ?></p>
            <table class="widefat fixed" style="max-width:700px;">
                <thead>
                    <tr>
                        <th><?php esc_html_e( 'Attribute', 'dfw-forms' ); ?></th>
                        <th><?php esc_html_e( 'Default', 'dfw-forms' ); ?></th>
                        <th><?php esc_html_e( 'Description', 'dfw-forms' ); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td><code>slug</code></td><td>&mdash;</td><td><?php esc_html_e( 'Form slug (required)', 'dfw-forms' ); ?></td></tr>
                    <tr><td><code>server</code></td><td><?php esc_html_e( 'Settings value', 'dfw-forms' ); ?></td><td><?php esc_html_e( 'Override the DFW server URL', 'dfw-forms' ); ?></td></tr>
                    <tr><td><code>theme</code></td><td>&mdash;</td><td><?php esc_html_e( '"light" or "dark"', 'dfw-forms' ); ?></td></tr>
                    <tr><td><code>accent_color</code></td><td>&mdash;</td><td><?php esc_html_e( 'Hex color for buttons (e.g., #ff6600)', 'dfw-forms' ); ?></td></tr>
                    <tr><td><code>min_height</code></td><td>300</td><td><?php esc_html_e( 'Minimum iframe height in pixels', 'dfw-forms' ); ?></td></tr>
                    <tr><td><code>loading_text</code></td><td>Loading form...</td><td><?php esc_html_e( 'Text shown while form loads', 'dfw-forms' ); ?></td></tr>
                    <tr><td><code>mode</code></td><td>js</td><td><?php esc_html_e( '"js" (auto-resize) or "iframe" (plain iframe fallback)', 'dfw-forms' ); ?></td></tr>
                </tbody>
            </table>

            <h3><?php esc_html_e( 'Gutenberg Block', 'dfw-forms' ); ?></h3>
            <p><?php esc_html_e( 'Search for "DFW Form" in the block inserter to add a form with a visual editor.', 'dfw-forms' ); ?></p>
        </div>
        <?php
    }
}
