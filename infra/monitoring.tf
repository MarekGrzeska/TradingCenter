# Application Insights, workspace-based (the classic, non-workspace mode is deprecated
# for new resources). market-data emits `market_data.candle_age_seconds` onto it
# (market_data/telemetry.py) — the metric every alert below that mentions staleness
# depends on existing before it can be alerted on.
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  # Free tier ships 5 GB/month; a single-operator project with two low-traffic services
  # does not come close, so no daily cap is set here.
  retention_in_days = 30
}

resource "azurerm_application_insights" "main" {
  name                = "appi-tradingcenter"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
}

output "application_insights_connection_string" {
  sensitive = true
  value     = azurerm_application_insights.main.connection_string
}

# One operator, one address — not a distribution list, because there is exactly one
# person to page.
resource "azurerm_monitor_action_group" "operator" {
  name                = "ag-tradingcenter-operator"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "tc-operator"

  email_receiver {
    name          = "operator"
    email_address = var.operator_email
  }
}

# The candle-age metric (market_data/telemetry.py) already excludes any pair whose
# market the gateway says is closed — so "w godzinach handlu" (design.md, group 10) is
# encoded in what the metric reports, not in when this alert is allowed to fire.
#
# Stands on `market_data.candle_age_periods`, not `..._seconds`: a healthy `DAY` pair
# sits near 86,400 raw seconds old and a healthy `WEEK` pair near 604,800 — one second
# threshold could not be both blind to slow resolutions and quiet on fast ones, and
# `..._seconds` spent nine hours firing continuously as a result (openspec/changes/
# candle-age-alert-in-periods). The periods metric is `(age − DELIVERY_GRACE) / period`
# per pair, so one threshold means the same thing at every resolution. Three periods:
# one more than the module's own STALLED threshold (`STALE_AFTER_PERIODS` in
# tracking.py), so the production safety net is deliberately blunter than the per-pair
# indicator, not a second copy of it. `..._seconds` stays published for the portal —
# periods are what to alert on, seconds are what a human reads once alerted.
resource "azurerm_monitor_metric_alert" "candle_age" {
  name                = "alert-candle-age-stale"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_application_insights.main.id]
  description         = "A tracked pair's newest candle is more than 3 periods late (past its delivery grace) while its market is open."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "azure.applicationinsights"
    metric_name      = "market_data.candle_age_periods"
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

# `connections_failed` is Postgres Flexible Server's own platform metric — any failed
# connection attempt in the window is worth knowing about on a single-operator database
# with a handful of expected connections, not just a spike.
resource "azurerm_monitor_metric_alert" "database_unreachable" {
  name                = "alert-database-connections-failed"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "The database is refusing or failing connection attempts."
  severity            = 0
  frequency           = "PT5M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "connections_failed"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

resource "azurerm_monitor_metric_alert" "database_storage" {
  name                = "alert-database-storage-high"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  description         = "The database is over 80% of its 32GB — design.md's risk: local work and production share this one server, and dev data counts against the same free-tier limit."
  severity            = 2
  frequency           = "PT1H"
  window_size         = "PT1H"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

resource "azurerm_monitor_metric_alert" "plan_memory" {
  name                = "alert-plan-memory-high"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_service_plan.main.id]
  description         = "The B1 plan both apps share is over 92% memory."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.Web/serverfarms"
    metric_name      = "MemoryPercentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 92
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

resource "azurerm_monitor_metric_alert" "gateway_5xx" {
  name                = "alert-gateway-http-5xx"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_linux_web_app.capital_gateway.id]
  description         = "capital-gateway is answering with 5xx."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.Web/sites"
    metric_name      = "Http5xx"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

# No CPU alert on the plan, deliberately (design.md, group 10) — on a B1, CPU spikes on
# every backfill and a threshold tight enough to mean anything would fire on ordinary
# collection, not on a problem. This comment is the confirmation task 10.7 asks for:
# there is no `azurerm_monitor_metric_alert` for Percentage CPU in this file, and there
# should not be one.
