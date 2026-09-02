# Application Insights, workspace-based, since the classic mode is deprecated for new resources. market-data emits
# `market_data.candle_age_seconds` onto it, which every staleness alert below depends on existing.
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

# Stands on `market_data.candle_age_periods`, not `..._seconds`: a healthy `DAY` pair is 86,400 raw seconds old, so one
# threshold could not be blind to slow resolutions and quiet on fast ones — three periods, blunter than the indicator.
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

# `connections_failed` is the server's own platform metric — any failed attempt in the window is worth knowing about on
# a single-operator database with a handful of expected connections, not just a spike.
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

# The one question the platform's metrics cannot answer: whether the container is alive. An idle healthy process and a
# dead one both report zero requests, which is how market-data served no 2xx for nine hours with five alerts standing.
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
  # Both ids, not just the component's — this alert type refuses with a bare "Alert scope is invalid" 400 unless the
  # web test itself is in scopes alongside the Application Insights resource.
  scopes = [
    azurerm_application_insights_standard_web_test.market_data_ping.id,
    azurerm_application_insights.main.id,
  ]
  description = "market-data's /ping availability test is failing from outside."
  severity    = 1
  frequency   = "PT5M"
  window_size = "PT15M"

  application_insights_web_test_location_availability_criteria {
    web_test_id           = azurerm_application_insights_standard_web_test.market_data_ping.id
    component_id          = azurerm_application_insights.main.id
    failed_location_count = 1
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}

# A loop that stops is the failure mode nothing here reported: it holds no connection, answers no request and raises
# nothing, so the process stays up, `/ping` stays green and the archive quietly stops growing. Measured in market-data
# on 24 August 2026 — one stream room silent for fourteen hours — and fixed there alone until 2 September.
#
# The metric is in *passes of the loop's own interval*, for the reason `candle_age_periods` is in periods: a sampling
# pass every minute and a collection every five are both healthy, and one threshold in seconds would be wrong for one
# of them. Three, matching the candle alert: two is a restart landing badly, three is a loop that stopped.
locals {
  # The modules with a loop worth watching, and the metric each one publishes. telegram-gateway is deliberately absent:
  # its watcher is a long poll per adopted bot, so a gateway with no bots has no loop, and silence there is a supported
  # state rather than a failure — an alert on it would fire on the day the operator has bound nothing.
  loop_alerts = {
    polymarket-data = "polymarket_data.loop_passes_late"
    social-data     = "social_data.loop_passes_late"
    strategy        = "strategy.loop_passes_late"
  }
}

resource "azurerm_monitor_metric_alert" "loop_stopped" {
  for_each = local.loop_alerts

  name                = "alert-${each.key}-loop-stopped"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_application_insights.main.id]
  description         = "A loop in ${each.key} has not finished a pass in three of its own intervals."
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "azure.applicationinsights"
    metric_name      = each.value
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = azurerm_monitor_action_group.operator.id
  }
}
