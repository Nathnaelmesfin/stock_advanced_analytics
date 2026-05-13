/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class KpiCard extends Component { static template = "stock_advanced_analytics.KpiCard"; }
export class DataTable extends Component {
    static template = "stock_advanced_analytics.DataTable";
    get rows() { return Array.isArray(this.props.rows) ? this.props.rows : []; }
    get headers() { return this.rows.length ? Object.keys(this.rows[0]) : []; }
}
export class BarChart extends Component {
    static template = "stock_advanced_analytics.BarChart";
    get rows() { return Array.isArray(this.props.rows) ? this.props.rows.slice(0, 12) : []; }
    get maxValue() { return Math.max(1, ...this.rows.map((r) => Number(r.value || r.quantity || r.count || 0))); }
}
export class DonutChart extends Component { static template = "stock_advanced_analytics.DonutChart"; }
export class LineChart extends Component { static template = "stock_advanced_analytics.LineChart"; }
export class HeatmapChart extends Component { static template = "stock_advanced_analytics.HeatmapChart"; }

export class StockAnalyticsDashboard extends Component {
    static template = "stock_advanced_analytics.Dashboard";
    static components = { KpiCard, DataTable, BarChart, DonutChart, LineChart, HeatmapChart };
    setup() {
        this.analytics = useService("stockAnalytics");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({ loading: true, error: null, bootstrap: {}, data: {}, mode: this.props.action?.context?.mode || "live_dashboard", filters: {}, refreshTimer: null });
        onWillStart(async () => { await this.loadBootstrap(); await this.loadData(); });
        onWillUnmount(() => { if (this.state.refreshTimer) clearInterval(this.state.refreshTimer); });
    }
    async loadBootstrap() {
        this.state.bootstrap = await this.analytics.bootstrap();
        const interval = Math.max(30, Number(this.state.bootstrap.settings?.auto_refresh_interval || 300)) * 1000;
        this.state.refreshTimer = setInterval(() => this.loadData(true), interval);
    }
    async loadData(silent = false) {
        this.state.loading = !silent; this.state.error = null;
        try { this.state.data = await this.analytics.load(this.state.mode, this.cleanFilters()); }
        catch (error) { this.state.error = error.message || String(error); this.notification.add(this.state.error, { type: "danger" }); }
        finally { this.state.loading = false; }
    }
    cleanFilters() { return Object.fromEntries(Object.entries(this.state.filters).filter(([, v]) => v !== "" && v !== null && v !== undefined)); }
    async setMode(mode) { this.state.mode = mode; await this.loadData(); }
    async applyFilters(ev) { ev.preventDefault(); await this.loadData(); }
    async openReports() { await this.action.doAction("stock_advanced_analytics.action_stock_analytics_report_wizard"); }
    get modeTitle() { return (this.state.mode || "").replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase()); }
    get kpis() { return this.state.data.kpis || {}; }
    get mainRows() {
        const d = this.state.data;
        return d.rows || d.current_stock || d.raw_pickings || d.unfinished_transfers || d.raw_lines || d.status_breakdown || [];
    }
    get secondaryRows() {
        const d = this.state.data;
        return d.by_product || d.movement_trend || d.status_breakdown || d.summary || d.top_used || [];
    }
}
registry.category("actions").add("stock_advanced_analytics.dashboard", StockAnalyticsDashboard);
