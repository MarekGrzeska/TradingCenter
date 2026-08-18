# easy-auth-app

The Entra registration behind one App Service's Easy Auth: an application, a service
principal, and the client secret Easy Auth reads as
`MICROSOFT_PROVIDER_AUTHENTICATION_SECRET`. Six apps had it written out by hand — three of
them with a delegated scope, three without — and adding a seventh module meant copying
about thirty lines and hoping nothing was left out. Something was, once:
`requested_access_token_version` went missing from `market-mcp` on 13 August 2026 and cost
an interrupted apply, because that app needed the `api` block for nothing but the version.

The App Service blocks themselves stay written out. They differ for real, and half of
`app-service.tf` is dated incident comments a `for_each` could not carry.

## Applying this is the operator's, not CI's

Every resource here is `azuread_*`, and the CI principal holds `Application.Read.All`, not
write — `terraform-apply.yml` refuses any plan touching them on purpose. So a change in this
module is applied locally.

## The one thing to check before applying

The secret. `azuread_application_password` recreated rather than moved means Easy Auth on
that app rejects every token until the next apply lands, and six of them at once is six
applications refusing the operator. Any plan touching this module must read
`0 to add, 0 to change, 0 to destroy` for the resources it moves; anything else is a state
move that did not take, not a change to review.
