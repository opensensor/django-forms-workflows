/**
 * Stripe Payment Element integration.
 *
 * Expects global variables set by the template:
 *   PAYMENT_CONFIG = { provider, publishable_key, client_secret }
 *   CONFIRM_URL    = "/forms/payments/<id>/confirm/"
 *   CSRF_TOKEN     = "..."
 */
(function () {
    'use strict';

    if (!window.PAYMENT_CONFIG || PAYMENT_CONFIG.provider !== 'stripe') {
        return; // Not a Stripe payment page
    }

    var publishableKey = PAYMENT_CONFIG.publishable_key;
    var clientSecret = PAYMENT_CONFIG.client_secret;

    if (!publishableKey || !clientSecret) {
        document.getElementById('payment-message').textContent =
            'Payment configuration is incomplete. Please contact support.';
        document.getElementById('payment-message').classList.add('visible');
        return;
    }

    // Load Stripe.js dynamically
    var script = document.createElement('script');
    script.src = 'https://js.stripe.com/v3/';
    script.async = true;
    script.onload = initStripe;
    document.head.appendChild(script);

    function initStripe() {
        var stripe = Stripe(publishableKey);
        var elements = stripe.elements({ clientSecret: clientSecret });

        var paymentElement = elements.create('payment');
        paymentElement.mount('#payment-element');

        var submitBtn = document.getElementById('payment-submit');
        var btnText = document.getElementById('button-text');
        var spinner = document.getElementById('spinner');
        var messageEl = document.getElementById('payment-message');

        submitBtn.addEventListener('click', async function (e) {
            e.preventDefault();
            setLoading(true);

            var result = await stripe.confirmPayment({
                elements: elements,
                redirect: 'if_required'
            });

            if (result.error) {
                showMessage(result.error.message);
                setLoading(false);
                return;
            }

            // Payment succeeded client-side — verify server-side
            try {
                var resp = await fetch(CONFIRM_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': CSRF_TOKEN
                    },
                    body: JSON.stringify({
                        payment_intent_id: result.paymentIntent.id
                    })
                });

                var data = await resp.json();
                if (data.success && data.redirect_url) {
                    window.location.href = data.redirect_url;
                } else {
                    showMessage(data.error || 'Payment verification failed.');
                    setLoading(false);
                }
            } catch (err) {
                showMessage('Network error. Please try again.');
                setLoading(false);
            }
        });

        function setLoading(loading) {
            submitBtn.disabled = loading;
            spinner.style.display = loading ? 'inline-block' : 'none';
            btnText.textContent = loading ? 'Processing...' : 'Pay Now';
        }

        function showMessage(msg) {
            messageEl.textContent = msg;
            messageEl.classList.add('visible');
        }
    }
})();
