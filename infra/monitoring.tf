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

# alert-on-dead-backend: five alerts existed and none could tell "dead" from "quiet" —
# market-data served zero 2xx for nine hours on 10-11 August and nothing below fired.

resource "azurerm_monitor_metric_alert" "market_data_5xx" {
  name                = "alert-market-data-http-5xx"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_linux_web_app.market_data.id]
  description         = "market-data is answering with 5xx."
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

# `alert-gateway-http-5xx` above only ever scoped the gateway — market-data can and does
# emit 5xx (one was recorded at 05:20 during the 10-11 August investigation) and had no
# rule of its own.
resource "azurerm_monitor_metric_alert" "market_data_requests_low" {
  name                = "alert-market-data-requests-low"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_linux_web_app.market_data.id]
  description         = "market-data answered zero requests in the last 30 minutes — the baseline the night before the 10 August outage was ~360/hour."
  severity            = 1
  frequency           = "PT15M"
  window_size         = "PT30M"

  criteria {
    metric_namespace = "Microsoft.Web/sites"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "LessThanOrEqual"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

# Zero requests and a dead container look the same from this metric alone — an idle
# healthy process also answers zero. `market_data_ping` below is what tells them apart:
# an external probe that reaches the container itself, on a path Easy Auth cannot gate
# (app-service.tf, `excluded_paths`), since a dead container and a live one both answer
# Easy Auth's own 401 identically.
resource "azurerm_application_insights_standard_web_test" "market_data_ping" {
  name                    = "webtest-market-data-ping"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  application_insights_id = azurerm_application_insights.main.id
  enabled                 = true
  retry_enabled           = true
  # One location, the cheapest configuration that still proves the container answers a
  # real external request — this is a liveness probe, not a latency-by-region survey.
  geo_locations = ["emea-nl-ams-azr"]
  frequency     = 900
  timeout       = 30

  request {
    url = "https://${local.market_data_hostname}/ping"
  }

  validation_rules {
    expected_status_code = 200
  }
}

resource "azurerm_monitor_metric_alert" "market_data_availability" {
  name                = "alert-market-data-availability"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_application_insights.main.id]
  description         = "market-data's /ping availability test is failing from outside."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT15M"

  application_insights_web_test_location_availability_criteria {
    web_test_id           = azurerm_application_insights_standard_web_test.market_data_ping.id
    component_id          = azurerm_application_insights.main.id
    failed_location_count = 1
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

# The 45x UndefinedColumnError storm on 10 August (migration 0007 landing after the code
# that needed it) killed ingest for 23 minutes and self-resolved with nothing firing.
# Threshold picked from what the same night measured on the other side: ConnectionClosedError
# from the gateway WebSocket reconnecting is normal churn — 736 times over 30h, ~6.1 per
# 15-minute window — and the storm was ~29 per 15-minute window at the same rate. 15 sits
# roughly between the two; see design.md (alert-on-dead-backend) for the arithmetic and the
# caveat that it is an estimate from one night, not a tuned value.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "app_exceptions_high" {
  name                 = "alert-app-exceptions-high"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  scopes               = [azurerm_log_analytics_workspace.main.id]
  description          = "Exception volume across both apps is above the measured reconnect-churn baseline."
  severity             = 2
  evaluation_frequency = "PT15M"
  window_duration      = "PT15M"

  criteria {
    query                   = "AppExceptions | summarize AggregatedValue = count()"
    time_aggregation_method = "Count"
    threshold               = 15
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.operator.id]
  }
}
