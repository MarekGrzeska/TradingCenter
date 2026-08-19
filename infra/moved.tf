# State moves, not changes. Each block below tells Terraform that a resource it already
# tracks now lives inside `modules/easy-auth-app` — without them it would plan a destroy and
# a create for all twenty, and for the six `azuread_application_password` resources that
# means six Easy Auth secrets rotated while six applications are still configured with the
# old one. Every token refused until the next apply.
#
# `moved` rather than twenty `terraform state mv` invocations: declarative, idempotent, and
# visible in the pull request, where CI's own plan runs before anybody applies anything.
#
# The gate this file exists to pass: `terraform plan` must read
# `0 to add, 0 to change, 0 to destroy` for these resources. Anything else is a move that
# did not take.
#
# These blocks can be deleted once the move has been applied and the state reflects it —
# they are a one-time instruction, not a permanent part of the configuration. Keeping them
# costs nothing and documents where these came from, so they stay until the change
# is archived. Four have gone already, and not because they were applied: they named
# market-mcp's Easy Auth triplet and its Key Vault policy, and that module is a route in
# market-data now — a move to an address that no longer exists says nothing to anybody.

moved {
  from = azuread_application.market_data_easy_auth
  to   = module.market_data_easy_auth.azuread_application.this
}

moved {
  from = azuread_service_principal.market_data_easy_auth
  to   = module.market_data_easy_auth.azuread_service_principal.this
}

moved {
  from = azuread_application_password.market_data_easy_auth
  to   = module.market_data_easy_auth.azuread_application_password.this
}

moved {
  from = random_uuid.market_data_scope
  to   = module.market_data_easy_auth.random_uuid.scope[0]
}

moved {
  from = azuread_application.trading_mcp_easy_auth
  to   = module.trading_mcp_easy_auth.azuread_application.this
}

moved {
  from = azuread_service_principal.trading_mcp_easy_auth
  to   = module.trading_mcp_easy_auth.azuread_service_principal.this
}

moved {
  from = azuread_application_password.trading_mcp_easy_auth
  to   = module.trading_mcp_easy_auth.azuread_application_password.this
}

moved {
  from = azuread_application.teams_mcp_easy_auth
  to   = module.teams_mcp_easy_auth.azuread_application.this
}

moved {
  from = azuread_service_principal.teams_mcp_easy_auth
  to   = module.teams_mcp_easy_auth.azuread_service_principal.this
}

moved {
  from = azuread_application_password.teams_mcp_easy_auth
  to   = module.teams_mcp_easy_auth.azuread_application_password.this
}

moved {
  from = azuread_application.agent_easy_auth
  to   = module.agent_easy_auth.azuread_application.this
}

moved {
  from = azuread_service_principal.agent_easy_auth
  to   = module.agent_easy_auth.azuread_service_principal.this
}

moved {
  from = azuread_application_password.agent_easy_auth
  to   = module.agent_easy_auth.azuread_application_password.this
}

moved {
  from = random_uuid.agent_scope
  to   = module.agent_easy_auth.random_uuid.scope[0]
}

moved {
  from = azuread_application.teams_easy_auth
  to   = module.teams_easy_auth.azuread_application.this
}

moved {
  from = azuread_service_principal.teams_easy_auth
  to   = module.teams_easy_auth.azuread_service_principal.this
}

moved {
  from = azuread_application_password.teams_easy_auth
  to   = module.teams_easy_auth.azuread_application_password.this
}

moved {
  from = random_uuid.teams_scope
  to   = module.teams_easy_auth.random_uuid.scope[0]
}

# And the seven Key Vault grants, which were the same three lines seven times over.

moved {
  from = azurerm_key_vault_access_policy.capital_gateway
  to   = azurerm_key_vault_access_policy.apps["capital-gateway"]
}

moved {
  from = azurerm_key_vault_access_policy.market_data
  to   = azurerm_key_vault_access_policy.apps["market-data"]
}

moved {
  from = azurerm_key_vault_access_policy.agent
  to   = azurerm_key_vault_access_policy.apps["agent"]
}

moved {
  from = azurerm_key_vault_access_policy.teams
  to   = azurerm_key_vault_access_policy.apps["teams"]
}

moved {
  from = azurerm_key_vault_access_policy.trading_mcp
  to   = azurerm_key_vault_access_policy.apps["trading-mcp"]
}

moved {
  from = azurerm_key_vault_access_policy.teams_mcp
  to   = azurerm_key_vault_access_policy.apps["teams-mcp"]
}

# --- agent-and-teams-one-workbench ----------------------------------------------------
#
# Renames, not replacements. `agent` and `teams` became one process, and the App Service
# that serves it is the one `agent` already had — its name is an identity here rather than
# a label (`local.workbench_app_name`). Without the blocks below Terraform reads a rename
# as a destroy and a create, which for the Easy Auth application means **a new client id**:
# the terminal's build holds that id, and so do three allow-lists. Every sign-in refused
# until somebody noticed.

moved {
  from = azurerm_linux_web_app.agent
  to   = azurerm_linux_web_app.workbench
}

moved {
  from = module.agent_easy_auth
  to   = module.workbench_easy_auth
}

moved {
  from = azuread_application_pre_authorized.agent_terminal
  to   = azuread_application_pre_authorized.workbench_terminal
}

moved {
  from = azurerm_postgresql_flexible_server_firewall_rule.agent_outbound
  to   = azurerm_postgresql_flexible_server_firewall_rule.workbench_outbound
}
