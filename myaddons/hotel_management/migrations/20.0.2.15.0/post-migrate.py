from odoo import Command, SUPERUSER_ID, api


def migrate(cr, version):
    """Canal « Réservations en ligne » (donnée noupdate) : la Réception devient
    membre automatique ; les utilisateurs Réception existants sont ajoutés."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    channel = env.ref('hotel_management.channel_online_reservations', raise_if_not_found=False)
    group = env.ref('hotel_management.group_hotel_user', raise_if_not_found=False)
    if channel and group and group not in channel.group_ids:
        channel.write({'group_ids': [Command.link(group.id)]})
