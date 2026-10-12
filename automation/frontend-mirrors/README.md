# Frontend mirror patches — awaiting connector write access

These are the tested freshness changes for the independently deployed language mirrors. They are not deployed by this directory and do not change either mirror repository. Both `github_create_tree` attempts returned the complete non-sensitive error below on 2026-10-12; no alternate write route was attempted:

```
GitHub API error 403: {"message":"Resource not accessible by integration","documentation_url":"https://docs.github.com/rest/git/trees#create-a-tree","status":"403"}
```

The authenticated user's reported repository `push=true` does not prove that the active integration may write these organization repositories. Restore the current GitHub connection's relevant repository access before committing these changes through the authorized adapter.

| Patch | Repository | Expected main baseline | Expected updated index.html SHA-256 |
|---|---|---|---|
| `aibubble-cn.patch` | `aibubble-cn/aibubble-cn.github.io` | `ec211cc649cc6c23db7f677242ac6040c07a0ea3` | `59ab062c6431e710e6c0e7939bdfc58bb3e8580ccb0990dc1e3dec2184694d4d` |
| `bubblewatch.patch` | `bubblewatch/bubblewatch.github.io` | `bf9d5bd93d15c53f3621d9ba28b46f83edc4723f` | `b379b2eb7a6a73861f2c6eebb04f24c2575bb1ffb173bfbf8d561c3b6aa0b2ba` |

After refreshing the exact target repository and checking the baseline, apply its patch to `index.html` and run `git diff --check`. If main changed, inspect the new head and reconcile; never blindly force a patch or reset someone else's work. Commit only the intended frontend change with the existing authorized GitHub adapter. No research run, historical snapshot edit, outbox write or workflow_dispatch is required.

The patches implement `new` without a badge, `current` as 最新披露 / Latest filing, and `stale` as STALE. Missing or unknown freshness keeps the old behavior. The actual inline renderer suite tested 21 cases across all three pages; all 75 cards from the real Issue #28 fixture remained byte-identical.

Use the main repository's renderer test with the staged mirror page paths:

```sh
node tests/frontend_freshness.test.js docs/index.html /path/to/chinese/index.html /path/to/english/index.html
```

Publishing a patch here is a reviewable handoff only; it is not proof that either mirror frontend has been committed or deployed.
