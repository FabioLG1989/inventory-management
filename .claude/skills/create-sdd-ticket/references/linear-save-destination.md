# Linear save destination

Load this reference before any `--save-to-linear` write.

The live Linear MCP tool schema is authoritative for tool names, argument names,
required fields, and response shapes; inspect it before each operation instead of
relying on remembered contracts. Require an authenticated project-scoped Linear
MCP server — if it is missing, disconnected, or unauthorized, stop with a setup
error and never fall back to an SDK, REST, or GraphQL transport. Preserve
descriptions and comments as native Markdown, and preserve unspecified fields
when updating.

## Inputs

- `--from-linear <ISSUE-ID> --save-to-linear [URL]` updates that exact issue.
  The URL is optional. If supplied, it must identify the existing issue's own
  team or project; never use it to retarget the issue.
- Text, Markdown, or Jira input with `--save-to-linear` creates a Linear issue
  and requires a destination URL.

Accept only HTTPS URLs on `linear.app` with one of these path shapes:

- `/<workspace>/team/<KEY>/...`
- `/<workspace>/project/<slug>`

Reject bare keys, bare slugs, issue URLs used as destinations, malformed paths,
and non-Linear URLs.

## Update an existing Linear issue

1. Fetch `--from-linear` and retain its internal ID, team, project, and URL.
2. If a destination URL is present, resolve and validate it against that issue.
   Stop on any team, project, or workspace mismatch.
3. Save using the retained issue ID. Do not omit the ID or call a create path.
4. Verify the returned identifier is unchanged.

## Create in a team

1. Extract the workspace and team key from the URL.
2. Resolve the team key with the MCP team lookup and use its returned ID.
3. Save the issue with that team ID and no inferred project.
4. Compare the workspace in the returned issue URL with the requested workspace.
   On mismatch, report the failure and returned URL.

## Create in a project

1. Extract the workspace and project slug from the URL.
2. Resolve the project before writing.
3. Validate the resolved project's URL against the requested workspace.
4. Resolve a team from the project response; stop if none or multiple candidates
   remain ambiguous.
5. Save with both resolved project and team IDs.
6. Verify the returned issue URL belongs to the requested workspace and project.

## Failure handling

- Missing issue: report the exact identifier and stop.
- Missing or ambiguous team or project: show the resolved candidates and stop.
- Schema mismatch: re-inspect the active MCP tool schema; do not invent an
  argument or switch transport.
- Workspace mismatch after a write: report the returned issue URL and the
  expected workspace. Do not claim success.

Return the resulting issue identifier and canonical Linear URL after any write.
