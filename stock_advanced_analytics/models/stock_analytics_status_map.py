from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

BUSINESS_STATUSES = [
    ('draft_request', 'Draft Request'), ('waiting_approval', 'Waiting for Approval'),
    ('approved_ready', 'Approved / Ready'), ('waiting_availability', 'Waiting Availability'),
    ('partially_available', 'Partially Available'), ('received_done', 'Received / Done'),
    ('cancelled', 'Cancelled'), ('late', 'Late'), ('back_order', 'Back Order'),
    ('unfinished', 'Unfinished'), ('other', 'Other'),
]


class StockAnalyticsStatusMap(models.Model):
    _name = 'stock.analytics.status.map'
    _description = 'Inventory Analytics Status Mapping'
    _order = 'applies_to, technical_state'

    name = fields.Char(required=True)
    technical_state = fields.Char(required=True, index=True)
    business_status = fields.Selection(BUSINESS_STATUSES, required=True, default='other', index=True)
    applies_to = fields.Selection([('internal_transfer', 'Internal Transfer'), ('receipt', 'Receipt'), ('all', 'All')], required=True, default='all', index=True)
    active = fields.Boolean(default=True, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)

    @api.constrains('technical_state', 'applies_to', 'company_id', 'active')
    def _check_unique_active_status(self):
        for rec in self.filtered(lambda r: r.active and r.company_id):
            if self.search_count([('id', '!=', rec.id), ('active', '=', True), ('technical_state', '=', rec.technical_state), ('applies_to', '=', rec.applies_to), ('company_id', '=', rec.company_id.id)]):
                raise ValidationError(_('Only one active status mapping is allowed for the same state, scope, and company.'))

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
            raise AccessError(_('Only Inventory Analytics Managers can change status mappings.'))

    @api.model
    def default_status_for_state(self, state, applies_to='all'):
        mapping = self.search([('active', '=', True), ('technical_state', '=', state), ('applies_to', 'in', [applies_to, 'all'])], limit=1)
        if mapping:
            return mapping.business_status
        defaults = {'draft': 'draft_request', 'waiting': 'waiting_availability', 'confirmed': 'waiting_availability', 'assigned': 'approved_ready', 'done': 'received_done', 'cancel': 'cancelled'}
        return defaults.get(state, 'other')

    @api.model
    def safe_approval_fields(self):
        fields_map = self.env['stock.picking']._fields
        return {field: field in fields_map for field in ['approval_state', 'request_state', 'x_approval_status', 'x_request_status', 'approved_by', 'requested_by']}
