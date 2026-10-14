# The two APIs a browser asks for a token for, and the names both sides agree on. The applications check these tokens
# themselves (`packages/tc-entra-auth`): the audience is the identifier URI below, or the registration's client id for a
# v2 token, and the server's `*_ENTRA_AUDIENCES` lists both.

locals {
  workbench_api_uri   = "api://tradingcenter-agent"
  workbench_api_scope = "access_as_user"

  capital_gateway_api_uri   = "api://tradingcenter-capital-gateway"
  capital_gateway_api_scope = "access_as_user"

  # Microsoft's own well-known registration for the Azure CLI: the operator's only client for the door to Telegram,
  # which has no screen. `/telegram`'s bots and destinations are the only routes it reaches.
  azure_cli_client_id = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
}

# The gateway's API: the terminal reads the account from it with the operator's own token.
module "capital_gateway_easy_auth" {
  source = "./modules/easy-auth-app"

  display_name   = "app-tradingcenter-gateway-easyauth"
  identifier_uri = local.capital_gateway_api_uri

  scope = {
    value                      = local.capital_gateway_api_scope
    admin_consent_display_name = "Read the demo account"
    admin_consent_description  = "Allows the app to read and fund the capital.com demo account as the signed-in operator."
    user_consent_display_name  = "Read your demo account"
    user_consent_description   = "Allows the app to read and fund your capital.com demo account."
  }
}
