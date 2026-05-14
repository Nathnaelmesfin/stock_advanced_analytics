from odoo import api, fields, models, _
from odoo.exceptions import AccessError

REPORT_TYPES = [
('inventory_management_summary','Inventory Management Summary'),('current_stock_by_location','Current Stock by Location'),('historical_stock_as_of_date','Historical Stock as of Date'),('stock_movement_period_summary','Stock Movement Period Summary'),('consumption_used_location_report','Consumption / Used Location Report'),('kitchen_usage_report','Kitchen Usage Report'),('cafe_usage_report','Café Usage Report'),('pastry_usage_report','Pastry Usage Report'),('staff_meal_management_meal_report','Staff Meal / Management Meal Report'),('branch_stock_report','Branch Stock Report'),('operation_type_performance_report','Operation Type Performance Report'),('internal_transfer_analysis_report','Internal Transfer Analysis Report'),('internal_transfer_status_report','Internal Transfer Status Report'),('internal_transfer_user_performance_report','Internal Transfer User Performance Report'),('internal_transfer_location_performance_report','Internal Transfer Location Performance Report'),('unfinished_internal_transfer_report','Unfinished Internal Transfer Report'),('receipt_analysis_report','Receipt Analysis Report'),('receipt_status_report','Receipt Status Report'),('receipt_user_performance_report','Receipt User Performance Report'),('receipt_location_performance_report','Receipt Location Performance Report'),('unfinished_receipt_report','Unfinished Receipt Report'),('requested_product_report','Requested Product Report'),('waiting_approval_report','Waiting Approval Report'),('late_operations_report','Late Operations Report'),('back_order_report','Back Order Report'),('low_stock_report','Low Stock Report'),('out_of_stock_report','Out of Stock Report'),('negative_stock_report','Negative Stock Report'),('quant_vs_ledger_difference_report','Quant vs Ledger Difference Report'),('internal_transfer_report','Internal Transfer Report'),('scrap_waste_report','Scrap / Waste Report'),('inventory_adjustment_report','Inventory Adjustment Report'),('pending_operations_report','Pending Operations Report'),('slow_moving_products_report','Slow Moving Products Report'),('fast_moving_products_report','Fast Moving Products Report')]

GROUP_BY = [('day','Day'),('week','Week'),('month','Month'),('year','Year'),('product','Product'),('product_category','Product Category'),('warehouse','Warehouse'),('location','Location'),('source_location','Source Location'),('destination_location','Destination Location'),('operation_type','Operation Type'),('responsible_user','Responsible User'),('movement_status','Movement Status'),('business_status','Business Status'),('department','Department'),('branch','Branch'),('requested_by','Requested By'),('approved_by','Approved By')]


class StockAnalyticsReportWizard(models.TransientModel):
    _name = 'stock.analytics.report.wizard'
    _description = 'Inventory Analytics Report Wizard'

    report_mode = fields.Selection([('current_stock','Current Stock'),('stock_as_of_date','Stock as of Date'),('date_range_movement','Date Range Movement')], default='current_stock', required=True)
    date_start = fields.Datetime()
    date_end = fields.Datetime(default=fields.Datetime.now)
    as_of_datetime = fields.Datetime(default=fields.Datetime.now)
    warehouse_ids = fields.Many2many('stock.warehouse')
    location_ids = fields.Many2many('stock.location', 'saa_wiz_location_rel')
    source_location_ids = fields.Many2many('stock.location', 'saa_wiz_source_location_rel')
    destination_location_ids = fields.Many2many('stock.location', 'saa_wiz_destination_location_rel')
    location_role = fields.Selection(selection=lambda self: self.env['stock.analytics.location.map']._fields['location_role'].selection)
    operation_type_ids = fields.Many2many('stock.picking.type')
    product_category_ids = fields.Many2many('product.category')
    product_ids = fields.Many2many('product.product')
    responsible_user_ids = fields.Many2many('res.users')
    movement_state = fields.Selection([('draft','Draft'),('waiting','Waiting'),('confirmed','Confirmed'),('assigned','Ready'),('done','Done'),('cancel','Cancelled')])
    business_status = fields.Selection(selection=lambda self: self.env['stock.analytics.status.map']._fields['business_status'].selection)
    department = fields.Char()
    branch_label = fields.Char()
    report_type = fields.Selection(REPORT_TYPES, default='inventory_management_summary', required=True)
    group_by = fields.Selection(GROUP_BY, default='product')
    report_basis = fields.Selection([('quantity','Quantity'),('movement_count','Movement Count'),('transfer_count','Transfer Count')], default='quantity')
    include_raw_moves = fields.Boolean()
    include_raw_pickings = fields.Boolean()
    export_format = fields.Selection([('pdf','PDF'),('xlsx','Excel')], default='pdf')
    only_late = fields.Boolean()
    only_backorders = fields.Boolean()
    only_unfinished = fields.Boolean()
    only_waiting_approval = fields.Boolean()
    only_negative_stock = fields.Boolean()
    only_low_stock = fields.Boolean()
    only_out_of_stock = fields.Boolean()

    def _check_user_access(self):
        if not self.env.user.has_group('stock_advanced_analytics.group_stock_analytics_user'):
            raise AccessError(_('You are not allowed to generate Inventory Analytics reports.'))

    def _filters(self):
        self.ensure_one()
        return {
            'report_mode': self.report_mode, 'date_start': self.date_start, 'date_end': self.date_end, 'as_of_datetime': self.as_of_datetime,
            'warehouse_ids': self.warehouse_ids.ids, 'location_ids': self.location_ids.ids, 'source_location_ids': self.source_location_ids.ids,
            'destination_location_ids': self.destination_location_ids.ids, 'location_role': self.location_role, 'operation_type_ids': self.operation_type_ids.ids,
            'product_category_ids': self.product_category_ids.ids, 'product_ids': self.product_ids.ids, 'responsible_user_ids': self.responsible_user_ids.ids,
            'movement_state': self.movement_state, 'business_status': self.business_status, 'department': self.department, 'branch_label': self.branch_label,
            'report_type': self.report_type, 'group_by': self.group_by, 'report_basis': self.report_basis, 'include_raw_moves': self.include_raw_moves,
            'include_raw_pickings': self.include_raw_pickings, 'only_late': self.only_late, 'only_backorders': self.only_backorders,
            'only_unfinished': self.only_unfinished, 'only_waiting_approval': self.only_waiting_approval, 'only_negative_stock': self.only_negative_stock,
            'only_low_stock': self.only_low_stock, 'only_out_of_stock': self.only_out_of_stock,
        }

    def get_report_payload(self):
        self.ensure_one(); self._check_user_access()
        return self.env['stock.analytics.service'].get_report_data(self._filters())

    def action_generate_pdf(self):
        self.ensure_one(); self._check_user_access(); self.export_format = 'pdf'
        return self.env.ref('stock_advanced_analytics.action_report_stock_analytics_pdf').report_action(self)

    def action_generate_excel(self):
        self.ensure_one(); self._check_user_access(); self.export_format = 'xlsx'
        return {'type': 'ir.actions.act_url', 'url': f'/stock_advanced_analytics/xlsx/{self.id}', 'target': 'self'}
