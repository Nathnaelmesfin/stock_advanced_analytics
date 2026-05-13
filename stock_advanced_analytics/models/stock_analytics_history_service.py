from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class StockAnalyticsHistoryService(models.AbstractModel):
    _name = 'stock.analytics.history.service'
    _description = 'Inventory Analytics History Service'

    def _check_user_access(self):
        if not self.env.user.has_group('stock_advanced_analytics.group_stock_analytics_user'):
            raise AccessError(_('You are not allowed to use Inventory Analytics.'))

    @api.model
    def get_quantity_field(self):
        fields_map = self.env['stock.move.line']._fields
        if 'quantity' in fields_map:
            return 'quantity'
        if 'qty_done' in fields_map:
            return 'qty_done'
        return 'product_uom_qty'

    @api.model
    def get_done_move_line_domain(self, filters):
        filters = filters or {}
        domain = [('state', '=', 'done')]
        allowed_company_ids = self.env.companies.ids
        if 'company_id' in self.env['stock.move.line']._fields:
            domain.append(('company_id', 'in', allowed_company_ids))
        if filters.get('product_ids'):
            domain.append(('product_id', 'in', filters['product_ids']))
        if filters.get('location_ids'):
            domain += ['|', ('location_id', 'in', filters['location_ids']), ('location_dest_id', 'in', filters['location_ids'])]
        if filters.get('date_start'):
            domain.append(('date', '>=', filters['date_start']))
        if filters.get('date_end'):
            domain.append(('date', '<=', filters['date_end']))
        return domain

    @api.model
    def _qty(self, line):
        return line[self.get_quantity_field()] or 0.0

    @api.model
    def get_opening_balance(self, product_id, location_id, start_datetime):
        self._check_user_access()
        domain = [('active', '=', True), ('product_id', '=', product_id), ('location_id', '=', location_id), ('opening_date', '<=', start_datetime), '|', ('company_id', '=', False), ('company_id', 'in', self.env.companies.ids)]
        ob = self.env['stock.analytics.opening.balance'].search(domain, order='opening_date desc, id desc', limit=1)
        return {'quantity': ob.quantity if ob else 0.0, 'opening_date': fields.Datetime.to_string(ob.opening_date) if ob else False, 'found': bool(ob)}

    @api.model
    def get_incoming_moves(self, product_id, location_id, start_datetime, end_datetime):
        self._check_user_access()
        domain = [('state', '=', 'done'), ('product_id', '=', product_id), ('location_dest_id', '=', location_id)]
        if start_datetime:
            domain.append(('date', '>', start_datetime))
        if end_datetime:
            domain.append(('date', '<=', end_datetime))
        lines = self.env['stock.move.line'].search(domain)
        return sum(self._qty(line) for line in lines)

    @api.model
    def get_outgoing_moves(self, product_id, location_id, start_datetime, end_datetime):
        self._check_user_access()
        domain = [('state', '=', 'done'), ('product_id', '=', product_id), ('location_id', '=', location_id)]
        if start_datetime:
            domain.append(('date', '>', start_datetime))
        if end_datetime:
            domain.append(('date', '<=', end_datetime))
        lines = self.env['stock.move.line'].search(domain)
        return sum(self._qty(line) for line in lines)

    @api.model
    def get_location_product_balance(self, product_id, location_id, as_of_datetime):
        self._check_user_access()
        opening = self.get_opening_balance(product_id, location_id, as_of_datetime)
        start = opening['opening_date'] if opening['found'] else False
        incoming = self.get_incoming_moves(product_id, location_id, start, as_of_datetime)
        outgoing = self.get_outgoing_moves(product_id, location_id, start, as_of_datetime)
        if not opening['found']:
            warning = _('No opening balance found; calculated from available move history.')
        else:
            warning = False
        return {'product_id': product_id, 'location_id': location_id, 'opening': opening['quantity'], 'incoming': incoming, 'outgoing': outgoing, 'balance': opening['quantity'] + incoming - outgoing, 'warning': warning}

    @api.model
    def get_stock_as_of_date(self, filters):
        self._check_user_access()
        filters = filters or {}
        as_of = filters.get('as_of_datetime') or fields.Datetime.now()
        location_ids = filters.get('location_ids') or self.env['stock.location'].search([('usage', 'in', ['internal', 'transit'])]).ids
        product_ids = filters.get('product_ids') or self.env['product.product'].search([('type', 'in', ['product', 'consu'])], limit=5000).ids
        rows = []
        Quant = self.env['stock.quant']
        for product_id in product_ids[:5000]:
            product = self.env['product.product'].browse(product_id)
            for location_id in location_ids[:1000]:
                location = self.env['stock.location'].browse(location_id)
                balance = self.get_location_product_balance(product_id, location_id, as_of)
                current_qty = sum(Quant.search([('product_id', '=', product_id), ('location_id', '=', location_id)]).mapped('quantity'))
                if any([balance['opening'], balance['incoming'], balance['outgoing'], balance['balance'], current_qty]) or filters.get('include_zero'):
                    rows.append({
                        'product': product.display_name, 'category': product.categ_id.display_name, 'location': location.display_name,
                        'opening': balance['opening'], 'incoming': balance['incoming'], 'outgoing': balance['outgoing'],
                        'historical_balance': balance['balance'], 'current_balance': current_qty, 'difference': current_qty - balance['balance'],
                        'warning': balance['warning'] or '',
                    })
        return {'as_of_datetime': fields.Datetime.to_string(as_of), 'rows': rows, 'warnings': list({r['warning'] for r in rows if r['warning']})}

    @api.model
    def get_stock_period_summary(self, filters):
        self._check_user_access()
        filters = filters or {}
        start = filters.get('date_start') or fields.Date.to_string(fields.Date.today())
        end = filters.get('date_end') or fields.Datetime.now()
        products = filters.get('product_ids') or self.env['product.product'].search([('type', 'in', ['product', 'consu'])], limit=1000).ids
        locations = filters.get('location_ids') or self.env['stock.location'].search([('usage', 'in', ['internal', 'transit'])], limit=500).ids
        rows = []
        consumption_ids = set(self.env['stock.analytics.location.map'].get_consumption_locations())
        for product_id in products:
            product = self.env['product.product'].browse(product_id)
            for location_id in locations:
                location = self.env['stock.location'].browse(location_id)
                opening = self.get_location_product_balance(product_id, location_id, start)['balance']
                incoming = self.get_incoming_moves(product_id, location_id, start, end)
                outgoing = self.get_outgoing_moves(product_id, location_id, start, end)
                used = incoming if location_id in consumption_ids else 0.0
                closing = opening + incoming - outgoing
                if any([opening, incoming, outgoing, closing, used]):
                    rows.append({'product': product.display_name, 'location': location.display_name, 'opening': opening, 'incoming': incoming, 'outgoing': outgoing, 'used': used, 'returned': 0.0, 'scrapped': 0.0, 'adjustment': 0.0, 'closing': closing})
        return {'date_start': start, 'date_end': fields.Datetime.to_string(end), 'rows': rows}
