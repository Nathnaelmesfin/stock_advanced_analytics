from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class StockAnalyticsOpeningBalance(models.Model):
    _name = 'stock.analytics.opening.balance'
    _description = 'Inventory Analytics Opening Balance'
    _order = 'opening_date desc, product_id, location_id'

    product_id = fields.Many2one('product.product', required=True, index=True)
    location_id = fields.Many2one('stock.location', required=True, index=True)
    opening_date = fields.Datetime(required=True, index=True)
    quantity = fields.Float(required=True, default=0.0)
    uom_id = fields.Many2one('uom.uom', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    note = fields.Text()
    active = fields.Boolean(default=True, index=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id

    @api.constrains('product_id', 'location_id', 'opening_date', 'company_id', 'active', 'quantity')
    def _check_opening_balance(self):
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_('Opening balance quantity cannot be negative.'))
            if rec.active:
                domain = [('id', '!=', rec.id), ('active', '=', True), ('product_id', '=', rec.product_id.id), ('location_id', '=', rec.location_id.id), ('opening_date', '=', rec.opening_date)]
                domain += [('company_id', '=', rec.company_id.id)] if rec.company_id else [('company_id', '=', False)]
                if self.search_count(domain):
                    raise ValidationError(_('Only one active opening balance is allowed per product/location/company/date.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager_access()
        for vals in vals_list:
            if vals.get('product_id') and not vals.get('uom_id'):
                vals['uom_id'] = self.env['product.product'].browse(vals['product_id']).uom_id.id
        return super().create(vals_list)

    def write(self, vals):
        self._check_manager_access()
        return super().write(vals)

    def unlink(self):
        self._check_manager_access()
        return super().unlink()

    def _check_manager_access(self):
        if not self.env.user.has_group('stock_advanced_analytics.group_stock_analytics_manager'):
            raise AccessError(_('Only Inventory Analytics Managers can change opening balances.'))
