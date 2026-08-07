# fixtures

Provider payloads, kept verbatim. A test that asserts against a hand-tidied payload
proves the tidying, not the mapping.

| Origin | Files |
|---|---|
| Recorded from the capital.com demo API | everything except the three below |
| Hand-written from the documented shape | `navigation_root.json`, `navigation_commodities.json`, `navigation_metals.json` |

The navigation fixtures are the exception because neither spike recorded the market
tree: `broker-gateway` mocked it inline in its tests, and the streaming spike never
walked it. The market entries inside them are copied from a recorded search response,
so only the tree structure — nodes pointing at nodes — is invented. That structure is
what the traversal is tested against: a nested node, a market appearing under two
branches, and a leaf.

Re-record with `--run-live` credentials rather than editing one by hand: a field
adjusted to make a test pass is a field the provider never sent.
