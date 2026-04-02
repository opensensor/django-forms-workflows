/**
 * DFW Form — Gutenberg block editor component.
 *
 * Uses wp.element.createElement (no JSX, no build step required).
 */
( function () {
    'use strict';

    var el            = wp.element.createElement;
    var useState      = wp.element.useState;
    var Fragment      = wp.element.Fragment;
    var __            = wp.i18n.__;
    var InspectorControls = wp.blockEditor.InspectorControls;
    var useBlockProps  = wp.blockEditor.useBlockProps;
    var PanelBody     = wp.components.PanelBody;
    var TextControl   = wp.components.TextControl;
    var SelectControl = wp.components.SelectControl;
    var RangeControl  = wp.components.RangeControl;
    var Button        = wp.components.Button;

    var serverUrl = ( window.dfwFormsEditor && window.dfwFormsEditor.serverUrl ) || '';

    function DFWFormEdit( props ) {
        var attributes    = props.attributes;
        var setAttributes = props.setAttributes;
        var blockProps    = useBlockProps();
        var slug          = attributes.slug || '';
        var theme         = attributes.theme || '';
        var accentColor   = attributes.accentColor || '';
        var minHeight     = attributes.minHeight || 300;
        var mode          = attributes.mode || 'js';

        var slugInput     = useState( slug );
        var tempSlug      = slugInput[0];
        var setTempSlug   = slugInput[1];

        // Placeholder: no slug configured yet.
        if ( ! slug ) {
            return el( 'div', blockProps,
                el( 'div', { className: 'dfw-block-placeholder' },
                    el( 'span', { className: 'dashicons dashicons-feedback' } ),
                    el( 'h4', null, __( 'DFW Form', 'dfw-forms' ) ),
                    el( 'p', null, __( 'Enter the form slug to embed a Django Forms Workflows form.', 'dfw-forms' ) ),
                    el( TextControl, {
                        value: tempSlug,
                        onChange: setTempSlug,
                        placeholder: __( 'e.g., contact-us', 'dfw-forms' ),
                    } ),
                    el( Button, {
                        variant: 'primary',
                        disabled: ! tempSlug.trim(),
                        onClick: function () {
                            setAttributes( { slug: tempSlug.trim() } );
                        },
                    }, __( 'Embed Form', 'dfw-forms' ) )
                )
            );
        }

        // Build preview iframe URL.
        var previewUrl = '';
        if ( serverUrl ) {
            previewUrl = serverUrl + '/forms/' + encodeURIComponent( slug ) + '/embed/';
            var params = [];
            if ( theme ) params.push( 'theme=' + encodeURIComponent( theme ) );
            if ( accentColor ) params.push( 'accent_color=' + encodeURIComponent( accentColor ) );
            if ( params.length ) previewUrl += '?' + params.join( '&' );
        }

        // Configured: show preview + inspector controls.
        return el( Fragment, null,
            el( InspectorControls, null,
                el( PanelBody, { title: __( 'Form Settings', 'dfw-forms' ), initialOpen: true },
                    el( TextControl, {
                        label: __( 'Form Slug', 'dfw-forms' ),
                        value: slug,
                        onChange: function ( val ) { setAttributes( { slug: val } ); },
                        help: __( 'The slug of the form on your DFW server.', 'dfw-forms' ),
                    } ),
                    el( SelectControl, {
                        label: __( 'Theme', 'dfw-forms' ),
                        value: theme,
                        options: [
                            { label: __( 'Default', 'dfw-forms' ), value: '' },
                            { label: __( 'Light', 'dfw-forms' ),   value: 'light' },
                            { label: __( 'Dark', 'dfw-forms' ),    value: 'dark' },
                        ],
                        onChange: function ( val ) { setAttributes( { theme: val } ); },
                    } ),
                    el( TextControl, {
                        label: __( 'Accent Color', 'dfw-forms' ),
                        value: accentColor,
                        onChange: function ( val ) { setAttributes( { accentColor: val } ); },
                        placeholder: '#ff6600',
                        help: __( 'Hex color for primary buttons.', 'dfw-forms' ),
                    } ),
                    el( RangeControl, {
                        label: __( 'Minimum Height (px)', 'dfw-forms' ),
                        value: minHeight,
                        onChange: function ( val ) { setAttributes( { minHeight: val } ); },
                        min: 100,
                        max: 1200,
                        step: 50,
                    } ),
                    el( SelectControl, {
                        label: __( 'Embed Mode', 'dfw-forms' ),
                        value: mode,
                        options: [
                            { label: __( 'JS (auto-resize)', 'dfw-forms' ),   value: 'js' },
                            { label: __( 'iframe (plain fallback)', 'dfw-forms' ), value: 'iframe' },
                        ],
                        onChange: function ( val ) { setAttributes( { mode: val } ); },
                        help: __( 'Use "iframe" for WordPress.com or restricted hosts.', 'dfw-forms' ),
                    } )
                )
            ),
            el( 'div', blockProps,
                el( 'div', { className: 'dfw-block-preview' },
                    el( 'div', { className: 'dfw-block-label' },
                        el( 'span', { className: 'dashicons dashicons-feedback' } ),
                        __( 'DFW Form:', 'dfw-forms' ) + ' ' + slug
                    ),
                    previewUrl
                        ? el( Fragment, null,
                            el( 'iframe', {
                                src: previewUrl,
                                style: { minHeight: minHeight + 'px' },
                                title: slug,
                                loading: 'lazy',
                            } ),
                            el( 'div', { className: 'dfw-block-preview-overlay' } )
                        )
                        : el( 'p', { style: { padding: '24px', textAlign: 'center', color: '#999' } },
                            __( 'Configure the DFW server URL in Settings > DFW Forms to see a preview.', 'dfw-forms' )
                        )
                )
            )
        );
    }

    wp.blocks.registerBlockType( 'dfw/form', {
        edit: DFWFormEdit,
        save: function () { return null; },
    } );
} )();
