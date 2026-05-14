{
    'name': 'Inventory Advanced Analytics Dashboard',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Location-aware inventory analytics, movement ledgers, consumption, branch, operation, PDF and Excel reports.',
    'description': '''
Inventory Advanced Analytics Dashboard for Odoo 17.

Provides movement-ledger stock analytics, current stock by location, historical stock, consumption analytics from used locations, branch analytics, internal transfer and receipt monitoring, operation status dashboards, low/out/negative stock alerts, PDF and Excel reporting, opening balances, mapping configuration, and multi-company-safe security.
    ''',
    'author': 'OpenAI',
    'depends': ['base', 'product', 'stock', 'uom', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'reports/stock_analytics_report_action.xml',
        'reports/stock_analytics_pdf_template.xml',
        'views/stock_analytics_rule_views.xml',
        'views/stock_analytics_location_map_views.xml',
        'views/stock_analytics_operation_map_views.xml',
        'views/stock_analytics_status_map_views.xml',
        'views/stock_analytics_opening_balance_views.xml',
        'views/stock_analytics_report_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'data/dashboard_actions.xml',
        'views/stock_analytics_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_advanced_analytics/static/src/js/stock_analytics_service.js',
            'stock_advanced_analytics/static/src/js/stock_analytics_dashboard.js',
            'stock_advanced_analytics/static/src/xml/stock_analytics_dashboard.xml',
            'stock_advanced_analytics/static/src/scss/stock_analytics_dashboard.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
