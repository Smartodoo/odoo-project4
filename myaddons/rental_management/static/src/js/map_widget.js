odoo.define('rental_management.map_widget', function(require) {
    "use strict";

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    var MapWidget = AbstractField.extend({
        template: 'MapWidget',
        events: {
            'click .refresh-map': '_refreshMap',
        },
        init: function(parent, name, record, options) {
            this._super(parent, name, record, options);
            this.map = null;
        },
        _render: function() {
            this._loadMap();
        },
        _loadMap: function() {
            if (this.map) this.map.remove();
            // Coordonnées fictives (Casablanca)
            this.map = L.map(this.$el.find('.map-container')[0]).setView([33.5731, -7.5898], 12);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> & CartoDB'
            }).addTo(this.map);
            // Récupérer les appartements avec coordonnées
            this._rpc({
                model: 'property.apartment',
                method: 'get_map_data',
            }).then(function(data) {
                for (var i = 0; i < data.length; i++) {
                    var apt = data[i];
                    var marker = L.marker([apt.lat, apt.lng]).addTo(this.map);
                    marker.bindPopup("<b>" + apt.name + "</b><br>" + apt.address_full + "<br>Prix mensuel: " + apt.price_monthly + " DH");
                }
            }.bind(this));
        },
        _refreshMap: function() {
            this._loadMap();
        }
    });
    fieldRegistry.add('map_widget', MapWidget);
});