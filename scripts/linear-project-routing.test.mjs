import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { LOOKUP_QUERY, PROJECT_ID, REPOSITORY, TEAM_ID, UPDATE_MUTATION,
  routeIssue, runCli, validateEvent } from './linear-project-routing.mjs';

const secret = 'private-test-token-never-log';
const githubSecret = 'github-private-test-token-never-log';
const number = 8;
const url = `https://github.com/${REPOSITORY}/issues/${number}`;
const nodeId = 'I_kwDO_test8';
const env = {
  GITHUB_REPOSITORY: REPOSITORY,
  GITHUB_SERVER_URL: 'https://github.com',
  GITHUB_EVENT_NAME: 'issues',
  GITHUB_REF: 'refs/heads/main',
  GITHUB_EVENT_PATH: '/event.json',
  LINEAR_API_KEY: secret,
  GITHUB_TOKEN: githubSecret,
};
const event = {
  action: 'opened',
  repository: { full_name: REPOSITORY, html_url: `https://github.com/${REPOSITORY}` },
  issue: { number, html_url: url, node_id: nodeId },
};

function attachment(overrides = {}) {
  return {
    id: 'attachment-8', url, archivedAt: null,
    issue: {
      id: 'linear-issue-42', identifier: 'FBC-42', archivedAt: null, trashed: false,
      updatedAt: '2026-10-15T00:00:00.000Z', team: { id: TEAM_ID }, project: null,
      syncedWith: [{ id: nodeId, service: 'github' }],
      ...overrides,
    },
  };
}

function lookup(nodes = [attachment()], hasNextPage = false) {
  return { data: { attachmentsForURL: { nodes, pageInfo: { hasNextPage } } } };
}

function updated(success = true) {
  return { data: { issueUpdate: { success,
    issue: { id: 'linear-issue-42', team: { id: TEAM_ID }, project: { id: PROJECT_ID } },
  } } };
}

function mockFetch(responses) {
  const calls = [];
  const fetchImpl = async (requestUrl, options) => {
    calls.push({ url: requestUrl, options,
      body: options.body ? JSON.parse(options.body) : null });
    const response = responses.shift();
    assert.notEqual(response, undefined, 'Unexpected network request');
    if (response instanceof Error) throw response;
    if (typeof response === 'function') return response(calls.at(-1));
    return { ok: true, status: 200, json: async () => response };
  };
  return { calls, fetchImpl };
}

function mutationCalls(mock) {
  return mock.calls.filter((call) => call.body?.query === UPDATE_MUTATION);
}

async function routeWith(mock, options = {}) {
  return routeIssue({ event, env, fetchImpl: mock.fetchImpl, pollDelaysMs: [], ...options });
}

test('routes only projectId after a second exact lookup and confirms readback', async () => {
  const mock = mockFetch([lookup(), lookup(), updated(), lookup([attachment({
    project: { id: PROJECT_ID }, updatedAt: '2026-10-15T00:00:01.000Z',
  })])]);
  assert.deepEqual(await routeWith(mock), { status: 'routed', issueNumber: number });
  assert.equal(mock.calls.length, 4);
  assert.deepEqual(mutationCalls(mock)[0].body.variables, {
    id: 'linear-issue-42', input: { projectId: PROJECT_ID },
  });
  for (const call of mock.calls) {
    assert.equal(call.url, 'https://api.linear.app/graphql');
    assert.equal(call.options.redirect, 'error');
    assert.equal(call.options.headers.Authorization, secret);
    if (call.body.query === LOOKUP_QUERY) assert.deepEqual(call.body.variables, { url });
  }
  assert.match(LOOKUP_QUERY, /first: 2, includeArchived: true/);
  assert.match(LOOKUP_QUERY, /syncedWith/);
  assert.doesNotMatch(LOOKUP_QUERY, /metadata|ExternalEntityInfoGithubMetadata/);
});

test('a present nullable trashed state can be routed and read back', async () => {
  const mock = mockFetch([lookup([attachment({ trashed: null })]),
    lookup([attachment({ trashed: null })]), updated(),
    lookup([attachment({ trashed: null, project: { id: PROJECT_ID } })])]);
  assert.deepEqual(await routeWith(mock), { status: 'routed', issueNumber: number });
  assert.equal(mutationCalls(mock).length, 1);
});

test('missing and invalid trashed fields fail closed with value-free diagnostics', async () => {
  const missing = attachment();
  delete missing.issue.trashed;
  const cases = [
    [missing, 'missing'],
    [attachment({ trashed: undefined }), 'undefined'],
    [attachment({ trashed: secret }), 'string'],
    [attachment({ trashed: 0 }), 'number'],
    [attachment({ trashed: {} }), 'object'],
    [attachment({ trashed: [] }), 'array'],
  ];
  for (const [node, type] of cases) {
    const mock = mockFetch([lookup([node])]);
    await assert.rejects(routeWith(mock), (error) => {
      assert.equal(error.message,
        `Linear attachment or issue identity is incomplete (issue.trashed=${type}).`);
      assert.ok(!error.message.includes(secret));
      return true;
    });
    assert.equal(mutationCalls(mock).length, 0);
  }
  const trashed = mockFetch([lookup([attachment({ trashed: true })])]);
  await assert.rejects(routeWith(trashed), /Archived or trashed records/);
  assert.equal(mutationCalls(trashed).length, 0);
});

test('incomplete identity diagnostics identify fixed fields and types without their values', async () => {
  const node = attachment({ updatedAt: null, team: { id: { secret } },
    project: secret, trashed: secret });
  node.url = `https://example.com/${secret}`;
  node.id = { secret };
  delete node.issue.archivedAt;
  const mock = mockFetch([lookup([node])]);
  const messages = [];
  assert.equal(await runCli({ env, fetchImpl: mock.fetchImpl,
    readEvent: async () => JSON.stringify(event),
    logError: (message) => messages.push(message) }), 1);
  assert.equal(messages[0], 'Linear attachment or issue identity is incomplete ' +
    '(attachment.url=string, attachment.id=object, issue.team.id=object, ' +
    'issue.updatedAt=null, issue.trashed=string, issue.archivedAt=missing, issue.project=string).');
  assert.ok(!messages[0].includes(secret));
  assert.equal(mutationCalls(mock).length, 0);
});

test('existing CIS or any other project is preserved', async () => {
  for (const projectId of ['cis-project', 'another-project']) {
    const mock = mockFetch([lookup([attachment({ project: { id: projectId } })])]);
    assert.deepEqual(await routeWith(mock), {
      status: 'skipped', reason: 'existing-project', issueNumber: number,
    });
    assert.equal(mutationCalls(mock).length, 0);
  }
});

test('an already routed issue is idempotent', async () => {
  const mock = mockFetch([lookup([attachment({ project: { id: PROJECT_ID } })])]);
  assert.equal((await routeWith(mock)).reason, 'already-routed');
  assert.equal(mock.calls.length, 1);
  assert.equal(mutationCalls(mock).length, 0);
});

test('a foreign team is preserved', async () => {
  const mock = mockFetch([lookup([attachment({ team: { id: 'foreign-team' } })])]);
  assert.equal((await routeWith(mock)).reason, 'foreign-team');
  assert.equal(mutationCalls(mock).length, 0);
});

test('foreign repository, host, action and pull request inputs cannot request a write', async () => {
  const cases = [
    { env: { ...env, GITHUB_REPOSITORY: 'FlipBelt/CIS' } },
    { env: { ...env, GITHUB_SERVER_URL: 'https://github.example.com' } },
    { event: { ...event, repository: { ...event.repository, full_name: 'FlipBelt/CIS' } } },
    { event: { ...event, action: 'edited' } },
    { event: { ...event, issue: { ...event.issue, html_url: 'https://example.com/issues/8' } } },
    { event: { ...event, issue: { ...event.issue, pull_request: { url } } } },
    { env: { ...env, GITHUB_EVENT_NAME: 'pull_request' } },
  ];
  for (const options of cases) {
    const mock = mockFetch([]);
    await assert.rejects(routeWith(mock, options));
    assert.equal(mock.calls.length, 0);
  }
});

test('duplicate attachments, including the same issue twice, fail closed', async () => {
  for (const response of [lookup([attachment(), attachment()]), lookup([attachment()], true)]) {
    const mock = mockFetch([response]);
    await assert.rejects(routeWith(mock), /Multiple matching/);
    assert.equal(mutationCalls(mock).length, 0);
  }
});

test('manual links and missing, foreign, duplicate or mismatched native identities are rejected', async () => {
  const correct = attachment().issue.syncedWith[0];
  const variants = [undefined, null, {}, [], [null], [{ ...correct, service: 'jira' }],
    [{ ...correct, id: 'another-node' }], [{ service: 'github' }],
    [{ ...correct, id: null }],
    [correct, correct]];
  for (const syncedWith of variants) {
    const mock = mockFetch([lookup([attachment({ syncedWith })])]);
    await assert.rejects(routeWith(mock), /matching native GitHub issue sync/);
    assert.equal(mutationCalls(mock).length, 0);
  }
});

test('optional metadata is not queried or used to determine a native synced identity', async () => {
  const native = { id: nodeId, service: 'github' };
  const mock = mockFetch([
    lookup([attachment({ syncedWith: [{ ...native, metadata: null }] })]),
    lookup([attachment({ syncedWith: [{ ...native, metadata: {
      owner: 'AnotherOrg', repo: 'CIS', number: null,
    } }] })]), updated(),
    lookup([attachment({ project: { id: PROJECT_ID }, syncedWith: [native] })]),
  ]);
  assert.equal((await routeWith(mock)).status, 'routed');
  assert.equal(mutationCalls(mock).length, 1);
  assert.doesNotMatch(LOOKUP_QUERY, /metadata/);
});

test('native identity failure logs only source count and node match boolean', async () => {
  const mock = mockFetch([lookup([attachment({ syncedWith: [{
    id: secret, service: 'github', metadata: { owner: githubSecret },
  }] })])]);
  const messages = [];
  assert.equal(await runCli({ env, fetchImpl: mock.fetchImpl,
    readEvent: async () => JSON.stringify(event),
    logError: (message) => messages.push(message) }), 1);
  assert.equal(messages[0], 'A matching native GitHub issue sync is required; ' +
    'a manual link is insufficient (githubSources=1, nodeIdMatch=false).');
  assert.ok(!messages[0].includes(secret) && !messages[0].includes(githubSecret));
  assert.equal(mutationCalls(mock).length, 0);
});

test('archived, trashed, mismatched URL and incomplete records cannot be routed', async () => {
  const badUrl = attachment();
  badUrl.url = `${url}/`;
  const archivedAttachment = attachment();
  archivedAttachment.archivedAt = '2026-10-15';
  const missingProject = attachment();
  delete missingProject.issue.project;
  for (const node of [attachment({ archivedAt: '2026-10-15' }), attachment({ trashed: true }),
    attachment({ updatedAt: null }), badUrl, archivedAttachment, missingProject]) {
    const mock = mockFetch([lookup([node])]);
    await assert.rejects(routeWith(mock));
    assert.equal(mutationCalls(mock).length, 0);
  }
});

test('native sync delay is retried a bounded number of times', async () => {
  const delays = [];
  const mock = mockFetch([lookup([]), lookup([]), lookup(), lookup(), updated(),
    lookup([attachment({ project: { id: PROJECT_ID } })])]);
  const result = await routeWith(mock, { pollDelaysMs: [2, 4, 8],
    sleep: async (delay) => delays.push(delay) });
  assert.equal(result.status, 'routed');
  assert.deepEqual(delays, [2, 4]);
  assert.equal(mutationCalls(mock).length, 1);
});

test('native sync absence fails after the retry window without creating anything', async () => {
  const mock = mockFetch([lookup([]), lookup([]), lookup([])]);
  await assert.rejects(routeWith(mock, { pollDelaysMs: [1, 2], sleep: async () => {} }),
    /retry window/);
  assert.equal(mock.calls.length, 3);
  assert.equal(mutationCalls(mock).length, 0);
});

test('the total deadline stops polling before any write', async () => {
  let elapsed = 0;
  const mock = mockFetch([lookup([])]);
  await assert.rejects(routeWith(mock, { timeoutMs: 10, now: () => elapsed,
    pollDelaysMs: [20], sleep: async (delay) => { elapsed += delay; } }), /timed out/);
  assert.equal(mock.calls.length, 1);
  assert.equal(mutationCalls(mock).length, 0);
});

test('lookup HTTP, network, JSON and GraphQL errors never reach the mutation', async () => {
  const variants = [
    new Error(`network ${secret}`),
    () => ({ ok: false, status: 401, json: async () => ({ message: secret }) }),
    () => ({ ok: true, status: 200, json: async () => { throw new Error(secret); } }),
    { errors: [{ message: secret }], data: lookup().data },
    { errors: { message: secret } },
    { data: {} },
  ];
  for (const response of variants) {
    const mock = mockFetch([response]);
    await assert.rejects(routeWith(mock), (error) => !error.message.includes(secret));
    assert.equal(mutationCalls(mock).length, 0);
  }
});

test('write-time recheck preserves project/team changes and rejects identity changes', async () => {
  for (const current of [attachment({ project: { id: 'cis-project' } }),
    attachment({ project: { id: PROJECT_ID } }), attachment({ team: { id: 'cis-team' } })]) {
    const mock = mockFetch([lookup(), lookup([current])]);
    assert.equal((await routeWith(mock)).status, 'skipped');
    assert.equal(mutationCalls(mock).length, 0);
  }
  for (const current of [attachment({ id: 'another-issue' }),
    attachment({ updatedAt: '2026-10-15T00:00:01.000Z' })]) {
    const mock = mockFetch([lookup(), lookup([current])]);
    await assert.rejects(routeWith(mock), /changed before/);
    assert.equal(mutationCalls(mock).length, 0);
  }
  const vanished = mockFetch([lookup(), lookup([])]);
  await assert.rejects(routeWith(vanished), /disappeared before/);
  assert.equal(mutationCalls(vanished).length, 0);
});

test('unsuccessful or mismatched mutation payloads fail clearly', async () => {
  const badProject = updated();
  badProject.data.issueUpdate.issue.project.id = 'cis-project';
  for (const response of [updated(false), badProject, { errors: [{ message: secret }] },
    new Error(secret)]) {
    const mock = mockFetch([lookup(), lookup(), response]);
    await assert.rejects(routeWith(mock), (error) => !error.message.includes(secret));
    assert.equal(mutationCalls(mock).length, 1);
    assert.equal(mock.calls.length, 3);
  }
});

test('a mismatched readback is a failure rather than reported success', async () => {
  const mock = mockFetch([lookup(), lookup(), updated(), lookup()]);
  await assert.rejects(routeWith(mock), /readback did not match/);
  assert.equal(mutationCalls(mock).length, 1);
});

test('missing Linear key or opened-issue node ID fails before network access', async () => {
  for (const options of [{ env: { ...env, LINEAR_API_KEY: '' } },
    { event: { ...event, issue: { ...event.issue, node_id: null } } }]) {
    const mock = mockFetch([]);
    await assert.rejects(routeWith(mock, options));
    assert.equal(mock.calls.length, 0);
  }
});

test('manual retries resolve the real GitHub node ID with the separate read-only token', async () => {
  const manualEnv = { ...env, GITHUB_EVENT_NAME: 'workflow_dispatch' };
  const manualEvent = { repository: event.repository, inputs: { issue_number: '8' } };
  const mock = mockFetch([event.issue, lookup([attachment({ project: { id: PROJECT_ID } })])]);
  const result = await routeWith(mock, { event: manualEvent, env: manualEnv });
  assert.equal(result.reason, 'already-routed');
  assert.equal(mock.calls[0].url, `https://api.github.com/repos/${REPOSITORY}/issues/8`);
  assert.equal(mock.calls[0].options.headers.Authorization, `Bearer ${githubSecret}`);
  assert.equal(mock.calls[1].options.headers.Authorization, secret);
  assert.equal(mutationCalls(mock).length, 0);
});

test('manual retry rejects non-main refs, shell strings, missing token, PRs and wrong GitHub URL', async () => {
  const manualEnv = { ...env, GITHUB_EVENT_NAME: 'workflow_dispatch' };
  const manualEvent = { repository: event.repository, inputs: { issue_number: '8' } };
  for (const options of [
    { env: { ...manualEnv, GITHUB_REF: 'refs/heads/untrusted' } },
    { env: { ...manualEnv, GITHUB_TOKEN: '' } },
    { event: { ...manualEvent, inputs: { issue_number: '8; echo bad' } } },
    { event: { ...manualEvent, inputs: { issue_number: '1e2' } } },
  ]) {
    const mock = mockFetch([]);
    await assert.rejects(routeWith(mock, { event: manualEvent, env: manualEnv, ...options }));
    assert.equal(mock.calls.length, 0);
  }
  for (const issue of [{ ...event.issue, pull_request: { url } },
    { ...event.issue, html_url: 'https://github.com/FlipBelt/CIS/issues/8' }]) {
    const mock = mockFetch([issue]);
    await assert.rejects(routeWith(mock, { event: manualEvent, env: manualEnv }));
    assert.equal(mock.calls.length, 1);
  }
});

test('issue content is never sent to Linear or evaluated', async () => {
  const mock = mockFetch([lookup([attachment({ project: { id: PROJECT_ID } })])]);
  await routeWith(mock, { event: { ...event, issue: { ...event.issue,
    title: '$(echo untrusted)', body: '`echo unsafe`',
  } } });
  assert.deepEqual(mock.calls[0].body.variables, { url });
});

test('CLI reports missing secret and upstream failures without printing sensitive values', async () => {
  const messages = [];
  const options = { readEvent: async () => JSON.stringify(event),
    log: (message) => messages.push(message), logError: (message) => messages.push(message) };
  assert.equal(await runCli({ ...options, env: { ...env, LINEAR_API_KEY: '' } }), 1);
  assert.match(messages[0], /LINEAR_API_KEY is missing/);
  const mock = mockFetch([{ errors: [{ message: `${secret} ${githubSecret}` }] }]);
  assert.equal(await runCli({ ...options, env, fetchImpl: mock.fetchImpl }), 1);
  assert.equal(await runCli({ ...options, env, readEvent: async () => { throw new Error(secret); } }), 1);
  assert.ok(messages.every((message) => !message.includes(secret) && !message.includes(githubSecret)));
});

test('workflow keeps secrets out of shell expressions and uses main with minimal GitHub permissions', async () => {
  const workflow = await readFile(new URL('../.github/workflows/linear-project-routing.yml', import.meta.url), 'utf8');
  assert.match(workflow, /types: \[opened\]/);
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /contents: read\s+issues: read/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /persist-credentials: false/);
  assert.match(workflow, /actions\/checkout@[a-f0-9]{40}/);
  assert.match(workflow, /LINEAR_PROJECT_ROUTING_API_KEY/);
  assert.doesNotMatch(workflow, /pull_request|issues: write|contents: write/);
  assert.match(workflow, /run: node scripts\/linear-project-routing\.mjs\s*$/);
  assert.equal(validateEvent(event, env).url, url);
});
