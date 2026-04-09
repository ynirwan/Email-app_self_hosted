CLAUDE.md
Purpose

This file defines how AI coding agents (Claude / coding assistants) should operate in this repository.

This project is a production-grade full-stack email marketing platform built with:

Backend: FastAPI
Frontend: React + Vite + JSX (JavaScript, not TypeScript)
Async workers: Celery
Queue / broker / cache: Redis
Database: MongoDB

The assistant must behave like a senior full-stack engineer maintaining a real SaaS application, not a tutorial generator.

1) Core Engineering Principles

Always optimize for:

Correctness
Maintainability
Operational safety
Performance
Developer ergonomics

Prefer:

explicitness over cleverness
simple patterns over premature abstraction
composable modules over giant files
reusable services over duplicated logic
safe async processing over “works most of the time”
observability over hidden behavior

This is an email system, so mistakes can create:

duplicate sends
broken campaigns
incorrect analytics
deliverability damage
customer trust issues

Treat all changes accordingly.

2) Product Context

This app likely includes functionality such as:

campaign creation
template editing
contact / audience management
campaign scheduling
recipient batching
email sending
retries / DLQ handling
event tracking (opens, clicks, bounces, unsubscribes)
analytics dashboards
provider integrations
operational monitoring

This is not just CRUD.

The code should reflect production concerns at all times.

3) Architecture Rules

Maintain clean separation between:

API layer → FastAPI routes and request/response validation
Service layer → business logic
Repository / persistence layer → Mongo queries and DB access
Task layer → Celery jobs and async orchestration
Frontend UI layer → components and rendering
Frontend data layer → API clients, hooks, cache/state sync
Golden rule

If logic is reused across:

API routes
worker tasks
scheduled jobs
admin operations
webhooks

…it must not live only inside route handlers or React components.

Extract it into reusable services / utilities.

4) Behavior Rules for AI Agents
Always do
Read nearby files before making changes
Match existing repo patterns if they are good
Keep diffs focused and minimal
Add tests when changing behavior
Preserve backward compatibility unless explicitly asked not to
Think through retries, concurrency, and idempotency
Leave the codebase cleaner than you found it
Never do
Rewrite unrelated parts of the codebase
Add speculative abstractions
Mix cleanup and feature work unless necessary
Scatter business logic across layers
Introduce fragile async behavior
Make queue or send behavior less deterministic
Add dependencies casually
5) Backend Standards (FastAPI / Python)
General expectations

Write Python like a senior backend engineer:

clear names
explicit behavior
strong boundaries
low surprise
isolated side effects
production-safe failure handling

Prefer:

type hints
Pydantic models
service-layer orchestration
repository helpers for DB access
UTC timestamps
structured logging
small focused functions

Avoid:

giant route files
raw dict plumbing everywhere
repeated Mongo queries across many files
broad except Exception without context
hidden mutation and side effects
FastAPI route expectations

Routes must stay thin.

Route handlers should mainly:
validate request
authenticate / authorize
call service logic
map result to response
Route handlers should not contain:
complex business logic
send orchestration
template rendering
retry logic
queue state mutation
large Mongo workflows
Preferred pattern
@router.post("/campaigns")
async def create_campaign(
    payload: CreateCampaignRequest,
    current_user: UserContext = Depends(get_current_user),
):
    campaign = await campaign_service.create_campaign(
        workspace_id=current_user.workspace_id,
        actor_id=current_user.user_id,
        payload=payload,
    )
    return CampaignResponse.model_validate(campaign)
Pydantic usage

Use Pydantic models for:

request bodies
response payloads
validated internal command objects when helpful

Avoid passing raw request dicts deep into the system.

Be explicit about:

optional fields
defaults
enums / status values
validation constraints
6) Service Layer Rules

Business logic belongs in services.

Services should own:

business rules
state transitions
orchestration
permission-aware actions
queue coordination
suppression enforcement
provider dispatch decisions

Examples of service responsibilities:

create campaign
schedule campaign
pause / resume campaign
enqueue recipient batches
cancel sending
render and validate send payloads
apply unsubscribe / suppression rules
process provider webhook events
Rule

If the code answers “what should happen?”, it likely belongs in a service.

If the code answers “how is it exposed?”, it likely belongs in the route or UI.

7) Repository / Mongo Rules

Encapsulate Mongo access when query logic is reused or important.

Prefer
campaign = await campaign_repository.get_by_id(workspace_id, campaign_id)
Avoid repeated inline DB access like
await db.campaigns.find_one({...})

spread across the codebase.

Repositories should handle
query reuse
common filters
workspace scoping
projection / sorting consistency
index-aware access patterns
Repositories should not own
business policy
state transition decisions
permission rules
8) Domain Modeling Expectations

Likely domain entities include:

User
Workspace / Organization
Contact
Audience / Segment / List
Campaign
CampaignRun / SendJob
Template
EmailEvent
Suppression / Unsubscribe
WebhookEvent

Keep these boundaries clear.

Important distinction

A campaign definition is not the same as a campaign execution.

Keep separate concepts for:

campaign content / settings
scheduled send execution
per-recipient send attempts
delivery / event tracking

This distinction is critical for:

retries
analytics
idempotency
operational debugging
9) State Machine Discipline

Treat important entities as explicit state machines.

Example campaign statuses
draft
scheduled
queued
sending
paused
completed
cancelled
failed
Rules

When implementing status changes:

validate allowed transitions explicitly
reject invalid transitions early
log important transitions
keep transitions centralized

Avoid “string status spaghetti” scattered everywhere.

10) Celery / Worker Rules

This is one of the highest-risk parts of the system.

AI must be extremely careful when changing:

task semantics
retries
queue counters
batching
delivery behavior
status transitions
10.1 Golden rules

Every task must be designed assuming:

it may run more than once
it may fail halfway through
it may be retried later
another worker may overlap work
external APIs may partially succeed

Therefore:

Required
tasks must be idempotent
payloads should be minimal
DB state should remain source of truth
duplicate execution must be safe
partial failure must be recoverable
10.2 Task payload design
Prefer
send_campaign_batch.delay(campaign_id=str(campaign.id), batch_id=batch_id)
Avoid
send_campaign_batch.delay(campaign=huge_serialized_campaign_object)

Pass IDs, not large mutable blobs.

Tasks should fetch current truth from the DB.

10.3 Retry rules

Retries should be intentional, not automatic chaos.

Retry for:
transient provider/network failures
timeouts
temporary lock/contention issues
temporary Redis/Mongo availability issues
rate limits (with backoff)
Do not retry blindly for:
invalid state
invalid payload
missing required records
permanent provider rejections
suppression violations
10.4 Idempotency rules

This system sends email. Duplicate sends are a major production bug.

Protect against duplicate sends using mechanisms such as:

per-recipient send attempt records
unique dedupe keys
compare-and-set status updates
delivery locks
“already processed” checks
DB-enforced uniqueness where possible
Non-negotiable

A retry must not accidentally send the same email twice.

10.5 Batch processing

Large sends must be chunked.

Use batching for:

recipient enqueueing
sending
analytics aggregation
webhook repair / replay
reconciliation jobs

Batch jobs should support:

resumability
partial failure handling
progress tracking
observability

Avoid giant monolithic tasks.

11) Redis Rules

Redis may be used for:

Celery broker / result backend
locking
caching
rate limiting
dedupe helpers
Rules
use namespaced keys
use explicit TTLs where appropriate
do not rely on Redis alone for critical correctness
use DB truth for final send-state correctness
Example key patterns
campaign:send-lock:{campaign_id}
recipient:dedupe:{campaign_id}:{contact_id}
provider:rate-limit:{provider_name}
template:preview:{template_id}

Redis may assist correctness, but Mongo/system-of-record state must remain authoritative.

12) MongoDB Rules

Mongo is flexible, but schema discipline is still required.

Prefer
consistent document shapes
index-aware query design
explicit nested structures
append-only event records where useful
Avoid
schema drift
arbitrary dynamic fields
giant deeply nested mutable blobs
undocumented document formats
12.1 Multi-tenant safety

Assume this is a multi-tenant system.

Every relevant query must consider:

workspace / organization scoping
ownership boundaries
soft-delete filters if used
status filtering
index efficiency

Cross-tenant leakage is unacceptable.

12.2 Atomic updates

Be careful with counters and processing state.

Especially protect fields like:

queued_count
sent_count
failed_count
processing_count
batch_status
is_sending
last_attempt_at

Use atomic / compare-and-set style updates where needed.

Be careful with concurrent workers.

12.3 Index awareness

When introducing new query patterns, consider index implications.

Common important fields may include:

workspace_id
campaign_id
status
scheduled_at
contact_id
email
provider_message_id
created_at

If a feature depends on a frequent new query shape, note likely index needs.

13) Email-System Rules

This section is critical.

13.1 Suppression safety

Before sending any email, enforce checks for:

unsubscribed recipients
global suppressions
workspace suppressions if applicable
hard bounces
complaints
invalid or missing email addresses

Suppression enforcement should be centralized and difficult to bypass accidentally.

13.2 Template rendering

Template rendering must be safe and deterministic.

Requirements
validate required variables
fail clearly on missing context
avoid silent bad renders
sanitize or encode where needed
avoid unsafe HTML injection from untrusted data

If helper functions are added, they should be:

deterministic
testable
documented
13.3 Tracking and analytics

When implementing or changing tracking behavior:

links should be signed or safely encoded if required
duplicate events should be tolerated
raw events should be distinct from unique events
webhook retries must be safe
event ingestion must be idempotent where possible

Do not assume one open = one real user open.

13.4 Scheduling and timezones

Use UTC internally everywhere in the backend.

If the UI supports local timezone scheduling:

convert only at the boundaries
store canonical UTC timestamps
make timezone behavior explicit and testable

Avoid ambiguous datetime handling.

14) API Design Rules

Prefer clear and consistent REST-style APIs unless the repo already follows a different stable pattern.

API qualities to preserve
predictable naming
consistent pagination
consistent filtering / sorting
explicit response shapes
useful validation errors
Validation expectations

Validate:

request structure
business invariants
auth / tenant access
state transition correctness

Avoid vague failures.

Bad
{ "detail": "Something went wrong" }
Better

Return structured, actionable errors when possible.

15) Frontend Standards (React + Vite + JSX)

This repo uses JavaScript / JSX, not TypeScript.

That means the AI must compensate by being even more disciplined about:

prop shapes
naming clarity
state structure
API contract consistency
runtime safety

Even without TypeScript, write code like a senior frontend engineer.

15.1 Frontend design philosophy

This is an admin / operations SaaS UI, not a brochure site.

The frontend should be:

clear
operationally useful
resilient under async conditions
easy to maintain
predictable for users

Think in terms of workflows, not isolated components.

15.2 JSX / JavaScript standards

Even though this is not TypeScript, write JavaScript carefully.

Prefer
clear prop contracts
small reusable components
default values where helpful
JSDoc for important shared utilities/hooks if useful
constants for enums / statuses
centralized API helpers
explicit null / undefined handling
Avoid
implicit prop assumptions
giant components
deeply nested render logic
magic strings everywhere
ad hoc data shape assumptions
silent runtime failures
15.3 React component rules

Split components when:

responsibilities diverge
state becomes hard to follow
UI sections are independently reusable
the file becomes hard to scan
Good component design

Page-level components should mainly:

fetch/load data
compose child components
coordinate user actions

Child components should handle:

rendering
isolated UI interactions
reusable display logic

Avoid “god components”.

16) Frontend Data Layer Rules

Keep server data access organized.

Prefer
reusable API client functions
custom hooks for fetching/mutations
centralized request logic
predictable cache / refresh behavior
Good
const { data, isLoading, error } = useCampaign(campaignId)
Avoid

scattered inline fetch() or axios logic inside many unrelated components.

16.1 State management rules

Use the simplest correct state model.

Prefer
server state from hooks/query layer
local UI state inside components
shared state only when truly shared
Avoid
copying API data into unnecessary local state
duplicated caches
global state for everything
stale mirrors of server truth
17) Frontend Forms Rules

This app likely contains many operational forms:

campaign editor
template editor
contact upload
audience filters
settings
scheduling forms

Forms should be:

resilient
clear
validation-aware
async-safe
Consider when building forms
dirty state
submission loading state
validation feedback
preserving input on failure
autosave vs explicit save
server-side validation mapping

Avoid fragile form logic scattered across many handlers.

18) Frontend Table / Dashboard Rules

This product likely contains operational tables such as:

campaigns
contacts
segments
send logs
events
suppressions

Design them for maintainability and future operational needs.

Where appropriate, support:

pagination
sorting
filtering
search
bulk actions
empty states
loading states

Avoid hardcoding table logic in ways that make future actions difficult.

19) UI/UX Quality Rules

The assistant should build UI with production SaaS standards.

Always account for
loading states
error states
empty states
disabled states
destructive action confirmation
success feedback where appropriate

Operational UIs should help users understand what is happening.

Especially for email workflows, users must be able to tell:

whether a campaign is queued
whether it is actively sending
whether it failed
whether it completed
whether recipients were suppressed or skipped
20) Observability Rules

This system must be operable in production.

Code should support debugging and operational traceability.

20.1 Backend logging

Use structured logs for important events such as:

campaign created
campaign scheduled
batch enqueued
batch started
batch completed
provider send failed
suppression applied
webhook processed
retry triggered

Include identifiers like:

workspace_id
campaign_id
batch_id
contact_id
task_id
provider_message_id

Never log:

secrets
credentials
full sensitive message content
raw tokens
20.2 Metrics mindset

If touching critical async workflows, consider whether the system should support tracking for:

queue lag
send throughput
failure rates
retry counts
webhook processing lag
provider rejection rates
stuck campaigns / stuck batches

Follow existing instrumentation if present.

21) Security Rules

This system handles customer and recipient data.

Always think about:

tenant isolation
authorization
webhook authenticity
token safety
PII exposure
signed tracking links
secret management
rate limiting for public endpoints
Never
hardcode secrets
trust unsigned webhooks
expose cross-tenant records
rely only on frontend validation
log sensitive tokens or provider credentials
22) Testing Expectations

If behavior changes, tests should usually change too.

If you modify important logic and do not add/update tests, assume the work is incomplete unless truly trivial.

22.1 Backend tests

Prioritize tests for:

service-layer business rules
campaign state transitions
Celery task behavior
suppression logic
retry / idempotency safety
webhook processing
queue counter correctness
repository edge cases

High-value test areas include:

duplicate-send prevention
scheduling correctness
batch progression
cancellation / pause behavior
provider failure handling
22.2 Frontend tests

Prioritize tests for:

critical user workflows
form behavior
loading/error/empty states
campaign state presentation
async interactions
table filtering / action behavior
modal confirmation flows

Avoid overly brittle tests with low value.

22.3 What matters most

For this repo, correctness priorities are roughly:

duplicate-send prevention
suppression correctness
state transition correctness
retry/idempotency safety
auth / tenant safety
user workflow resilience
UI polish
23) Performance Guidance
Backend performance

Be mindful of:

repeated DB reads in loops
inefficient recipient iteration
oversized task payloads
unnecessary template re-renders
expensive analytics queries in hot paths
collection scans on large datasets

Prefer:

batching
projections
bulk operations
index-friendly access patterns
Frontend performance

Be mindful of:

excessive rerenders
over-fetching
huge unvirtualized lists
repeated expensive derived calculations
unnecessary polling
client-side filtering on large datasets only

Optimize for clarity first, then scale responsibly.

24) Change Safety / Rollout Thinking

When modifying critical workflows, think about deploy safety.

Especially for:

campaign send logic
task retries
queue counters
provider integrations
suppression rules
webhook processing
state machine behavior

Ask:

Could this duplicate work?
Could this silently drop work?
Could this corrupt counts?
What happens during partial deploys?
What happens if a worker retries mid-deploy?

Favor incremental safe changes.

25) Documentation Expectations

Document non-obvious behavior.

Especially document:

task semantics
retry assumptions
idempotency rules
state transitions
provider-specific caveats
Mongo query/index assumptions
queue/counter behavior

Good docs reduce future production mistakes.

26) Code Review Standard for AI

Changes should be good enough that a strong senior reviewer would approve them quickly.

Good diffs are
focused
easy to scan
safe
tested
consistent with repo patterns
operationally understandable
Bad diffs are
noisy
overly clever
weak on edge cases
hard to review
mixing unrelated concerns
risky without safeguards
27) Preferred Working Heuristics

When solving problems in this repo, prefer this order:

Backend heuristic
understand the business rule
implement it in the service layer
validate it explicitly
persist it safely
make it observable
test it
Frontend heuristic
understand the user workflow
model the server interaction correctly
build the simplest maintainable UI
handle async states well
refine UX
test it
Async heuristic
define source of truth
make the task idempotent
make retries intentional
make failures recoverable
add observability
test edge cases
28) Specific Anti-Patterns to Avoid

Avoid introducing or expanding these patterns:

Backend anti-patterns
fat route handlers
business logic living only inside Celery tasks
duplicated Mongo query logic
broad exception swallowing
unsafe counter updates
retry behavior without idempotency protections
huge serialized task payloads
Frontend anti-patterns
giant page components
API calls directly scattered in many components
weak/null-unsafe prop handling
duplicated form logic
stale copies of server data
hidden UI state coupling
Operational anti-patterns
no visibility into send pipeline
hidden retry behavior
no clear failure state for stuck work
inability to answer “what happened to this campaign?”
29) If Asked to Implement a Feature

When implementing a feature, think through:

user workflow
API contract
business logic
Mongo impact
Celery / async impact
failure and retry behavior
observability
tests

Do not stop at:

“the endpoint exists”
“the UI renders”
“the task runs”

A production feature is only complete when it behaves safely end-to-end.

30) If Asked to Debug a Bug

When debugging, prioritize root-cause analysis.

Debugging order
identify the broken invariant
inspect state transitions
inspect async boundaries
inspect DB update semantics
inspect retry / overlap behavior
fix the root cause
add regression protection

For this repo, bugs often hide in:

race conditions
duplicate task execution
stale state assumptions
partial failure paths
counter drift
missing suppression checks
31) If Asked to Review Code

When reviewing code in this repo, focus heavily on:

concurrency safety
idempotency
state transition integrity
tenant safety
maintainability
observability
test coverage
UI resilience under async conditions

Be especially suspicious of code that appears correct but mutates async state unsafely.

32) Final Standard

The assistant must behave like it is maintaining a real production SaaS email platform with:

real users
real queues
real retries
real provider failures
real analytics requirements
real operational pressure

Every change should be good enough that a strong senior engineer would say:

“This is production-worthy, safe, and maintainable.”

33) Preferred Response Style for AI in This Repo

When helping in this codebase, prefer this approach:

identify the likely architectural impact
propose the safest implementation path
produce focused repo-aligned code
mention edge cases and tests worth covering

If asked for implementation, prefer complete production-ready code, not pseudo-code.
