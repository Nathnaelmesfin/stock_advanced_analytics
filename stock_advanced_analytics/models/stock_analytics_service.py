from collections import Counter, defaultdict
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class StockAnalyticsService(models.AbstractModel):
    _name = 'stock.analytics.service'
    _description = 'Inventory Advanced Analytics Service'

    def _check_user_access(self):
        if not self.env.user.has_group('stock_advanced_analytics.group_stock_analytics_user'):
            raise AccessError(_('You are not allowed to use Inventory Analytics.'))

    @api.model
    def _model_has_field(self, model_name, field_name):
        return model_name in self.env and field_name in self.env[model_name]._fields

    @api.model
    def _table_has_column(self, table_name, column_name):
        self.env.cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s", (table_name, column_name))
        return bool(self.env.cr.fetchone())

    @api.model
    def _get_move_line_quantity_expr(self, alias='sml'):
        if self._table_has_column('stock_move_line', 'quantity'):
            return f'COALESCE({alias}.quantity, 0)'
        if self._table_has_column('stock_move_line', 'qty_done'):
            return f'COALESCE({alias}.qty_done, 0)'
        return f'COALESCE({alias}.product_uom_qty, 0)'

    @api.model
    def _safe_user_field(self, field_candidates):
        fields_map = self.env['stock.picking']._fields
        return next((field for field in field_candidates if field in fields_map), False)

    @api.model
    def _safe_approval_fields(self):
        return self.env['stock.analytics.status.map'].safe_approval_fields()

    @api.model
    def _settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        def get_bool(key, default=True):
            return ICP.get_param(f'stock_advanced_analytics.{key}', str(default)) == 'True'
        def get_int(key, default):
            try: return int(ICP.get_param(f'stock_advanced_analytics.{key}', default))
            except Exception: return default
        def get_ids(key):
            value = ICP.get_param(f'stock_advanced_analytics.{key}', '')
            return [int(x) for x in value.split(',') if x]
        return {
            'default_dashboard_date_range': ICP.get_param('stock_advanced_analytics.default_dashboard_date_range', '30'),
            'auto_refresh_interval': max(get_int('auto_refresh_interval', 300), 30),
            'default_warehouse_id': int(ICP.get_param('stock_advanced_analytics.default_warehouse_id', 0) or 0),
            'default_internal_location_ids': get_ids('default_internal_location_ids'),
            'consumption_location_ids': get_ids('consumption_location_ids'),
            'scrap_location_ids': get_ids('scrap_location_ids'),
            'branch_location_ids': get_ids('branch_location_ids'),
            'transit_location_ids': get_ids('transit_location_ids'),
            'enable_branch_analytics': get_bool('enable_branch_analytics'),
            'enable_usage_analytics': get_bool('enable_usage_analytics'),
            'enable_scrap_analytics': get_bool('enable_scrap_analytics'),
            'enable_adjustment_analytics': get_bool('enable_adjustment_analytics'),
            'enable_internal_transfer_analytics': get_bool('enable_internal_transfer_analytics'),
            'enable_receipt_analytics': get_bool('enable_receipt_analytics'),
            'enable_approval_analytics': get_bool('enable_approval_analytics'),
            'enable_low_stock_analytics': get_bool('enable_low_stock_analytics'),
            'default_report_timezone': ICP.get_param('stock_advanced_analytics.default_report_timezone', 'Africa/Addis_Ababa'),
            'pending_operation_late_days': get_int('pending_operation_late_days', 3),
            'no_movement_days_threshold': get_int('no_movement_days_threshold', 60),
        }

    @api.model
    def _base_filters(self, filters):
        filters = dict(filters or {})
        settings = self._settings()
        if not filters.get('date_start') and not filters.get('date_end'):
            days = int(settings['default_dashboard_date_range'] or 30)
            filters['date_start'] = fields.Date.to_string(fields.Date.today() - timedelta(days=days))
            filters['date_end'] = fields.Datetime.now()
        return filters

    @api.model
    def get_dashboard_bootstrap_data(self):
        self._check_user_access()
        settings = self._settings()
        return {
            'settings': settings,
            'modes': ['live_dashboard', 'stock_by_location', 'historical_stock', 'stock_movement_analysis', 'internal_transfer_analysis', 'receipts_analysis', 'consumption_analytics', 'branch_analytics', 'operation_type_monitor', 'unfinished_operations'],
            'location_roles': self.env['stock.analytics.location.map']._fields['location_role'].selection,
            'business_statuses': self.env['stock.analytics.status.map']._fields['business_status'].selection,
            'warehouses': [{'id': w.id, 'name': w.display_name} for w in self.env['stock.warehouse'].search([])],
            'companies': [{'id': c.id, 'name': c.display_name} for c in self.env.companies],
            'optional_fields': {'approval': self._safe_approval_fields(), 'date_done': self._model_has_field('stock.picking', 'date_done'), 'partner_id': self._model_has_field('stock.picking', 'partner_id')},
        }

    @api.model
    def get_dashboard_data(self, filters):
        self._check_user_access(); filters = self._base_filters(filters); settings = self._settings()
        data = {'kpis': self._get_kpis(filters), 'current_stock': self._get_current_stock_by_location(filters)[:80], 'movement_trend': self._get_movement_trend(filters), 'low_stock': [], 'out_of_stock': [], 'negative_stock': self._get_negative_stock(filters), 'quant_vs_ledger': self._get_quant_vs_ledger_difference(filters)[:50], 'settings': settings}
        if settings['enable_low_stock_analytics']:
            data['low_stock'] = self._get_low_stock(filters); data['out_of_stock'] = self._get_out_of_stock(filters)
        if settings['enable_usage_analytics']:
            data['consumption'] = self.get_consumption_analytics(filters)
        if settings['enable_branch_analytics']:
            data['branch'] = self.get_branch_analytics(filters)
        if settings['enable_internal_transfer_analytics']:
            data['internal_transfer'] = self.get_internal_transfer_analysis(filters)
        if settings['enable_receipt_analytics']:
            data['receipts'] = self.get_receipt_analysis(filters)
        data['unfinished'] = self.get_unfinished_operations(filters)
        return data

    @api.model
    def get_stock_by_location_data(self, filters):
        self._check_user_access(); return {'rows': self._get_current_stock_by_location(filters or {}), 'kpis': self._get_stock_on_hand(filters or {})}

    @api.model
    def get_historical_stock_data(self, filters):
        self._check_user_access(); return self.env['stock.analytics.history.service'].get_stock_as_of_date(filters or {})

    @api.model
    def get_stock_movement_analysis(self, filters):
        self._check_user_access(); return self.env['stock.analytics.history.service'].get_stock_period_summary(filters or {})

    @api.model
    def _quant_domain(self, filters):
        domain = [('company_id', 'in', self.env.companies.ids)]
        if filters.get('location_ids'): domain.append(('location_id', 'in', filters['location_ids']))
        if filters.get('product_ids'): domain.append(('product_id', 'in', filters['product_ids']))
        if filters.get('product_category_ids'): domain.append(('product_id.categ_id', 'in', filters['product_category_ids']))
        return domain

    @api.model
    def _get_current_stock_by_location(self, filters):
        filters = filters or {}; rows = []; role_by_loc = {m.location_id.id: m.location_role for m in self.env['stock.analytics.location.map'].search([('active', '=', True)])}
        for quant in self.env['stock.quant'].search(self._quant_domain(filters), limit=5000):
            product = quant.product_id; location = quant.location_id
            if not product or location.usage not in ('internal', 'transit'):
                continue
            last_domain = [('product_id', '=', product.id), '|', ('location_id', '=', location.id), ('location_dest_id', '=', location.id), ('state', '=', 'done')]
            last = self.env['stock.move.line'].search(last_domain, order='date desc', limit=1)
            incoming = self.env['stock.move.line'].search([('product_id', '=', product.id), ('location_dest_id', '=', location.id), ('state', '=', 'done')], order='date desc', limit=1)
            outgoing = self.env['stock.move.line'].search([('product_id', '=', product.id), ('location_id', '=', location.id), ('state', '=', 'done')], order='date desc', limit=1)
            reserved = quant.reserved_quantity if 'reserved_quantity' in quant._fields else 0.0
            available = quant.quantity - reserved
            status = 'negative' if quant.quantity < 0 else ('out_of_stock' if quant.quantity == 0 else 'available')
            rows.append({'product': product.display_name, 'category': product.categ_id.display_name, 'type': product.type, 'uom': product.uom_id.name, 'warehouse': self._warehouse_for_location(location), 'location': location.display_name, 'role': role_by_loc.get(location.id, ''), 'on_hand': quant.quantity, 'reserved': reserved, 'available': available, 'last_movement': fields.Datetime.to_string(last.date) if last else '', 'last_incoming': fields.Datetime.to_string(incoming.date) if incoming else '', 'last_outgoing': fields.Datetime.to_string(outgoing.date) if outgoing else '', 'status': status})
        return rows

    @api.model
    def _warehouse_for_location(self, location):
        wh = self.env['stock.warehouse'].search(['|', ('lot_stock_id', '=', location.id), ('view_location_id', 'parent_of', location.id)], limit=1)
        return wh.display_name if wh else ''

    @api.model
    def _get_stock_on_hand(self, filters):
        rows = self._get_current_stock_by_location(filters)
        return {'stock_lines': len(rows), 'products_with_stock': len({r['product'] for r in rows if r['on_hand']}), 'total_on_hand': sum(r['on_hand'] for r in rows), 'total_available': sum(r['available'] for r in rows)}

    @api.model
    def _get_movement_ledger_balance(self, filters):
        filters = filters or {}; qty_field = self.env['stock.analytics.history.service'].get_quantity_field(); balances = defaultdict(float)
        lines = self.env['stock.move.line'].search(self.env['stock.analytics.history.service'].get_done_move_line_domain(filters), limit=10000)
        for line in lines:
            qty = line[qty_field] or 0.0; balances[(line.product_id.id, line.location_dest_id.id)] += qty; balances[(line.product_id.id, line.location_id.id)] -= qty
        for ob in self.env['stock.analytics.opening.balance'].search([('active', '=', True), '|', ('company_id', '=', False), ('company_id', 'in', self.env.companies.ids)]):
            balances[(ob.product_id.id, ob.location_id.id)] += ob.quantity
        rows = []
        for (product_id, location_id), balance in balances.items():
            if abs(balance) < 0.00001: continue
            product = self.env['product.product'].browse(product_id); location = self.env['stock.location'].browse(location_id)
            rows.append({'product': product.display_name, 'location': location.display_name, 'ledger_quantity': balance})
        return rows

    @api.model
    def _get_quant_vs_ledger_difference(self, filters):
        quant_rows = {(q.product_id.display_name, q.location_id.display_name): q.quantity for q in self.env['stock.quant'].search(self._quant_domain(filters or {}), limit=5000)}
        ledger_rows = {(r['product'], r['location']): r['ledger_quantity'] for r in self._get_movement_ledger_balance(filters or {})}
        rows = []
        for key in set(quant_rows) | set(ledger_rows):
            diff = quant_rows.get(key, 0.0) - ledger_rows.get(key, 0.0)
            if abs(diff) >= 0.0001:
                rows.append({'product': key[0], 'location': key[1], 'quant_quantity': quant_rows.get(key, 0.0), 'ledger_quantity': ledger_rows.get(key, 0.0), 'difference': diff, 'last_movement': '', 'possible_issue': _('Opening balance or historical move coverage should be reviewed.')})
        return rows

    @api.model
    def _move_line_domain(self, filters):
        domain = [('state', '=', 'done')]; filters = filters or {}
        if filters.get('date_start'): domain.append(('date', '>=', filters['date_start']))
        if filters.get('date_end'): domain.append(('date', '<=', filters['date_end']))
        if filters.get('product_ids'): domain.append(('product_id', 'in', filters['product_ids']))
        if filters.get('source_location_ids'): domain.append(('location_id', 'in', filters['source_location_ids']))
        if filters.get('destination_location_ids'): domain.append(('location_dest_id', 'in', filters['destination_location_ids']))
        return domain

    @api.model
    def _get_movement_trend(self, filters):
        qty_field = self.env['stock.analytics.history.service'].get_quantity_field(); totals = defaultdict(float)
        for line in self.env['stock.move.line'].search(self._move_line_domain(filters), limit=10000):
            totals[fields.Date.to_string(line.date.date())] += line[qty_field] or 0.0
        return [{'label': d, 'value': v} for d, v in sorted(totals.items())]

    @api.model
    def _get_top_products(self, filters):
        qty_field = self.env['stock.analytics.history.service'].get_quantity_field(); totals = Counter()
        for line in self.env['stock.move.line'].search(self._move_line_domain(filters), limit=10000): totals[line.product_id.display_name] += line[qty_field] or 0.0
        return [{'label': k, 'value': v} for k, v in totals.most_common(10)]

    @api.model
    def _get_top_categories(self, filters):
        qty_field = self.env['stock.analytics.history.service'].get_quantity_field(); totals = Counter()
        for line in self.env['stock.move.line'].search(self._move_line_domain(filters), limit=10000): totals[line.product_id.categ_id.display_name] += line[qty_field] or 0.0
        return [{'label': k, 'value': v} for k, v in totals.most_common(10)]

    @api.model
    def _get_warehouse_summary(self, filters):
        rows = self._get_current_stock_by_location(filters); totals = defaultdict(float)
        for row in rows: totals[row['warehouse'] or _('No Warehouse')] += row['on_hand']
        return [{'warehouse': k, 'quantity': v} for k, v in totals.items()]

    @api.model
    def _get_location_summary(self, filters):
        rows = self._get_current_stock_by_location(filters); totals = defaultdict(float)
        for row in rows: totals[row['location']] += row['on_hand']
        return [{'location': k, 'quantity': v} for k, v in totals.items()]

    @api.model
    def _get_branch_summary(self, filters):
        return self.get_branch_analytics(filters).get('summary', [])

    @api.model
    def _get_usage_summary(self, filters):
        return self.get_consumption_analytics(filters).get('summary', [])

    @api.model
    def _get_low_stock(self, filters):
        rows = self._get_current_stock_by_location(filters); rules = self.env['stock.analytics.rule'].search([('active', '=', True)])
        low = []
        for row in rows:
            for rule in rules:
                product_match = not rule.product_id or rule.product_id.display_name == row['product']
                category_match = not rule.product_category_id or rule.product_category_id.display_name == row['category']
                location_match = not rule.location_id or rule.location_id.display_name == row['location']
                if product_match and category_match and location_match and row['on_hand'] < rule.minimum_quantity:
                    low.append(dict(row, rule=rule.name, minimum_quantity=rule.minimum_quantity, shortage=rule.minimum_quantity - row['on_hand']))
                    break
        return low

    @api.model
    def _get_out_of_stock(self, filters): return [r for r in self._get_current_stock_by_location(filters) if r['on_hand'] == 0]
    @api.model
    def _get_negative_stock(self, filters): return [r for r in self._get_current_stock_by_location(filters) if r['on_hand'] < 0]

    @api.model
    def _get_slow_moving_products(self, filters):
        threshold = self._settings()['no_movement_days_threshold']; cutoff = fields.Datetime.now() - timedelta(days=threshold); rows=[]
        for p in self.env['product.product'].search([('type', 'in', ['product','consu'])], limit=1000):
            last = self.env['stock.move.line'].search([('product_id','=',p.id),('state','=','done')], order='date desc', limit=1)
            if not last or last.date < cutoff: rows.append({'product': p.display_name, 'category': p.categ_id.display_name, 'last_movement': fields.Datetime.to_string(last.date) if last else '', 'days_threshold': threshold})
        return rows

    @api.model
    def _get_fast_moving_products(self, filters): return self._get_top_products(filters)

    @api.model
    def _get_scrap_summary(self, filters):
        qty_field = 'scrap_qty' if self._model_has_field('stock.scrap', 'scrap_qty') else False; rows=[]
        if qty_field:
            for scrap in self.env['stock.scrap'].search([], limit=1000): rows.append({'product': scrap.product_id.display_name, 'location': scrap.location_id.display_name, 'quantity': scrap[qty_field], 'date': fields.Datetime.to_string(scrap.date_done or scrap.create_date), 'user': scrap.create_uid.display_name})
        return rows

    @api.model
    def _get_adjustment_summary(self, filters):
        return [r for r in self._get_movement_ledger_balance(filters) if r['ledger_quantity']]

    @api.model
    def _picking_domain(self, filters, kind=None):
        domain = [('company_id', 'in', self.env.companies.ids)]; filters = filters or {}
        if kind == 'internal': domain.append(('picking_type_id', 'in', self.env['stock.analytics.operation.map'].get_internal_transfer_operation_types()))
        elif kind == 'receipt': domain.append(('picking_type_id', 'in', self.env['stock.analytics.operation.map'].get_receipt_operation_types()))
        if filters.get('date_start'): domain.append(('create_date', '>=', filters['date_start']))
        if filters.get('date_end'): domain.append(('create_date', '<=', filters['date_end']))
        if filters.get('operation_type_ids'): domain.append(('picking_type_id', 'in', filters['operation_type_ids']))
        if filters.get('responsible_user_ids') and self._model_has_field('stock.picking','user_id'): domain.append(('user_id','in',filters['responsible_user_ids']))
        if filters.get('movement_state'): domain.append(('state', '=', filters['movement_state']))
        if filters.get('only_unfinished'): domain.append(('state', 'not in', ['done', 'cancel']))
        return domain

    @api.model
    def _business_status(self, picking, applies_to='all'):
        if self._is_backorder(picking): return 'back_order'
        if picking.state not in ('done','cancel') and self._is_late(picking): return 'late'
        approval = self._safe_approval_fields()
        for f in ('approval_state','request_state','x_approval_status','x_request_status'):
            if approval.get(f) and (picking[f] or '').lower() in ('waiting','to_approve','pending','waiting_approval'):
                return 'waiting_approval'
        return self.env['stock.analytics.status.map'].default_status_for_state(picking.state, applies_to)

    @api.model
    def _is_late(self, picking): return bool(self._model_has_field('stock.picking','scheduled_date') and picking.scheduled_date and picking.scheduled_date < fields.Datetime.now() and picking.state not in ('done','cancel'))

    @api.model
    def _is_backorder(self, picking):
        if self._model_has_field('stock.picking','backorder_id') and picking.backorder_id: return True
        if self._model_has_field('stock.picking','backorder_ids') and picking.backorder_ids: return True
        return bool(picking.origin and 'backorder' in picking.origin.lower())

    @api.model
    def _pickings_to_rows(self, pickings, applies_to='internal_transfer'):
        rows=[]; approval=self._safe_approval_fields(); qty_field=self.env['stock.analytics.history.service'].get_quantity_field()
        for p in pickings:
            move_lines = p.move_line_ids; demand = sum(p.move_ids.mapped('product_uom_qty')); done = sum((ml[qty_field] or 0.0) for ml in move_lines); pending=max(demand-done,0.0)
            scheduled = p.scheduled_date if self._model_has_field('stock.picking','scheduled_date') else False; done_date = p.date_done if self._model_has_field('stock.picking','date_done') else False
            rows.append({'reference': p.name, 'operation_type': p.picking_type_id.display_name, 'source_location': p.location_id.display_name, 'destination_location': p.location_dest_id.display_name, 'department': self._department_for_picking(p), 'branch': self._branch_for_picking(p), 'requested_by': p[ 'requested_by'].display_name if approval.get('requested_by') and p['requested_by'] else '', 'responsible_user': p.user_id.display_name if self._model_has_field('stock.picking','user_id') and p.user_id else '', 'approved_by': p['approved_by'].display_name if approval.get('approved_by') and p['approved_by'] else '', 'request_date': fields.Datetime.to_string(p.create_date), 'scheduled_date': fields.Datetime.to_string(scheduled) if scheduled else '', 'done_date': fields.Datetime.to_string(done_date) if done_date else '', 'status': p.state, 'business_status': self._business_status(p, applies_to), 'product_count': len(p.move_ids.mapped('product_id')), 'requested_qty': demand, 'done_qty': done, 'pending_qty': pending, 'late_days': self._late_days(p), 'back_order': self._is_backorder(p), 'priority': getattr(p, 'priority', '') if self._model_has_field('stock.picking','priority') else '', 'origin': p.origin or ''})
        return rows

    @api.model
    def _line_rows(self, pickings):
        rows=[]; qty_field=self.env['stock.analytics.history.service'].get_quantity_field()
        for p in pickings:
            done_by_product = defaultdict(float)
            for ml in p.move_line_ids: done_by_product[ml.product_id.id] += ml[qty_field] or 0.0
            for m in p.move_ids:
                done=done_by_product[m.product_id.id]; demand=m.product_uom_qty; reserved=getattr(m,'reserved_availability',0.0)
                rows.append({'reference': p.name, 'product': m.product_id.display_name, 'category': m.product_id.categ_id.display_name, 'requested_qty': demand, 'reserved_qty': reserved, 'done_qty': done, 'pending_qty': max(demand-done,0.0), 'uom': m.product_uom.name, 'source_location': p.location_id.display_name, 'destination_location': p.location_dest_id.display_name, 'line_status': p.state})
        return rows

    def _late_days(self, picking):
        if self._is_late(picking): return (fields.Datetime.now().date() - picking.scheduled_date.date()).days
        return 0

    def _department_for_picking(self, picking):
        mapping = self.env['stock.analytics.operation.map'].search([('picking_type_id','=',picking.picking_type_id.id),('active','=',True)], limit=1)
        return mapping.department or ''

    def _branch_for_picking(self, picking):
        mapping = self.env['stock.analytics.operation.map'].search([('picking_type_id','=',picking.picking_type_id.id),('active','=',True)], limit=1)
        return mapping.branch_label or ''

    @api.model
    def _get_pending_operations(self, filters): return self._pickings_to_rows(self.env['stock.picking'].search(self._picking_domain(dict(filters or {}, only_unfinished=True))), 'all')
    @api.model
    def _get_late_operations(self, filters): return [r for r in self._get_pending_operations(filters) if r['late_days']]
    @api.model
    def _get_backorder_analysis(self, filters): return [r for r in self._pickings_to_rows(self.env['stock.picking'].search(self._picking_domain(filters)), 'all') if r['back_order']]
    @api.model
    def _get_requested_product_analysis(self, filters):
        pickings = self.env['stock.picking'].search(self._picking_domain(filters), limit=5000); totals={}
        for p in pickings:
            for m in p.move_ids:
                key=m.product_id.id; rec=totals.setdefault(key, {'product':m.product_id.display_name,'category':m.product_id.categ_id.display_name,'requested_qty':0,'approved_qty':0,'done_qty':0,'pending_qty':0,'cancelled_qty':0,'request_count':0,'late_request_count':0,'top_requesting_location':p.location_id.display_name,'top_requesting_user':p.user_id.display_name if self._model_has_field('stock.picking','user_id') and p.user_id else ''})
                rec['requested_qty']+=m.product_uom_qty; rec['done_qty']+=m.quantity_done if 'quantity_done' in m._fields else 0; rec['pending_qty']+=max(m.product_uom_qty-rec['done_qty'],0); rec['request_count']+=1; rec['late_request_count']+=1 if self._is_late(p) else 0; rec['cancelled_qty']+=m.product_uom_qty if p.state=='cancel' else 0; rec['approved_qty']+=m.product_uom_qty if p.state in ('assigned','done') else 0
        return list(totals.values())
    @api.model
    def _get_approval_analysis(self, filters): return [r for r in self._get_pending_operations(filters) if r['business_status']=='waiting_approval']

    @api.model
    def get_consumption_analytics(self, filters):
        self._check_user_access(); filters=filters or {}; loc_ids=set(filters.get('destination_location_ids') or []) or set(self._settings()['consumption_location_ids']) or set(self.env['stock.analytics.location.map'].get_consumption_locations())
        if not loc_ids: return {'kpis':{}, 'summary':[], 'rows':[], 'by_product':[], 'by_category':[], 'by_department':[], 'by_location':[], 'trend':[]}
        qty_field=self.env['stock.analytics.history.service'].get_quantity_field(); domain=self._move_line_domain(filters)+[('location_dest_id','in',list(loc_ids))]
        rows=[]; by_prod=Counter(); by_cat=Counter(); by_dept=Counter(); by_loc=Counter(); trend=Counter()
        maps={m.location_id.id:m for m in self.env['stock.analytics.location.map'].search([('location_id','in',list(loc_ids)),('active','=',True)])}
        for line in self.env['stock.move.line'].search(domain, limit=10000):
            qty=line[qty_field] or 0.0; mapping=maps.get(line.location_dest_id.id); dept=(mapping.department if mapping else '') or ''
            row={'product':line.product_id.display_name,'category':line.product_id.categ_id.display_name,'department':dept,'source':line.location_id.display_name,'used_location':line.location_dest_id.display_name,'quantity_used':qty,'uom':line.product_uom_id.name,'reference':line.reference or (line.picking_id.name if line.picking_id else ''),'user':line.picking_id.user_id.display_name if line.picking_id and self._model_has_field('stock.picking','user_id') and line.picking_id.user_id else '','date':fields.Datetime.to_string(line.date)}
            rows.append(row); by_prod[row['product']]+=qty; by_cat[row['category']]+=qty; by_dept[dept or _('Unmapped')]+=qty; by_loc[row['used_location']]+=qty; trend[fields.Date.to_string(line.date.date())]+=qty
        return {'kpis':{'total_used_quantity':sum(by_prod.values()),'used_locations':len(loc_ids),'line_count':len(rows),'most_consumed_product':by_prod.most_common(1)[0][0] if by_prod else ''}, 'summary':[{'label':k,'value':v} for k,v in by_dept.items()], 'rows':rows, 'by_product':[{'label':k,'value':v} for k,v in by_prod.most_common(10)], 'by_category':[{'label':k,'value':v} for k,v in by_cat.most_common(10)], 'by_department':[{'label':k,'value':v} for k,v in by_dept.items()], 'by_location':[{'label':k,'value':v} for k,v in by_loc.items()], 'trend':[{'label':k,'value':v} for k,v in sorted(trend.items())]}

    @api.model
    def get_branch_analytics(self, filters):
        self._check_user_access(); branch_ids=set((filters or {}).get('location_ids') or []) or set(self._settings()['branch_location_ids']) or set(self.env['stock.analytics.location.map'].get_branch_locations())
        if not branch_ids: return {'kpis':{}, 'summary':[], 'rows':[], 'top_sent':[], 'top_used':[]}
        current=[r for r in self._get_current_stock_by_location({'location_ids':list(branch_ids)})]; consumption=self.get_consumption_analytics(dict(filters or {}, destination_location_ids=list(branch_ids)))
        rows=[]
        for r in current: rows.append({'product':r['product'],'category':r['category'],'opening_branch_stock':0.0,'sent_to_branch':0.0,'received_at_branch':0.0,'used_at_branch':0.0,'returned':0.0,'scrapped':0.0,'closing_branch_stock':r['on_hand'],'current_branch_stock':r['on_hand']})
        return {'kpis':{'branch_current_stock':sum(r['on_hand'] for r in current),'branch_used_quantity':consumption.get('kpis',{}).get('total_used_quantity',0),'branch_locations':len(branch_ids),'branch_low_stock':len(self._get_low_stock({'location_ids':list(branch_ids)}))}, 'summary':[{'label':r['location'],'value':r['on_hand']} for r in current[:20]], 'rows':rows, 'top_sent':self._get_top_products(filters or {}), 'top_used':consumption.get('by_product',[])}

    @api.model
    def _get_internal_transfer_kpis(self, filters):
        rows=self._pickings_to_rows(self.env['stock.picking'].search(self._picking_domain(filters,'internal'), limit=5000),'internal_transfer'); c=Counter(r['business_status'] for r in rows)
        return {'total_internal_transfer_requests':len(rows),'draft_requests':c['draft_request'],'waiting_approval':c['waiting_approval'],'approved_requests':c['approved_ready'],'ready_to_process':c['approved_ready'],'waiting_availability':c['waiting_availability'],'received_done':c['received_done'],'cancelled':c['cancelled'],'late_transfers':c['late'],'back_orders':c['back_order'],'unfinished_transfers':sum(1 for r in rows if r['status'] not in ('done','cancel')),'total_requested_qty':sum(r['requested_qty'] for r in rows),'total_done_qty':sum(r['done_qty'] for r in rows)}

    def _breakdown(self, rows, key):
        qty=defaultdict(float); count=Counter()
        for r in rows: count[r.get(key) or _('Unassigned')]+=1; qty[r.get(key) or _('Unassigned')]+=r.get('done_qty') or r.get('requested_qty') or 0
        return [{'label':k,'count':count[k],'quantity':qty[k]} for k in count]

    @api.model
    def get_internal_transfer_analysis(self, filters):
        self._check_user_access(); pickings=self.env['stock.picking'].search(self._picking_domain(filters or {},'internal'), limit=5000); rows=self._pickings_to_rows(pickings,'internal_transfer'); line_rows=self._line_rows(pickings)
        return {'kpis':self._get_internal_transfer_kpis(filters or {}),'status_breakdown':self._breakdown(rows,'business_status'),'user_breakdown':self._breakdown(rows,'responsible_user'),'location_breakdown':self._breakdown(rows,'destination_location'),'operation_breakdown':self._breakdown(rows,'operation_type'),'requested_products':self._get_requested_product_analysis(filters or {}),'late_transfers':[r for r in rows if r['late_days']],'unfinished_transfers':[r for r in rows if r['status'] not in ('done','cancel')],'raw_pickings':rows,'raw_lines':line_rows,'charts':{'status':self._breakdown(rows,'business_status'),'operation':self._breakdown(rows,'operation_type')}}

    _get_internal_transfer_status_breakdown = lambda self, f: self.get_internal_transfer_analysis(f)['status_breakdown']
    _get_internal_transfer_user_breakdown = lambda self, f: self.get_internal_transfer_analysis(f)['user_breakdown']
    _get_internal_transfer_location_breakdown = lambda self, f: self.get_internal_transfer_analysis(f)['location_breakdown']
    _get_internal_transfer_operation_breakdown = lambda self, f: self.get_internal_transfer_analysis(f)['operation_breakdown']
    _get_internal_transfer_requested_products = lambda self, f: self.get_internal_transfer_analysis(f)['requested_products']
    _get_late_internal_transfers = lambda self, f: self.get_internal_transfer_analysis(f)['late_transfers']
    _get_unfinished_internal_transfers = lambda self, f: self.get_internal_transfer_analysis(f)['unfinished_transfers']
    _get_internal_transfer_raw_pickings = lambda self, f: self.get_internal_transfer_analysis(f)['raw_pickings']
    _get_internal_transfer_raw_lines = lambda self, f: self.get_internal_transfer_analysis(f)['raw_lines']

    @api.model
    def _get_receipt_kpis(self, filters):
        rows=self._pickings_to_rows(self.env['stock.picking'].search(self._picking_domain(filters,'receipt'), limit=5000),'receipt'); c=Counter(r['business_status'] for r in rows)
        return {'total_receipt_requests':len(rows),'draft_receipts':c['draft_request'],'waiting_approval':c['waiting_approval'],'approved_receipts':c['approved_ready'],'ready_to_receive':c['approved_ready'],'received_receipts':c['received_done'],'cancelled_receipts':c['cancelled'],'late_receipts':c['late'],'back_orders':c['back_order'],'unfinished_receipts':sum(1 for r in rows if r['status'] not in ('done','cancel')),'total_requested_qty':sum(r['requested_qty'] for r in rows),'total_received_qty':sum(r['done_qty'] for r in rows),'pending_qty':sum(r['pending_qty'] for r in rows)}

    @api.model
    def get_receipt_analysis(self, filters):
        self._check_user_access(); pickings=self.env['stock.picking'].search(self._picking_domain(filters or {},'receipt'), limit=5000); rows=self._pickings_to_rows(pickings,'receipt'); line_rows=self._line_rows(pickings)
        for row,p in zip(rows,pickings):
            row['vendor']=p.partner_id.display_name if self._model_has_field('stock.picking','partner_id') and p.partner_id else ''; row['purchase_order']=p.origin or ''
        return {'kpis':self._get_receipt_kpis(filters or {}),'status_breakdown':self._breakdown(rows,'business_status'),'user_breakdown':self._breakdown(rows,'responsible_user'),'location_breakdown':self._breakdown(rows,'destination_location'),'vendor_breakdown':self._breakdown(rows,'vendor'),'product_breakdown':self._get_requested_product_analysis(filters or {}),'late_receipts':[r for r in rows if r['late_days']],'unfinished_receipts':[r for r in rows if r['status'] not in ('done','cancel')],'raw_pickings':rows,'raw_lines':line_rows}

    _get_receipt_status_breakdown = lambda self, f: self.get_receipt_analysis(f)['status_breakdown']
    _get_receipt_user_breakdown = lambda self, f: self.get_receipt_analysis(f)['user_breakdown']
    _get_receipt_location_breakdown = lambda self, f: self.get_receipt_analysis(f)['location_breakdown']
    _get_receipt_vendor_breakdown = lambda self, f: self.get_receipt_analysis(f)['vendor_breakdown']
    _get_receipt_product_breakdown = lambda self, f: self.get_receipt_analysis(f)['product_breakdown']
    _get_late_receipts = lambda self, f: self.get_receipt_analysis(f)['late_receipts']
    _get_unfinished_receipts = lambda self, f: self.get_receipt_analysis(f)['unfinished_receipts']
    _get_receipt_raw_pickings = lambda self, f: self.get_receipt_analysis(f)['raw_pickings']
    _get_receipt_raw_lines = lambda self, f: self.get_receipt_analysis(f)['raw_lines']

    @api.model
    def get_unfinished_operations(self, filters):
        self._check_user_access(); rows=self._get_pending_operations(filters or {})
        return {'kpis':{'total_unfinished_operations':len(rows),'waiting_approval':sum(1 for r in rows if r['business_status']=='waiting_approval'),'waiting_availability':sum(1 for r in rows if r['business_status']=='waiting_availability'),'ready_not_done':sum(1 for r in rows if r['business_status']=='approved_ready'),'late':sum(1 for r in rows if r['late_days']),'back_orders':sum(1 for r in rows if r['back_order']),'oldest_unfinished_operation':rows[-1]['reference'] if rows else ''}, 'rows':rows, 'by_user':self._breakdown(rows,'responsible_user'), 'by_location':self._breakdown(rows,'destination_location'), 'by_operation_type':self._breakdown(rows,'operation_type')}

    @api.model
    def get_operation_type_monitor(self, filters):
        self._check_user_access(); rows=[]
        for pt in self.env['stock.picking.type'].search([]):
            picks=self.env['stock.picking'].search([('picking_type_id','=',pt.id),('company_id','in',self.env.companies.ids)], limit=5000); pr=self._pickings_to_rows(picks,'all')
            rows.append({'operation_type':pt.display_name,'to_process':sum(1 for r in pr if r['status'] not in ('done','cancel')),'waiting':sum(1 for r in pr if r['status'] in ('waiting','confirmed')),'ready':sum(1 for r in pr if r['status']=='assigned'),'late':sum(1 for r in pr if r['late_days']),'back_orders':sum(1 for r in pr if r['back_order']),'done_today':sum(1 for r in pr if r['done_date'] and r['done_date'][:10] == fields.Date.to_string(fields.Date.today())),'done_this_week':0,'done_this_month':sum(1 for r in pr if r['done_date'] and r['done_date'][:7] == fields.Date.to_string(fields.Date.today())[:7]),'average_processing_time':0,'requested_qty':sum(r['requested_qty'] for r in pr),'done_qty':sum(r['done_qty'] for r in pr),'pending_qty':sum(r['pending_qty'] for r in pr)})
        return {'rows':rows}

    @api.model
    def get_report_data(self, filters):
        self._check_user_access(); filters=filters or {}; report_type=filters.get('report_type','inventory_management_summary')
        data={'metadata':self._report_metadata(filters),'report_type':report_type,'sections':{}}
        section_map={
            'current_stock_by_location': lambda: {'Current Stock by Location': self._get_current_stock_by_location(filters), 'Low Stock': self._get_low_stock(filters), 'Out of Stock': self._get_out_of_stock(filters), 'Negative Stock': self._get_negative_stock(filters)},
            'historical_stock_as_of_date': lambda: {'Historical Stock': self.get_historical_stock_data(filters).get('rows',[])},
            'stock_movement_period_summary': lambda: {'Movement Summary': self.get_stock_movement_analysis(filters).get('rows',[]), 'Movement Trend': self._get_movement_trend(filters)},
            'consumption_used_location_report': lambda: {'Consumption Detail': self.get_consumption_analytics(filters).get('rows',[]), 'Consumption by Product': self.get_consumption_analytics(filters).get('by_product',[])},
            'branch_stock_report': lambda: {'Branch Stock': self.get_branch_analytics(filters).get('rows',[])},
            'operation_type_performance_report': lambda: {'Operation Type Performance': self.get_operation_type_monitor(filters).get('rows',[])},
            'internal_transfer_analysis_report': lambda: self._sections_from_analysis(self.get_internal_transfer_analysis(filters), 'Internal Transfers'),
            'receipt_analysis_report': lambda: self._sections_from_analysis(self.get_receipt_analysis(filters), 'Receipts'),
            'requested_product_report': lambda: {'Requested Products': self._get_requested_product_analysis(filters)},
            'waiting_approval_report': lambda: {'Waiting Approval': self._get_approval_analysis(filters)},
            'late_operations_report': lambda: {'Late Operations': self._get_late_operations(filters)},
            'back_order_report': lambda: {'Back Orders': self._get_backorder_analysis(filters)},
            'low_stock_report': lambda: {'Low Stock': self._get_low_stock(filters)},
            'out_of_stock_report': lambda: {'Out of Stock': self._get_out_of_stock(filters)},
            'negative_stock_report': lambda: {'Negative Stock': self._get_negative_stock(filters)},
            'quant_vs_ledger_difference_report': lambda: {'Quant vs Ledger': self._get_quant_vs_ledger_difference(filters)},
            'internal_transfer_report': lambda: {'Raw Internal Transfers': self.get_internal_transfer_analysis(filters).get('raw_pickings',[]), 'Raw Transfer Lines': self.get_internal_transfer_analysis(filters).get('raw_lines',[])},
            'scrap_waste_report': lambda: {'Scrap Waste': self._get_scrap_summary(filters)},
            'inventory_adjustment_report': lambda: {'Inventory Adjustments': self._get_adjustment_summary(filters)},
            'pending_operations_report': lambda: {'Pending Operations': self._get_pending_operations(filters)},
            'slow_moving_products_report': lambda: {'Slow Moving Products': self._get_slow_moving_products(filters)},
            'fast_moving_products_report': lambda: {'Fast Moving Products': self._get_fast_moving_products(filters)},
        }
        usage_roles={'kitchen_usage_report':'Kitchen','cafe_usage_report':'Cafe','pastry_usage_report':'Pastry','staff_meal_management_meal_report':'Staff Meal'}
        if report_type in usage_roles:
            rows=[r for r in self.get_consumption_analytics(filters).get('rows',[]) if usage_roles[report_type].lower() in (r.get('department') or '').lower()]
            data['sections']={usage_roles[report_type]+' Usage':rows}
        elif report_type in section_map: data['sections']=section_map[report_type]()
        else:
            data['sections']={'KPI Summary':[self._get_kpis(filters)],'Current Stock':self._get_current_stock_by_location(filters),'Movement Summary':self.get_stock_movement_analysis(filters).get('rows',[]),'Consumption Summary':self.get_consumption_analytics(filters).get('rows',[]),'Branch Summary':self.get_branch_analytics(filters).get('rows',[]),'Internal Transfer Summary':self.get_internal_transfer_analysis(filters).get('raw_pickings',[]),'Receipt Summary':self.get_receipt_analysis(filters).get('raw_pickings',[]),'Unfinished Operations':self.get_unfinished_operations(filters).get('rows',[]),'Quant vs Ledger':self._get_quant_vs_ledger_difference(filters)}
        if filters.get('include_raw_moves'): data['sections']['Raw Movements']=self._raw_movement_rows(filters)
        if filters.get('include_raw_pickings'): data['sections']['Raw Pickings']=self._pickings_to_rows(self.env['stock.picking'].search(self._picking_domain(filters), limit=5000),'all')
        return data

    def _sections_from_analysis(self, analysis, label):
        return {'KPI Summary':[analysis.get('kpis',{})],'Status Breakdown':analysis.get('status_breakdown',[]),'User Breakdown':analysis.get('user_breakdown',[]),'Location Breakdown':analysis.get('location_breakdown',[]),'Operation Type Breakdown':analysis.get('operation_breakdown',[]),'Requested Products':analysis.get('requested_products') or analysis.get('product_breakdown',[]),'Late '+label:analysis.get('late_transfers') or analysis.get('late_receipts',[]),'Back Orders':[r for r in analysis.get('raw_pickings',[]) if r.get('back_order')],'Waiting Approval':[r for r in analysis.get('raw_pickings',[]) if r.get('business_status')=='waiting_approval'],'Unfinished '+label:analysis.get('unfinished_transfers') or analysis.get('unfinished_receipts',[]),'Raw '+label:analysis.get('raw_pickings',[]),'Raw Lines':analysis.get('raw_lines',[])}

    @api.model
    def get_grouped_report_data(self, filters):
        self._check_user_access(); filters=filters or {}; group_by=filters.get('group_by','product'); rows=self.get_report_data(filters).get('sections',{}); all_rows=[]
        for vals in rows.values():
            if isinstance(vals, list): all_rows += [v for v in vals if isinstance(v, dict)]
        grouped=defaultdict(lambda:{'count':0,'quantity':0.0})
        key_map={'product':'product','product_category':'category','location':'location','source_location':'source_location','destination_location':'destination_location','operation_type':'operation_type','responsible_user':'responsible_user','movement_status':'status','business_status':'business_status','department':'department','branch':'branch','requested_by':'requested_by','approved_by':'approved_by'}
        key_name=key_map.get(group_by, group_by)
        for row in all_rows:
            key=row.get(key_name) or _('Unassigned'); grouped[key]['count']+=1; grouped[key]['quantity']+=row.get('quantity') or row.get('quantity_used') or row.get('done_qty') or row.get('on_hand') or 0
        return [{'group':k, **v} for k,v in grouped.items()]

    def _report_metadata(self, filters): return {'company': self.env.company.display_name, 'generated_by': self.env.user.display_name, 'generated_at': fields.Datetime.to_string(fields.Datetime.now()), 'timezone': self._settings()['default_report_timezone'], 'filters': filters}

    def _raw_movement_rows(self, filters):
        qty_field=self.env['stock.analytics.history.service'].get_quantity_field(); rows=[]
        for line in self.env['stock.move.line'].search(self._move_line_domain(filters), limit=10000): rows.append({'reference':line.reference,'product':line.product_id.display_name,'category':line.product_id.categ_id.display_name,'source_location':line.location_id.display_name,'destination_location':line.location_dest_id.display_name,'quantity':line[qty_field] or 0,'uom':line.product_uom_id.name,'date':fields.Datetime.to_string(line.date),'status':line.state})
        return rows

    @api.model
    def _get_kpis(self, filters):
        stock=self._get_stock_on_hand(filters); cons=self.get_consumption_analytics(filters).get('kpis',{}); it=self._get_internal_transfer_kpis(filters); rec=self._get_receipt_kpis(filters); unfinished=self.get_unfinished_operations(filters).get('kpis',{})
        return {**stock,'low_stock_products':len(self._get_low_stock(filters)),'out_of_stock_products':len(self._get_out_of_stock(filters)),'negative_stock_products':len(self._get_negative_stock(filters)),'total_used_consumed_quantity':cons.get('total_used_quantity',0),'most_consumed_product':cons.get('most_consumed_product',''),'total_internal_transfer_requests':it.get('total_internal_transfer_requests',0),'waiting_approval_transfers':it.get('waiting_approval',0),'unfinished_transfers':it.get('unfinished_transfers',0),'total_receipts':rec.get('total_receipt_requests',0),'unfinished_receipts':rec.get('unfinished_receipts',0),'late_receipts':rec.get('late_receipts',0),'pending_transfers':it.get('unfinished_transfers',0),'late_transfers':it.get('late_transfers',0),'back_orders':it.get('back_orders',0)+rec.get('back_orders',0),'total_received_quantity':rec.get('total_received_qty',0),'total_internal_transfer_quantity':it.get('total_done_qty',0),'unfinished_operations':unfinished.get('total_unfinished_operations',0)}
