from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

OPERATION_ROLES = [
    ('main_to_kitchen_raw', 'Main to Kitchen Raw'), ('main_to_cafe_raw', 'Main to Cafe Raw'),
    ('main_to_pastry_raw', 'Main to Pastry Raw'), ('main_to_staff_raw', 'Main to Staff Raw'),
    ('main_to_dairy_farm', 'Main to Dairy Farm'), ('main_to_consumable_in_use', 'Main to Consumable In Use'),
    ('kitchen_raw_to_kitchen_used', 'Kitchen Raw to Kitchen Used'), ('cafe_raw_to_cafe_used', 'Cafe Raw to Cafe Used'),
    ('pastry_raw_to_pastry_used', 'Pastry Raw to Pastry Used'), ('staff_raw_to_staff_meal', 'Staff Raw to Staff Meal'),
    ('staff_raw_to_management_meal', 'Staff Raw to Management Meal'), ('finished_to_stock', 'Finished to Stock'),
    ('finished_to_branch', 'Finished to Branch'), ('branch_to_used', 'Branch to Used'),
    ('catering_equipment_request', 'Catering Equipment Request'), ('catering_equipment_return', 'Catering Equipment Return'),
    ('catering_used', 'Catering Used'), ('receipt', 'Receipt'), ('delivery', 'Delivery'), ('pos_order', 'PoS Order'),
    ('other_internal_transfer', 'Other Internal Transfer'),
]


class StockAnalyticsOperationMap(models.Model):
    _name = 'stock.analytics.operation.map'
    _description = 'Inventory Analytics Operation Mapping'
    _order = 'picking_type_id, company_id, name'

    name = fields.Char(required=True)
    picking_type_id = fields.Many2one('stock.picking.type', required=True, index=True, ondelete='cascade')
    operation_role = fields.Selection(OPERATION_ROLES, required=True, default='other_internal_transfer', index=True)
    source_location_id = fields.Many2one('stock.location')
    destination_location_id = fields.Many2one('stock.location')
    department = fields.Char(index=True)
    branch_label = fields.Char(index=True)
    is_consumption_operation = fields.Boolean(index=True)
    is_branch_transfer = fields.Boolean(index=True)
    is_staff_meal_operation = fields.Boolean(index=True)
    is_catering_operation = fields.Boolean(index=True)
    is_return_operation = fields.Boolean(index=True)
    is_internal_transfer_operation = fields.Boolean(index=True)
    is_receipt_operation = fields.Boolean(index=True)
    active = fields.Boolean(default=True, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    @api.constrains('picking_type_id', 'company_id', 'active')
    def _check_unique_active_company_operation(self):
        for rec in self.filtered(lambda r: r.active and r.company_id):
            if self.search_count([('id', '!=', rec.id), ('active', '=', True), ('picking_type_id', '=', rec.picking_type_id.id), ('company_id', '=', rec.company_id.id)]):
                raise ValidationError(_('Only one active company-specific mapping is allowed for each operation type.'))

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
            raise AccessError(_('Only Inventory Analytics Managers can change operation mappings.'))

    @api.onchange('picking_type_id')
    def _onchange_picking_type_id(self):
        if self.picking_type_id:
            vals = self.suggest_mapping_values(self.picking_type_id.id)
            for key, value in vals.items():
                setattr(self, key, value)
            self.name = self.name or self.picking_type_id.display_name

    @api.model
    def suggest_mapping_values(self, picking_type_id):
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        text = ' '.join([picking_type.name or '', picking_type.code or '', picking_type.default_location_src_id.display_name or '', picking_type.default_location_dest_id.display_name or '']).lower()
        role = 'other_internal_transfer'
        pairs = [('receipt', 'receipt'), ('incoming', 'receipt'), ('delivery', 'delivery'), ('kitchen used', 'kitchen_raw_to_kitchen_used'), ('cafe used', 'cafe_raw_to_cafe_used'), ('pastry used', 'pastry_raw_to_pastry_used'), ('staff meal', 'staff_raw_to_staff_meal'), ('management meal', 'staff_raw_to_management_meal'), ('catering return', 'catering_equipment_return'), ('catering', 'catering_equipment_request'), ('branch', 'finished_to_branch'), ('finished', 'finished_to_stock')]
        for token, candidate in pairs:
            if token in text:
                role = candidate
                break
        vals = {'operation_role': role, 'source_location_id': picking_type.default_location_src_id.id, 'destination_location_id': picking_type.default_location_dest_id.id}
        vals.update({
            'is_consumption_operation': role in ('kitchen_raw_to_kitchen_used', 'cafe_raw_to_cafe_used', 'pastry_raw_to_pastry_used', 'staff_raw_to_staff_meal', 'staff_raw_to_management_meal', 'catering_used', 'branch_to_used'),
            'is_branch_transfer': role in ('finished_to_branch', 'branch_to_used'),
            'is_staff_meal_operation': role in ('staff_raw_to_staff_meal', 'staff_raw_to_management_meal'),
            'is_catering_operation': role.startswith('catering'),
            'is_return_operation': role == 'catering_equipment_return',
            'is_internal_transfer_operation': picking_type.code == 'internal' or role not in ('receipt', 'delivery', 'pos_order'),
            'is_receipt_operation': picking_type.code == 'incoming' or role == 'receipt',
        })
        if 'kitchen' in text: vals['department'] = 'Kitchen'
        elif 'cafe' in text or 'café' in text: vals['department'] = 'Cafe'
        elif 'pastry' in text: vals['department'] = 'Pastry'
        elif 'staff' in text: vals['department'] = 'Staff Meal'
        elif 'catering' in text: vals['department'] = 'Catering'
        if 'branch' in text: vals['branch_label'] = picking_type.name
        return vals

    @api.model
    def _mapped_type_ids(self, extra_domain):
        return self.search([('active', '=', True)] + extra_domain).mapped('picking_type_id').ids

    @api.model
    def get_internal_transfer_operation_types(self):
        ids = set(self._mapped_type_ids([('is_internal_transfer_operation', '=', True)]))
        ids.update(self.env['stock.picking.type'].search([('code', '=', 'internal')]).ids)
        return list(ids)

    @api.model
    def get_receipt_operation_types(self):
        ids = set(self._mapped_type_ids(['|', ('is_receipt_operation', '=', True), ('operation_role', '=', 'receipt')]))
        ids.update(self.env['stock.picking.type'].search([('code', '=', 'incoming')]).ids)
        return list(ids)

    @api.model
    def get_consumption_operation_types(self):
        return self._mapped_type_ids([('is_consumption_operation', '=', True)])

    @api.model
    def get_branch_transfer_operation_types(self):
        return self._mapped_type_ids([('is_branch_transfer', '=', True)])
