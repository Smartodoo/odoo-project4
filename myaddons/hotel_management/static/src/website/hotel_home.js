/*
 * Page d'accueil de l'auberge : animations.
 *  - apparition progressive des blocs au défilement ;
 *  - inclinaison 3D + reflet lumineux des cartes « types de chambre » au survol.
 * Sans JavaScript (ou avec « réduire les animations »), tout reste visible et statique.
 */
(function () {
    'use strict';

    const REVEAL_SELECTOR = [
        '.ah_head', '.ah_value', '.ah_gallery', '.ah_offer', '.ah_type_cell',
        '.ah_room', '.ah_step', '.ah_amenity', '.ah_cta', '.ah_showcase_card',
    ].join(', ');

    function setupReveal(root) {
        if (!('IntersectionObserver' in window)) {
            return;
        }
        // Les blocs déjà visibles à l'ouverture ne sont pas animés (pas de clignotement)
        const viewportBottom = window.innerHeight;
        const items = [...root.querySelectorAll(REVEAL_SELECTOR)]
            .filter((el) => el.getBoundingClientRect().top > viewportBottom);

        items.forEach((el) => {
            const siblings = [...el.parentElement.children].filter((sib) => sib.matches(REVEAL_SELECTOR));
            const rank = Math.max(siblings.indexOf(el), 0) % 4;
            el.style.setProperty('--ah-delay', `${rank * 0.09}s`);
            el.setAttribute('data-ah-reveal', '');
        });
        root.classList.add('ah_js');

        const cleanUp = (el) => {
            // Rend la main aux effets de survol propres à chaque bloc
            el.removeAttribute('data-ah-reveal');
            el.classList.remove('is-in');
            el.style.removeProperty('--ah-delay');
        };
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }
                const el = entry.target;
                observer.unobserve(el);
                el.classList.add('is-in');
                el.addEventListener('transitionend', () => cleanUp(el), { once: true });
                setTimeout(() => cleanUp(el), 1600);
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
        items.forEach((el) => observer.observe(el));
    }

    function setupTilt(root) {
        if (!window.matchMedia('(hover: hover)').matches) {
            return;
        }
        root.querySelectorAll('.ah_type_card').forEach((card) => {
            card.addEventListener('mousemove', (ev) => {
                const rect = card.getBoundingClientRect();
                const x = (ev.clientX - rect.left) / rect.width;
                const y = (ev.clientY - rect.top) / rect.height;
                card.style.setProperty('--rx', `${(0.5 - y) * 7}deg`);
                card.style.setProperty('--ry', `${(x - 0.5) * 9}deg`);
                card.style.setProperty('--mx', `${x * 100}%`);
                card.style.setProperty('--my', `${y * 100}%`);
            });
            card.addEventListener('mouseleave', () => {
                card.style.setProperty('--rx', '0deg');
                card.style.setProperty('--ry', '0deg');
            });
        });
    }

    function init() {
        const root = document.querySelector('.o_auberge_home');
        if (!root || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            return;
        }
        setupReveal(root);
        setupTilt(root);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
