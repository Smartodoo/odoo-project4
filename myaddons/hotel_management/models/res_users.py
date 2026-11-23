from odoo import models


def _hotel_sync_online_channel(env, users):
    """Retire du canal « Réservations en ligne » les utilisateurs qui n'ont
    plus aucun des accès qui y donnent droit (Réception, Responsable,
    Administrateur). L'ajout est fait par Odoo (groupes du canal)."""
    channel = env.ref('hotel_management.channel_online_reservations',
                      raise_if_not_found=False)
    if not channel or not users:
        return
    channel = channel.sudo()
    allowed = channel.group_ids
    lost = users.sudo().filtered(lambda u: not (u.all_group_ids & allowed))
    members = channel.channel_member_ids.filtered(
        lambda m: m.partner_id in lost.partner_id)
    if members:
        members.unlink()


class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        res = super().write(vals)
        if 'group_ids' in vals:
            _hotel_sync_online_channel(self.env, self)
        return res


class ResGroups(models.Model):
    _inherit = 'res.groups'

    def write(self, vals):
        before = self.sudo().all_user_ids if 'user_ids' in vals else None
        res = super().write(vals)
        if before is not None:
            _hotel_sync_online_channel(self.env, before)
        return res
