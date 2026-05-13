from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class StockAnalyticsRule(models.Model):
    _name = 'stock.analytics.rule'
    _description = 'Inventory Analytics Stock Rule'
    _order = 'product_id, product_category_id, location_id'

    name = fields.Char(required=True)
    product_id = fields.Many2one('product.product', index=True)
    product_category_id = fields.Many2one('product.category', index=True)
    warehouse_id = fields.Many2one('stock.warehouse', index=True)
    location_id = fields.Many2one('stock.location', index=True)
    minimum_quantity = fields.Float(default=0.0)
    maximum_quantity = fields.Float(default=0.0)
    reorder_quantity = fields.Float(default=0.0)
    active = fields.Boolean(default=True, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    @api.constrains('minimum_quantity', 'maximum_quantity', 'reorder_quantity', 'product_id', 'product_category_id')
    def _check_quantities(self):
        for rec in self:
            if rec.minimum_quantity < 0 or rec.maximum_quantity < 0 or rec.reorder_quantity < 0:
                raise ValidationError(_('Threshold quantities cannot be negative.'))
            if rec.maximum_quantity and rec.minimum_quantity and rec.maximum_quantity <= rec.minimum_quantity:
                raise ValidationError(_('Maximum quantity must be greater than minimum quantity.'))
            if not rec.product_id and not rec.product_category_id:
                raise ValidationError(_('Set at least a product or a product category.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager_access()
        return super().create(vals_list)

    def write(self, vals):
        self._check_manager_access()
        return super().write(vals)

    def unlink(self):
        self._check_manager_access()
        return super().unlink()

    def _check_manager_access(self):
        if not self.env.user.has_group('stock_advanced_analytics.group_stock_analytics_manager'):
            raise AccessError(_('Only Inventory Analytics Managers can change stock analytics rules.'))
