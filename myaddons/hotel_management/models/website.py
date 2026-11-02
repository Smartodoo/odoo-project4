import base64

from odoo import api, fields, models, tools


class Website(models.Model):
    _inherit = 'website'

    # Bloc « vitrine » de la page d'accueil, personnalisable depuis Auberge > Configuration
    hotel_home_image = fields.Image(
        string="Photo de l'auberge", max_width=2400, max_height=1600,
        help="Grande photo affichée sous le bandeau de la page d'accueil "
             "(idéalement la façade ou le salon, format paysage 1600×1000 px ou plus). "
             "Sans photo, une illustration de l'auberge est affichée.")
    hotel_home_kicker = fields.Char(string="Sur-titre", translate=True, default="Notre maison")
    hotel_home_title = fields.Char(string="Titre", translate=True, default="Bienvenue à L'Auberge")
    hotel_home_text = fields.Text(
        string="Texte", translate=True,
        default="Une auberge où l'on pose ses valises comme chez soi : chambres privées "
                "ou lits en dortoir, dans un cadre propre, calme et soigné.")
    hotel_home_badge = fields.Char(string="Badge", translate=True, default="Réservation en ligne 24h/24")

    # Galerie de la section « Notre engagement » (à défaut : photos des chambres)
    hotel_gallery_image_1 = fields.Image(string="Grande photo", max_width=1600, max_height=1600)
    hotel_gallery_image_2 = fields.Image(string="Photo en haut à droite", max_width=1200, max_height=1200)
    hotel_gallery_image_3 = fields.Image(string="Photo en bas à droite", max_width=1200, max_height=1200)

    def _hotel_gallery_urls(self):
        """URL des photos de galerie renseignées, dans l'ordre d'affichage."""
        self.ensure_one()
        unique = self.write_date and self.write_date.strftime('%Y%m%d%H%M%S')
        website = self.with_context(bin_size=True)
        return ['/web/image/website/%s/%s?unique=%s' % (self.id, fname, unique)
                for fname in ('hotel_gallery_image_1', 'hotel_gallery_image_2', 'hotel_gallery_image_3')
                if website[fname]]

    @api.model
    def _hotel_set_default_logo(self):
        """Pose le logo de l'auberge sur les sites qui ont encore le logo Odoo par défaut."""
        with tools.file_open('hotel_management/static/src/img/auberge_logo.png', 'rb') as f:
            logo = base64.b64encode(f.read())
        default = self._default_logo()
        for website in self.search([]):
            if not website.logo or website.logo == default:
                website.logo = logo

    @api.model
    def _hotel_setup_homepage(self):
        """En-tête transparent posé sur le bandeau de la page d'accueil, et textes
        par défaut du bloc vitrine pour les sites qui ne les ont pas encore saisis."""
        self.env['website.page'].search([('url', '=', '/')]).write({'header_overlay': True})
        text_fields = ['hotel_home_kicker', 'hotel_home_title', 'hotel_home_text', 'hotel_home_badge']
        defaults = self.default_get(text_fields)
        for website in self.search([]):
            missing = {f: defaults[f] for f in text_fields if not website[f] and defaults.get(f)}
            if missing:
                website.write(missing)
