# Telemetry UI design

API Builder is a compact workspace for configuring API entities.
Its existing visual identity is retained. Entity config uses `/api-builder/entity-config`;
legacy Work Organizer routes remain available.

## Source ownership

`src/theme/theme.css` owns base tokens and shared layout classes.
`src/theme/telemetry.css` owns the compact telemetry variant, including `tm-*`
composition. `src/styles.css` contains application overrides. Angular loads them
once, in that order. `src/theme/components.ts` owns the standalone card, spinner,
and text-input primitives used by pages. Keep behavior and API access in the
application components and services.

## Visual contract

- Use the system font, pale gray canvas, white compact header and pale gray (#eef1f4) cards matching kanban columns, green
  primary actions and active navigation, and visible keyboard focus.
- Preserve 4px radii and base 0.07em tracking. Retain the existing telemetry typography; the account trigger also uses a 4px radius.
- Keep the shell outside content cards. Header navigation contains Entity config, Routing, Authentication and Vector search; Preferences is in the account popup.
- Keep desktop boards in three status columns and stack them on narrow screens.
  The document list and reader also stack on narrow screens.
- Keep overlays in the browser top layer, constrain menus to the viewport, and
  preserve Escape dismissal, focus restoration and reduced-motion behavior.

## Icons

Use the shared decorative `WoIconComponent` outline icons before header and action
labels. Keep visible text; icons use currentColor and are hidden from accessibility
trees. Save uses a tick, add a plus, edit a pencil, remove a trash can. Navigation
icons are 14px, compact action icons 12px; preserve button heights and 4px radii.

## Projects

Projects is the first menu and landing page at `/api-builder/projects`. Match the
Entity config 35/65 split, gray containers, white cards, 28px input and compact
Save action. Collect a required name and summary. Show the active project on its
card and right-aligned beside the shared page title on every API Builder screen; provide Make active on other cards. Use primary green
borders for both the active card and page-title project control, with the telemetry
lock on a borderless circular background after the page-title project name; the header
border surrounds only the name. The browser favicon repeats the
header robot. Restore the selected
valid ID, otherwise select Default. Configuration routes require a loaded active
project, including direct URL visits. Project catalog failures offer retry here.
Names and summaries persist through the backend. Entity names and saved RBAC are
project-scoped; routing, authentication and search drafts use per-project service
instances for this session. Switching project happens on the Projects page.

## Entity config

Use a 35/65 desktop split and a single column on narrow screens. The left panel
uses a 28px name input and adjacent creation button, followed by compact definition
section for the selected entity. Creating an entity replaces the left editor; select a right-card name to return to another entity without losing its prompt. Each definition starts at three rows. The right panel
wraps all entities in one gray card with white individual cards, three per row.
Show only attribute names, schema types and Required/Optional. Omit descriptions,
relationship prose and mock explanations. Titles use 13px monospace; attribute rows
use 11px monospace. Add rules below card titles and every attribute, and after each
left-side entity section. Entity Edit/Delete actions sit right-aligned in each right-card title row using compact 24px controls. Attribute Edit
and Delete are inline text-link buttons; Edit opens the existing native dialog
pattern for name/type/Required with Save/Cancel and inline errors. Disable edits
while saving, and retain drafts on errors.

Entity names and definitions persist through project-owned API requests. Generate
configuration drafts/reviews schema only and displays safe current-run agent logs
below that entity's button, separated by a rule. All displayed agent logs follow appended events to the bottom. Poll independently per entity, finish the previous
run's final read, reject stale responses, and cancel polling on destruction. Logs
use a bounded monospace scrolling region; generated attributes remain on the right.
Prompt updates include the saved schema and preserve unrequested details. Build
alone invokes the implementation agent and isolated Docker validation. No production
authentication or infrastructure generation is introduced.

## Routing

`/api-builder/routing` configures session-only route drafts with a 35% editor
and 65% route list. The editor has Route type, Route path and Prompt;
inputs/selects are 28px tall, matching Entity config, and the prompt is three rows.
Use compact green actions, gray containers, white cards and 4px radii. Group cards
by entity without visible group or list headings; show two white route cards per row.
Place access policy above the method, use monospace paths and right-aligned 24px
Edit/Remove buttons top-aligned alongside the type/access line, above the path. Saved entities seed /{lowercase-name}/list, /get, /create, /update and
/delete once per session; edits/deletions survive in-app navigation. Custom routes
have no HTTP method until generation. Route execution and persistence remain future
work. Architecture and acceptance criteria: `.codex/docs/tasks/entity-route-defaults/plan.md`.
Verify changes quickly on desktop using the existing Chrome flow; no mobile checks.

## Interaction contract

Use native links for navigation and buttons for actions. Retain labels, focus
indicators, accessible loading status, disabled/busy controls, and explicit error,
empty and retry states. Use the shared spinner and reactive controls. Safe
Markdown rendering and authorization remain application responsibilities.

Work items use the existing editing drawer; uploads use the existing dialog.
Document edits preserve revision/conflict handling. Messages remains a disabled
preview without sending or persistence. The design-system routes demonstrate
the same primitives used by the product.

## Verification

Run `npm run build`, `npm test`, and `npm run check:format:web` from the repository
root. The root browser E2E harness owns desktop/mobile workflow checks; static
formatting and Angular tests alone do not prove private Cognito or persistence.

## Authentication

`/api-builder/authentication` uses Routing's 35/65 editor/summary composition,
shared card/input/select primitives and compact themed actions. Provider-specific
fields configure OAuth 2.0, OIDC, Auth0 or Cognito public clients with code + PKCE
S256. In-memory drafts and edits survive provider switches and navigation but not
reload. Save draft validates locally; it does not connect a provider or change
workspace login/API enforcement. No client secrets. Show inline errors and focus
the first invalid field. Saved summary stays separate from unsaved edits.

## Vector search

`/api-builder/vector-search` reuses the compact Routing editor/list layout. Type,
route path and prompt are the only inputs. Four types: Vector embedding, Semantic
search, Regular search and Hybrid search. Generate configuration calls the local
search-builder draft/review workflow. Configurations remain editable session
drafts, not deployed routes. Unknown setup requirements are visible; detailed
model, fields, pipeline and request/response proposals use a disclosure. Generation
disables edits and preserves previous results on failure. No credentials in UI.

## RBAC

RBAC follows Authentication in the header and uses `/api-builder/rbac`, guarded
lazy loading and the existing return-path allowlist. Follow the 35/65 editor/review
layout, stacked below 768px, shared WoCard/WoTextInput/Select/spinner and theme
field styles. Preserve the font, backgrounds and 4px corners. Role cards and
route permission cards are white within the gray review container.

Use explicit role/route grants and distinguish Public from Authenticated routes.
Custom route methods remain editable. Agent output is an unsaved proposal; Save
configuration persists a revision through `/api/rbac`. Keep unsaved inputs/errors
across in-app navigation, disable actions during requests and preserve edits on
errors/conflicts. Reloading dirty data requires an inline discard choice. Export
requires the saved, reconciled revision; UI never labels it deployed/enforced.
Permission preview reports the configuration result and explicitly excludes live AWS
validation. Identity and route imports stay separate from workspace authentication.

## Caching and Infrastructure

Caching immediately precedes Infrastructure in header navigation. Both use guarded,
lazy routes, shared cards, typography and 4px radii; the shell owns page headings.
Infrastructure uses the Routing/Caching 35/65 layout, stacking below 768px, and the
canonical 28px compact SelectComponent controls. AWS and serverless are defaults;
containerized deployment remains a disabled option. Environment and a short optional
requirements field feed the infrastructure agent's draft/review endpoint. Drafts
remain scoped to the project for the session; failed generation preserves prior
output, and changed inputs label proposals stale.

The right panel renders an ngx-vflow architecture with pan, zoom, fit and selectable
resource nodes. A keyboard-accessible resource list provides the same details.
Saved entities produce unique entity-prefixed Lambda names and proposed tables.
All resources remain visible in both the canvas and list. Conditional SQS/SNS/Redis
and deferred ALB display explicit statuses and dashed node borders. Empty projects
show conditional Lambda and DynamoDB placeholders, replaced by real entity resources
when entities are saved. None are presented as deployed. Queues and topics require explicit producer/consumer mapping
before implementation. CloudFront caches static assets by default; Cognito is a JWT
validation dependency, not a proxy hop. The graph's baseline and agent proposals
are clearly labeled; no deployment or durable infrastructure save is implied.

Below 750px the header menu scrolls horizontally with nonshrinking links, retaining
the standard navigation font instead of squeezing all entries into equal columns.


## Search route selection

Routing's Route type offers Authenticated, Public, Vector embedding, Semantic
search, Hybrid search and Keyword search. Type is separate from the access flag;
new search routes default to authenticated POST and converting an existing route
preserves its access. Show both classification and access on search route cards.
Keyword search retains the backend identifier `regular`.

Vector search uses the shared required Route path dropdown, listing only matching
search-type routes from the active project's RoutingDraftsService. Switching type
clears mismatches; removed/retyped routes cannot generate or accept a pending
response. Empty options direct users to Routing. Existing valid configurations
remain editable. Dropdowns retain keyboard operation, required/error semantics,
4px option corners, 8px menu inset and 4px gaps between option backgrounds.

## Shared titlebar and load testing

Header navigation uses 9px labels, 0px icon-to-label gap and 11px between menus.
The active project control sits right-aligned beside each page title, outside the
header navigation. No footer is displayed. Load testing is last in the header and
requires the active project guard. `/api-builder/load-testing` is a planning page
with shared gray/white cards explaining the proposed Python Locust workflow.
Scenario generation and load execution are not connected; research and future
acceptance criteria live in `.codex/docs/tasks/load-testing/locust-approach.md`.

The circular lock remains at header right; only the bordered active project name
appears beside the page title.

## Project documentation

Docs is last in the header, after Load testing. The guarded /api-builder/docs page reuses the telemetry Documents list/search/category layout (360px left list, 18px gap) and existing MarkdownEditorComponent with Preview/Edit at right. The original telemetry/S3 page remains unchanged. Project docs are generated from saved overview/entities and available RBAC/caching configuration; edited Markdown is persisted independently per project. Read and save requests carry X-Project-ID. Unsaved edits use an app dialog for navigation; stale writes retain the draft. No upload or S3 action is shown for local generated docs.

Docs toolbar uses one row for Documents, search and the active-project dropdown (the shared category-style select). The extra shell project badge is omitted on this page. Document rows use identical 12px/10px padding with horizontal separators, a green outline and pale selected background, no left marker. Longer descriptive titles/summaries describe each real document type. Project switches clear prior documents and cancel pending list/read requests; unsaved edits retain the existing discard dialog.

Projects cards and the Docs project dropdown place the active project first through BuilderProjectsService.orderedProjects. Remaining projects keep their existing catalog order; the underlying catalog is not mutated.

## Shared project lifecycle controls

Every builder title row uses a shared active-project dropdown at right and centered Swagger/Test/Build controls. Docs keeps its title and search together at left. Menu labels are Endpoints and Auth; their existing routing/authentication URLs are retained. Switching a project remounts configuration pages after route guards; Docs cancels prior requests. Project cards remain active-first and use a three-bar options button adjacent to Active/Make active. Edit fills the left form, Delete confirms removal, and built cards expose Download project and GitHub repository. Popup tokens are masked and transient. No footer actions.

Current Build packages the local container API with saved project entities, generated
attributes and endpoint operations. Test checks syntax, JSON, application health,
CRUD, mock authentication and concurrent stock sales. Builds exclude cloud infrastructure.
Ready artifacts are fingerprinted against saved inputs and source. Swagger documents
configured routes and the localhost token endpoint. GitHub publication remains explicit;
tokens are never persisted.

Entity generation uses the registered draft/review agent and saves attributes and
prompt per project. Pending configuration loads keep prompts read-only; failed loads
show Retry. Real attributes replace illustrative sample schemas. Endpoints have explicit
Entity and Operation controls and persist edits/removals with revision checks. Save errors
retain the form and restore the previous route catalog. Project switching remounts screens.
Auth explains the local mock bearer issuer; future provider drafts are in a disclosure and
are not connected. Retain existing theme controls and 4px corners.

## Functional Caching

Caching now uses RBAC's 35/65 editor/review composition, stacked below 768px.
Use shared cards/select and themed fields, 4px radius and existing typography.
Three backend-defined presets: Route caching, Redis caching, API Gateway caching.
Save persists a project-scoped revision; export is enabled only for that saved,
unchanged policy. Preserve drafts on navigation/errors; require an inline discard
choice before reloading edits. Public GET confirmation and TTL validation precede
save. Loading disables inputs; failed initial loads expose Retry. Generated templates
need integration; no action claims a live cache or deployment.

Caching inputs and select triggers use the shared 28px compact rule. Review heading and saved state share one row, with status right aligned. Cache summary uses the existing monospace stack, method/path header, labeled expiry/API/storage/key rows and separated integration note. Checkbox sizing stays unchanged.

## Load testing configuration and report

Use the existing 35/65 editor/report split, 28px inputs, gray outer cards and
white report cards. Endpoint prompt, host, concurrency, spawn rate, duration and
optional task wait range are persisted per project by the backend. Run load testing
starts a real Docker workload and polls status. Disable inputs until initial loading
finishes and while running; preserve drafts during status retries. Show the last
saved report and local start/completion time on entry, keeping the previous report
visible during a new run. Show explicit empty, failed and unavailable-metric states;
never display sample results. Current scope is local GET list endpoints.

## Local connection settings

The shared project selector owns a visible Settings button immediately before its
project dropdown, including the Documents toolbar. Use the compact action style,
shared icon and 4px radii. Its native `tm-dialog` follows existing form dialogs,
with shared text input, labelled checkbox, inline feedback and focus restoration.
The scrollable popup fits narrow screens; changes require explicit Save and reload.
Cancel/Escape offers an inline discard choice for edited settings.

Settings are browser-local: the default uses the site's existing backend proxy;
direct mode selects an already-running backend on the same localhost hostname and
scheme, with a validated port. Test connection does not save. Save verifies the
backend, persists the connection, then reloads Projects to clear old backend state.
The form explains that unsaved page drafts are lost. No identity or cookie value
is displayed. Swagger loads its specification from the same chosen backend.

## Project actions and More navigation

The shared toolbar keeps its centered actions. Build and Test open the existing
GB Systems left-to-right native drawer with 4px radius, Close/Escape dismissal,
indeterminate progress and actual success/failure. Build shows correlated safe
execution events in an automatically scrolling region; Logs reopens the drawer.
No operation-status card is inserted above page panels, including Documents. Never estimate
percentage completion when the backend supplies no progress events.

More replaces the Docs header entry and discloses Documents, project Swagger,
Settings and Activities. Preserve outside-click/Escape dismissal and current-page
link semantics. Activities lists browser-local project interactions newest first,
bounded to 500 records across projects. Record action names, field labels and
operation outcomes, never field values or credential payloads. It is not a server
audit log. Load testing records the start of real project-specific container runs;
the durable JSON run reports remain the source of truth for results.

Button clicks use trailing shared feedback: brief for local actions, retained for
HTTP work initiated by the click. Preserve existing labels and disabled behavior;
respect reduced motion and avoid duplicate in-button spinners. Local Settings
uses 28px inputs and 11px body text. Project More Edit/Delete align right.

## Observability & Tracing

More places Observability & Tracing immediately before Documents. Its popup is
260px wide, capped to the viewport, to fit the full label. Observability panels
use the shared monospace stack with 11px body/labels, 10px controls/hints and
12px section headings. Its guarded page
uses Caching's compact 35/65 editor/review layout and stacks below 768px. Reuse
shared cards, fields, compact buttons, 28px input rules and 4px radii. Save persists
a project-scoped revision; pending operations disable inputs. Drafts remain scoped
to the project across in-app navigation. Reload requires explicit discard for edits.
Show load retry, validation focus, save/conflict errors and an accessible status.

Local OTLP HTTP tracing is disabled by default. Saved settings apply to subsequent
API Builder project requests and future generated artifacts; saving does not start
Jaeger. Show the local collector command and viewer link. Send test trace requires a
saved, enabled, unchanged configuration and reports export acceptance separately
from trace visibility. Traces and existing log correlation are supported; metrics,
log export and browser tracing are outside this screen. No request payload capture.
