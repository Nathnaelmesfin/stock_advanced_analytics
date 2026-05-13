/** @odoo-module **/

import { registry } from "@web/core/registry";

export const stockAnalyticsService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        return {
            bootstrap() { return orm.call("stock.analytics.service", "get_dashboard_bootstrap_data", []); },
            load(mode, filters = {}) {
                const methodByMode = {
                    live_dashboard: "get_dashboard_data",
                    stock_by_location: "get_stock_by_location_data",
                    historical_stock: "get_historical_stock_data",
                    stock_movement_analysis: "get_stock_movement_analysis",
                    internal_transfer_analysis: "get_internal_transfer_analysis",
                    receipts_analysis: "get_receipt_analysis",
                    consumption_analytics: "get_consumption_analytics",
                    branch_analytics: "get_branch_analytics",
                    operation_type_monitor: "get_operation_type_monitor",
                    unfinished_operations: "get_unfinished_operations",
                };
                return orm.call("stock.analytics.service", methodByMode[mode] || "get_dashboard_data", [filters]);
            },
        };
    },
};
registry.category("services").add("stockAnalytics", stockAnalyticsService);
