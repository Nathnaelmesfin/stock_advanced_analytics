from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


LOCATION_ROLES = [
    ('main_store', 'Main Store'), ('kitchen_raw', 'Kitchen Raw'), ('kitchen_used', 'Kitchen Used'),
    ('cafe_raw', 'Cafe Raw'), ('cafe_used', 'Cafe Used'), ('pastry_raw', 'Pastry Raw'),
    ('pastry_used', 'Pastry Used'), ('staff_raw', 'Staff Raw'), ('staff_meal', 'Staff Meal'),
    ('management_meal', 'Management Meal'), ('finished_stock', 'Finished Stock'),
    ('cafe_finished', 'Cafe Finished'), ('kitchen_finished', 'Kitchen Finished'),
    ('pastry_finished', 'Pastry Finished'), ('catering_stock', 'Catering Stock'),
    ('catering_used', 'Catering Used'), ('branch_stock', 'Branch Stock'), ('branch_used', 'Branch Used'),
    ('scrap', 'Scrap'), ('transit', 'Transit'), ('other', 'Other'),
]


class StockAnalyticsLocationMap(models.Model):
    _name = 'stock.analytics.location.map'
    _description = 'Inventory Analytics Location Mapping'
    _order = 'location_id, company_id, name'

    name = fields.Char(required=True)
    location_id = fields.Many2one('stock.location', required=True, index=True, ondelete='cascade')
    location_role = fields.Selection(LOCATION_ROLES, required=True, default='other', index=True)
    department = fields.Char(index=True)
    branch_label = fields.Char(index=True)
    is_consumption_location = fields.Boolean(index=True)
    is_branch_location = fields.Boolean(index=True)
    is_raw_material_location = fields.Boolean(index=True)
    is_finished_location = fields.Boolean(index=True)
    is_catering_location = fields.Boolean(index=True)
    is_staff_meal_location = fields.Boolean(index=True)
    is_scrap_location = fields.Boolean(index=True)
    active = fields.Boolean(default=True, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    @api.constrains('location_id', 'company_id', 'active')
    def _check_unique_active_company_location(self):
        for rec in self.filtered(lambda r: r.active and r.company_id):
            domain = [('id', '!=', rec.id), ('active', '=', True), ('location_id', '=', rec.location_id.id), ('company_id', '=', rec.company_id.id)]
            if self.search_count(domain):
                raise ValidationError(_('Only one active company-specific mapping is allowed for each location.'))

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
            raise AccessError(_('Only Inventory Analytics Managers can change location mappings.'))

    @api.onchange('location_id')
    def _onchange_location_id(self):
        if self.location_id:
            vals = self.suggest_mapping_values(self.location_id.display_name or self.location_id.name)
            for key, value in vals.items():
                setattr(self, key, value)
            self.name = self.name or self.location_id.display_name

    @api.model
    def suggest_mapping_values(self, location_name):
        text = (location_name or '').lower()
        vals = {'location_role': 'other'}
        role_map = [
            ('kitchen used', 'kitchen_used'), ('cafe used', 'cafe_used'), ('pastry used', 'pastry_used'),
            ('management meal', 'management_meal'), ('staff meal', 'staff_meal'), ('catering used', 'catering_used'),
            ('branch used', 'branch_used'), ('kitchen raw', 'kitchen_raw'), ('cafe raw', 'cafe_raw'),
            ('pastry raw', 'pastry_raw'), ('staff raw', 'staff_raw'), ('finished', 'finished_stock'),
            ('catering', 'catering_stock'), ('branch', 'branch_stock'), ('scrap', 'scrap'), ('transit', 'transit'),
            ('main store', 'main_store'),
        ]
        for token, role in role_map:
            if token in text:
                vals['location_role'] = role
                break
        role = vals['location_role']
        vals.update({
            'is_consumption_location': role in self._consumption_roles(),
            'is_branch_location': role in ('branch_stock', 'branch_used'),
            'is_raw_material_location': role.endswith('_raw') or role == 'main_store',
            'is_finished_location': 'finished' in role,
            'is_catering_location': role.startswith('catering'),
            'is_staff_meal_location': role in ('staff_meal', 'management_meal', 'staff_raw'),
            'is_scrap_location': role == 'scrap',
        })
        if 'kitchen' in text: vals['department'] = 'Kitchen'
        elif 'cafe' in text or 'café' in text: vals['department'] = 'Cafe'
        elif 'pastry' in text: vals['department'] = 'Pastry'
        elif 'staff' in text or 'management meal' in text: vals['department'] = 'Staff Meal'
        elif 'catering' in text: vals['department'] = 'Catering'
        if 'branch' in text:
            vals['branch_label'] = location_name
        return vals

    @api.model
    def _consumption_roles(self):
        return ('kitchen_used', 'cafe_used', 'pastry_used', 'staff_meal', 'management_meal', 'catering_used', 'branch_used')

    @api.model
    def _mapped_location_ids(self, extra_domain):
        maps = self.search([('active', '=', True)] + extra_domain)
        return maps.mapped('location_id').ids

    @api.model
    def get_consumption_locations(self):
        return self._mapped_location_ids(['|', ('is_consumption_location', '=', True), ('location_role', 'in', self._consumption_roles())])

    @api.model
    def get_branch_locations(self):
        return self._mapped_location_ids(['|', ('is_branch_location', '=', True), ('location_role', 'in', ['branch_stock', 'branch_used'])])

    @api.model
    def get_raw_locations(self):
        return self._mapped_location_ids(['|', ('is_raw_material_location', '=', True), ('location_role', 'in', ['main_store', 'kitchen_raw', 'cafe_raw', 'pastry_raw', 'staff_raw'])])

    @api.model
    def get_finished_locations(self):
        return self._mapped_location_ids(['|', ('is_finished_location', '=', True), ('location_role', 'in', ['finished_stock', 'cafe_finished', 'kitchen_finished', 'pastry_finished'])])
