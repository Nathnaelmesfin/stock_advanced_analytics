import werkzeug
from odoo import http, _
from odoo.exceptions import AccessError
from odoo.http import request


class StockAnalyticsController(http.Controller):
    @http.route('/stock_advanced_analytics/xlsx/<int:wizard_id>', type='http', auth='user')
    def download_xlsx(self, wizard_id, **kwargs):
        if not request.env.user.has_group('stock_advanced_analytics.group_stock_analytics_user'):
            raise AccessError(_('You are not allowed to export Inventory Analytics reports.'))
        wizard = request.env['stock.analytics.report.wizard'].browse(wizard_id).exists()
        if not wizard:
            return request.not_found()
        try:
            content = request.env['report.stock_advanced_analytics.stock_excel_report'].generate_xlsx(wizard)
        except Exception as exc:
            return werkzeug.wrappers.Response(str(exc), status=500, content_type='text/plain; charset=utf-8')
        filename = f"inventory_analytics_{wizard.report_type}.xlsx"
        headers = [('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'), ('Content-Disposition', http.content_disposition(filename)), ('Content-Length', len(content))]
        return request.make_response(content, headers=headers)
