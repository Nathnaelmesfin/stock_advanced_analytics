from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    default_dashboard_date_range = fields.Integer(config_parameter='stock_advanced_analytics.default_dashboard_date_range', default=30)
    auto_refresh_interval = fields.Integer(config_parameter='stock_advanced_analytics.auto_refresh_interval', default=300)
    default_warehouse_id = fields.Many2one('stock.warehouse', config_parameter='stock_advanced_analytics.default_warehouse_id')
    default_internal_location_ids = fields.Many2many('stock.location', 'saa_cfg_internal_location_rel')
    consumption_location_ids = fields.Many2many('stock.location', 'saa_cfg_consumption_location_rel')
    scrap_location_ids = fields.Many2many('stock.location', 'saa_cfg_scrap_location_rel')
    branch_location_ids = fields.Many2many('stock.location', 'saa_cfg_branch_location_rel')
    transit_location_ids = fields.Many2many('stock.location', 'saa_cfg_transit_location_rel')
    enable_branch_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_branch_analytics', default=True)
    enable_usage_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_usage_analytics', default=True)
    enable_scrap_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_scrap_analytics', default=True)
    enable_adjustment_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_adjustment_analytics', default=True)
    enable_internal_transfer_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_internal_transfer_analytics', default=True)
    enable_receipt_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_receipt_analytics', default=True)
    enable_approval_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_approval_analytics', default=True)
    enable_low_stock_analytics = fields.Boolean(config_parameter='stock_advanced_analytics.enable_low_stock_analytics', default=True)
    default_report_timezone = fields.Char(config_parameter='stock_advanced_analytics.default_report_timezone', default='Africa/Addis_Ababa')
    pending_operation_late_days = fields.Integer(config_parameter='stock_advanced_analytics.pending_operation_late_days', default=3)
    no_movement_days_threshold = fields.Integer(config_parameter='stock_advanced_analytics.no_movement_days_threshold', default=60)

    def get_values(self):
        res = super().get_values(); ICP = self.env['ir.config_parameter'].sudo()
        for field in ['default_internal_location_ids','consumption_location_ids','scrap_location_ids','branch_location_ids','transit_location_ids']:
            value = ICP.get_param(f'stock_advanced_analytics.{field}', '')
            res[field] = [(6, 0, [int(x) for x in value.split(',') if x])]
        return res

    def set_values(self):
        super().set_values(); ICP = self.env['ir.config_parameter'].sudo()
        for field in ['default_internal_location_ids','consumption_location_ids','scrap_location_ids','branch_location_ids','transit_location_ids']:
            ICP.set_param(f'stock_advanced_analytics.{field}', ','.join(map(str, self[field].ids)))
