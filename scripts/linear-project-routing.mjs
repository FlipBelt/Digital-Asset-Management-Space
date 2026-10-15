import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPOSITORY = 'FlipBelt/Digital-Asset-Management-Space';
export const TEAM_ID = '841e149e-6934-40d5-901a-ecdb1efc5b03';
export const PROJECT_ID = '77af2f8a-8f02-4816-abdd-ce59f3d747a2';
const LINEAR_ENDPOINT = 'https://api.linear.app/graphql';
const GITHUB_ENDPOINT = `https://api.github.com/repos/${REPOSITORY}/issues/`;
const DEFAULT_POLL_DELAYS = [2000, 4000, 8000, 16000, 30000, 30000, 30000, 30000];

export const LOOKUP_QUERY = `query GithubSyncLookup($url: String!) {
  attachmentsForURL(url: $url, first: 2, includeArchived: true) {
    nodes {
      id url archivedAt
      issue {
        id identifier archivedAt trashed updatedAt
        team { id }
        project { id }
        syncedWith { id service }
      }
    }
    pageInfo { hasNextPage }
  }
}`;

export const UPDATE_MUTATION = `mutation RouteGithubIssue($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id team { id } project { id } }
  }
}`;

export class RoutingError extends Error {}

function fail(message) {
  throw new RoutingError(message);
}

function requireToken(value, name) {
  if (typeof value !== 'string' || !value.trim()) fail(`${name} is missing.`);
  return value.trim();
}

function issueNumber(value) {
  const text = String(value ?? '');
  const number = Number(text);
  if (!/^[1-9]\d*$/.test(text) || !Number.isSafeInteger(number)) {
    fail('A positive integer issue_number is required.');
  }
  return number;
}

function validateGithubIssue(issue, number) {
  const url = `https://github.com/${REPOSITORY}/issues/${number}`;
  if (!issue || issue.number !== number || issue.html_url !== url || issue.pull_request) {
    fail('GitHub issue identity does not match the allowed canonical issue URL.');
  }
  if (typeof issue.node_id !== 'string' || !/^[A-Za-z0-9_+/=-]+$/.test(issue.node_id)) {
    fail('GitHub issue node_id is missing or invalid.');
  }
  return { number, url, nodeId: issue.node_id };
}

export function validateEvent(event, env) {
  if (env.GITHUB_REPOSITORY !== REPOSITORY || env.GITHUB_SERVER_URL !== 'https://github.com' ||
      event?.repository?.full_name !== REPOSITORY ||
      event.repository.html_url !== `https://github.com/${REPOSITORY}`) {
    fail('Event repository is outside the allowed repository.');
  }
  if (env.GITHUB_EVENT_NAME === 'issues') {
    if (event.action !== 'opened') fail('Only issues.opened events are allowed.');
    return validateGithubIssue(event.issue, issueNumber(event.issue?.number));
  }
  if (env.GITHUB_EVENT_NAME === 'workflow_dispatch') {
    if (env.GITHUB_REF !== 'refs/heads/main') fail('Manual retries are allowed only on main.');
    return { number: issueNumber(event.inputs?.issue_number) };
  }
  fail('Unsupported GitHub event.');
}

function remainingMs(context) {
  const remaining = context.deadline - context.now();
  if (remaining <= 0) fail('Routing timed out; inspect the synced issue and retry manually.');
  return remaining;
}

async function requestJson(context, url, options, service, mutation = false) {
  const timeout = Math.min(10000, remainingMs(context));
  const suffix = mutation ? ' The update outcome may be unknown; inspect before retrying.' : '';
  let response;
  try {
    response = await context.fetchImpl(url, {
      ...options,
      redirect: 'error',
      signal: AbortSignal.timeout(timeout),
    });
  } catch {
    fail(`${service} request failed or timed out.${suffix}`);
  }
  if (!response.ok) {
    const status = Number.isInteger(response.status) ? response.status : 'unknown';
    fail(`${service} HTTP request failed (${status}).${suffix}`);
  }
  try {
    return await response.json();
  } catch {
    fail(`${service} response was not valid JSON.${suffix}`);
  }
}

async function linearRequest(context, query, variables, mutation = false) {
  const result = await requestJson(context, LINEAR_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: context.linearToken },
    body: JSON.stringify({ query, variables }),
  }, 'Linear', mutation);
  if (!result || (Array.isArray(result.errors) && result.errors.length) ||
      (result.errors && !Array.isArray(result.errors)) || !result.data) {
    fail(mutation ? 'Linear GraphQL update failed; inspect the issue before retrying.' :
      'Linear GraphQL lookup failed.');
  }
  return result.data;
}

function hasField(record, key) {
  return record !== null && typeof record === 'object' && Object.hasOwn(record, key);
}

function invalidField(name, record, key, accepts) {
  if (!hasField(record, key)) return `${name}=missing`;
  const value = record[key];
  if (accepts(value)) return null;
  const type = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
  return `${name}=${type}`;
}

async function fetchAttachment(context, githubIssue) {
  const data = await linearRequest(context, LOOKUP_QUERY, { url: githubIssue.url });
  const connection = data.attachmentsForURL;
  if (!connection || !Array.isArray(connection.nodes) ||
      typeof connection.pageInfo?.hasNextPage !== 'boolean') {
    fail('Linear attachment lookup returned an invalid shape.');
  }
  if (connection.pageInfo.hasNextPage || connection.nodes.length > 1) {
    fail('Multiple matching Linear attachments; routing cannot be confirmed.');
  }
  if (!connection.nodes.length) return null;
  const attachment = connection.nodes[0];
  const issue = attachment?.issue;
  const string = (value) => typeof value === 'string';
  const nullableString = (value) => value === null || string(value);
  const invalid = [
    invalidField('attachment.url', attachment, 'url', (value) => value === githubIssue.url),
    invalidField('attachment.id', attachment, 'id', string),
    invalidField('attachment.archivedAt', attachment, 'archivedAt', nullableString),
    invalidField('issue.id', issue, 'id', string),
    invalidField('issue.team.id', issue?.team, 'id', string),
    invalidField('issue.updatedAt', issue, 'updatedAt', string),
    invalidField('issue.trashed', issue, 'trashed', (value) => value === null || typeof value === 'boolean'),
    invalidField('issue.archivedAt', issue, 'archivedAt', nullableString),
    invalidField('issue.project', issue, 'project', (value) => value === null ||
      (typeof value === 'object' && !Array.isArray(value) && typeof value.id === 'string')),
  ].filter(Boolean);
  if (invalid.length) {
    fail(`Linear attachment or issue identity is incomplete (${invalid.join(', ')}).`);
  }
  if (attachment.archivedAt !== null || issue.archivedAt !== null || issue.trashed === true) {
    fail('Archived or trashed records cannot be routed.');
  }
  const sources = Array.isArray(issue.syncedWith) ?
    issue.syncedWith.filter((source) => source?.service === 'github') : [];
  const nodeIdMatch = sources[0]?.id === githubIssue.nodeId;
  if (sources.length !== 1 || !nodeIdMatch) {
    fail('A matching native GitHub issue sync is required; a manual link is insufficient ' +
      `(githubSources=${sources.length}, nodeIdMatch=${nodeIdMatch}).`);
  }
  return attachment;
}

function skipReason(attachment) {
  if (attachment.issue.team.id !== TEAM_ID) return 'foreign-team';
  if (attachment.issue.project !== null) {
    return attachment.issue.project.id === PROJECT_ID ? 'already-routed' : 'existing-project';
  }
  return null;
}

function snapshot(attachment) {
  const issue = attachment.issue;
  return JSON.stringify({
    attachmentId: attachment.id, issueId: issue.id, identifier: issue.identifier,
    archivedAt: issue.archivedAt, trashed: issue.trashed, updatedAt: issue.updatedAt,
    teamId: issue.team.id, projectId: issue.project?.id ?? null,
    syncedWith: issue.syncedWith.map((source) => ({ id: source?.id, service: source?.service })),
  });
}

export async function routeIssue({
  event,
  env = process.env,
  fetchImpl = globalThis.fetch,
  sleep = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds)),
  now = Date.now,
  pollDelaysMs = DEFAULT_POLL_DELAYS,
  timeoutMs = 210000,
}) {
  let githubIssue = validateEvent(event, env);
  const context = {
    fetchImpl, now, deadline: now() + Math.min(timeoutMs, 210000),
    linearToken: requireToken(env.LINEAR_API_KEY, 'LINEAR_API_KEY'),
  };
  if (!githubIssue.url) {
    const githubToken = requireToken(env.GITHUB_TOKEN, 'GITHUB_TOKEN');
    const issue = await requestJson(context, `${GITHUB_ENDPOINT}${githubIssue.number}`, {
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    }, 'GitHub');
    githubIssue = validateGithubIssue(issue, githubIssue.number);
  }

  let attachment = await fetchAttachment(context, githubIssue);
  for (const delay of pollDelaysMs) {
    if (attachment) break;
    await sleep(Math.min(delay, remainingMs(context)));
    attachment = await fetchAttachment(context, githubIssue);
  }
  if (!attachment) fail('Native Linear sync was not found within the retry window; retry manually.');
  let reason = skipReason(attachment);
  if (reason) return { status: 'skipped', reason, issueNumber: githubIssue.number };

  // Linear exposes no conditional project update; re-read immediately before the mutation.
  const current = await fetchAttachment(context, githubIssue);
  if (!current) fail('Native sync disappeared before the update; no project was changed.');
  reason = skipReason(current);
  if (reason) return { status: 'skipped', reason, issueNumber: githubIssue.number };
  if (snapshot(current) !== snapshot(attachment)) {
    fail('The synced issue changed before the update; no project was changed.');
  }

  const data = await linearRequest(context, UPDATE_MUTATION, {
    id: current.issue.id, input: { projectId: PROJECT_ID },
  }, true);
  const result = data.issueUpdate;
  if (result?.success !== true || result.issue?.id !== current.issue.id ||
      result.issue?.team?.id !== TEAM_ID || result.issue?.project?.id !== PROJECT_ID) {
    fail('Linear did not confirm the requested project update; inspect before retrying.');
  }
  const readback = await fetchAttachment(context, githubIssue);
  if (!readback || readback.issue.id !== current.issue.id ||
      readback.issue.team.id !== TEAM_ID || readback.issue.project?.id !== PROJECT_ID) {
    fail('Linear project readback did not match; inspect before retrying.');
  }
  return { status: 'routed', issueNumber: githubIssue.number };
}

export async function runCli({ env = process.env, readEvent = readFile, log = console.log,
  logError = console.error, fetchImpl = globalThis.fetch } = {}) {
  try {
    if (!env.GITHUB_EVENT_PATH) fail('GITHUB_EVENT_PATH is missing.');
    let event;
    try {
      event = JSON.parse(await readEvent(env.GITHUB_EVENT_PATH, 'utf8'));
    } catch {
      fail('GitHub event file could not be read as JSON.');
    }
    const result = await routeIssue({ event, env, fetchImpl });
    log(`GitHub issue #${result.issueNumber}: ${result.status}${result.reason ? ` (${result.reason})` : ''}.`);
    return 0;
  } catch (error) {
    // Never print upstream response bodies, event content, headers, or raw exception messages.
    logError(error instanceof RoutingError ? error.message : 'Unexpected routing failure; no secrets were logged.');
    return 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = await runCli();
}
