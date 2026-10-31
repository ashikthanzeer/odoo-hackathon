# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.constrains('login', 'email')
    def _check_unique_account_email(self):
        for user in self:
            check_val = (user.email or user.login or '').strip().lower()
            if check_val and '@' in check_val:
                domain = [
                    ('id', '!=', user.id),
                    ('active', 'in', [True, False]),
                    '|',
                    ('login', '=ilike', check_val),
                    ('email', '=ilike', check_val)
                ]
                duplicate = self.sudo().search(domain, limit=1)
                if duplicate:
                    raise ValidationError(_(
                        'The email address "%s" is already registered to user "%s". Each account must have a unique email address.'
                    ) % (check_val, duplicate.login))

    def _check_password_complexity(self, password):
        """
        Validates Brightloop Software password policy:
        - Must be more than eight characters (> 8 chars, i.e. len >= 9)
        - Must contain at least one uppercase letter
        - Must contain at least one lowercase letter
        - Must contain at least one special character
        """
        if not password:
            return
        if len(password) <= 8:
            raise ValidationError(_(
                'Password must be more than 8 characters in length. Current length is %d.'
            ) % len(password))
        if not re.search(r'[A-Z]', password):
            raise ValidationError(_(
                'Password must contain at least one uppercase letter (A-Z).'
            ))
        if not re.search(r'[a-z]', password):
            raise ValidationError(_(
                'Password must contain at least one lowercase letter (a-z).'
            ))
        if not re.search(r'[^a-zA-Z0-9]', password):
            raise ValidationError(_(
                'Password must contain at least one special character (e.g. !@#$%^&*).'
            ))

    def _set_password(self):
        """Hook called when password is set via user form or signup."""
        for user in self:
            if user.password:
                self._check_password_complexity(user.password)
        return super(ResUsers, self)._set_password()

    @api.model_create_multi
    def create(self, vals_list):
        current_user = self.env.user
        staff_group = self.env.ref('brightloop_subscription.group_subscription_user', raise_if_not_found=False)
        manager_group = self.env.ref('brightloop_subscription.group_subscription_manager', raise_if_not_found=False)

        for vals in vals_list:
            # Check password if provided in vals
            raw_password = vals.get('password')
            if raw_password:
                self._check_password_complexity(raw_password)

            # Restrict adding new staff members to Administrators only
            groups_val = vals.get('groups_id') or []
            is_adding_staff = False
            if staff_group or manager_group:
                staff_ids = {g.id for g in (staff_group, manager_group) if g}
                for command in groups_val:
                    if isinstance(command, (list, tuple)) and len(command) >= 2:
                        cmd = command[0]
                        if cmd == 4 and command[1] in staff_ids:
                            is_adding_staff = True
                        elif cmd == 6 and any(gid in staff_ids for gid in command[2]):
                            is_adding_staff = True

            if is_adding_staff and not (current_user.has_group('brightloop_subscription.group_subscription_manager') or self.env.is_superuser()):
                raise AccessError(_(
                    'Access Denied: Only a Subscription Administrator can add a new member of staff.'
                ))

        return super(ResUsers, self).create(vals_list)

    def write(self, vals):
        if vals.get('password'):
            self._check_password_complexity(vals['password'])

        # Check if updating groups to add staff role
        if 'groups_id' in vals and not (self.env.user.has_group('brightloop_subscription.group_subscription_manager') or self.env.is_superuser()):
            staff_group = self.env.ref('brightloop_subscription.group_subscription_user', raise_if_not_found=False)
            manager_group = self.env.ref('brightloop_subscription.group_subscription_manager', raise_if_not_found=False)
            staff_ids = {g.id for g in (staff_group, manager_group) if g}
            for command in vals['groups_id']:
                if isinstance(command, (list, tuple)) and len(command) >= 2:
                    cmd = command[0]
                    if (cmd == 4 and command[1] in staff_ids) or (cmd == 6 and any(gid in staff_ids for gid in command[2])):
                        raise AccessError(_(
                            'Access Denied: Only a Subscription Administrator can modify staff privileges or add staff members.'
                        ))

        return super(ResUsers, self).write(vals)
