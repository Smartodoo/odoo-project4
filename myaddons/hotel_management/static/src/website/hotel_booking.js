/*
 * Fiche chambre du site : quand le client change ses dates (ou le nombre de
 * personnes), la page est rechargée pour ne proposer que les lits libres sur
 * la nouvelle période. Sans JavaScript, la vérification se fait à l'envoi.
 */
(function () {
    'use strict';

    function setup(form) {
        const field = (name) => form.querySelector(`[name="${name}"]`);
        const checkin = field('checkin');
        const checkout = field('checkout');
        if (!checkin || !checkout) {
            return;
        }
        const initial = `${checkin.value}|${checkout.value}`;
        const reload = () => {
            const ci = checkin.value;
            const co = checkout.value;
            if (!ci || !co || co <= ci || `${ci}|${co}` === initial) {
                return;
            }
            const params = new URLSearchParams(window.location.search);
            params.set('checkin', ci);
            params.set('checkout', co);
            const guests = field('guests');
            if (guests && guests.value) {
                params.set('guests', guests.value);
            }
            const type = form.querySelector('[name="booking_type"]:checked')
                || form.querySelector('input[type="hidden"][name="booking_type"]');
            if (type && type.value) {
                params.set('booking_type', type.value);
            }
            window.location.assign(`${window.location.pathname}?${params.toString()}#o_hotel_booking`);
        };
        checkin.addEventListener('change', reload);
        checkout.addEventListener('change', reload);
    }

    function init() {
        document.querySelectorAll('form.o_hotel_booking_form').forEach(setup);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
