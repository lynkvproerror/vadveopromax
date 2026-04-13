# Pre-Submit Block And Stage-Retry Report

Status: analysis only. No code was changed.

Scope:
- Explain why many tasks appear stuck at `0%` or stay a long time around gate check.
- Clarify what is expected backpressure vs what is actual bug.
- Propose a handling direction that keeps high `foreman` count.
- Maximize asynchronous submit throughput.
- Increase per-task submit reliability.
- Move from "task can fail at any stage" to "stage-level retry until done" for transient failures.

Based on:
- Runtime logs around `dev_logs_20260412_053023.txt`
- Runtime logs around the `05:54:48 -> 05:56:36` session snippet
- Code inspection in:
  - `core/engine.py`
  - `core/dispatcher.py`
  - `core/extension_bridge.py`
  - `core/upscale_queue.py`

## 1. Executive Summary

The main problem is not that `submit_prompt()` itself hangs forever.

The real problem is that too many tasks are entering fragile pre-submit phases at the same time on the same account:
- prewarm
- reCAPTCHA recovery
- gate check
- adaptive burst delay
- submit admission

This creates three classes of damage:
- Tasks look stuck at `0%` because they are blocked before real submit.
- Soft recovery can reset page/frame state while other foremen are still preparing to submit.
- Dispatcher can repeatedly re-reserve the same task, causing queue churn and fake running pressure.

The right fix is not "reduce foremen".

The right fix is:
- keep foremen for poll/download/upscale parallelism
- add a per-account `SubmitCoordinator`
- serialize only the fragile pre-submit path
- add explicit waiting states
- convert transient failures into stage retries instead of task failure

## 2. What Is Expected vs What Is Broken

### 2.1 Expected blocking

These are intentional and should not be treated as bugs:

- `Cold profile gate` waiting for second successful submit
- `AdaptiveBurst` sleep before submit
- Temporary waiting for reCAPTCHA token
- Poll/download/upscale concurrency limits

These are legitimate throughput controls.

### 2.2 Broken blocking

These are the actual issues:

1. Forced prewarm / soft recovery can run while other tasks are still in pre-submit.
2. Recovery lock makes tasks wait without an explicit user-visible state.
3. Dispatcher reserve/requeue lifecycle allows the same task to be reserved repeatedly.
4. The system treats many transient stage failures as task failures too early.

## 3. Key Findings From Logs

### 3.1 "Gate passed" does not mean "submit started"

In `core/engine.py`, real submit starts only at:
- [engine.py:4491](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L4491)

Progress text `Submitting...` is only set right before extension submit at:
- [engine.py:4463](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L4463)

Therefore, when a task stays at `0%`, it usually means it never reached the real extension submit call.

### 3.2 `submit_prompt()` is not the main infinite blocker

`submit_prompt()` already has:
- per-account submit semaphore
- future-based response tracking
- timeout
- cleanup of pending request state

Relevant code:
- [extension_bridge.py:1132](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py#L1132)
- [extension_bridge.py:1187](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py#L1187)
- [extension_bridge.py:1227](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py#L1227)
- [extension_bridge.py:1233](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py#L1233)

So the dominant stuck symptom is before submit, not inside the bridge wait itself.

### 3.3 Dispatcher repeatedly reserves the same task

The strongest bug signal is repeated `READY -> RESERVED` lines for the same task id while `running_count` does not increase proportionally.

This was observed earlier on tasks such as:
- `task_12`
- `task_59`
- `task_60`
- replacement tasks like `task_3_retry...`

In the current session snippet, the same pattern appears again for `task_12`.

This points to a reserve / dedup lifecycle bug in `core/dispatcher.py`, not a simple slow gate.

### 3.4 Forced prewarm can break another task's submit context

Code already documents the risk:
- [engine.py:2735](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L2735)

This comment is correct: soft recovery navigates the page away and can abort active page-context work.

In the provided session:
- `05:56:18` task `12` is picked
- immediately after, forced prewarm triggers soft recovery
- `05:56:21` bridge reports `grecaptcha NOT ready ... Frame with ID 0 was removed`

This is direct evidence that prewarm/recovery is colliding with live work.

### 3.5 reCAPTCHA recovery lock is a real blocking point

Relevant code:
- [engine.py:8570](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L8570)

The log shows:
- `reCAPTCHA recovery already in progress by another foreman - waiting for lock...`

This is a true block, but the UI does not express it clearly, so it looks like a hung `0%` task.

## 4. Root Causes

### RC1. Too many foremen touch pre-submit on one account at the same time

Foremen are currently used for everything:
- picking tasks
- prewarm
- gate check
- burst delay
- submit
- poll/download handoff

This is good for throughput after submit, but harmful before submit.

### RC2. Prewarm guard is too narrow

Current guard only checks for submit in-flight using the bridge semaphore:
- [engine.py:2737](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L2737)

It does not guard against:
- gate wait
- burst sleep
- reCAPTCHA recovery
- frame re-upload
- other pre-submit preparation

So it can still fire at the wrong time.

### RC3. Dispatcher dedup is too weak during reserve/requeue transitions

Critical path:
- [dispatcher.py:575](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L575)
- [dispatcher.py:661](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L661)
- [dispatcher.py:677](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L677)

The queue dedup marker is discarded very early, and the system has many places that can `discard + enqueue` the same task id again.

Result:
- same task can be reintroduced to the queue
- same task can be re-reserved repeatedly
- UI and logs suggest progress, but real work is not advancing

### RC4. The state model is too coarse

Today many very different phases all look similar from the outside:
- waiting for capacity
- waiting for required account
- waiting for reCAPTCHA recovery lock
- prewarm in progress
- gate check
- adaptive burst delay

This makes legitimate backpressure indistinguishable from real bugs.

### RC5. Retry semantics are task-centric, not stage-centric

Current system still escalates many failures to `fail_task()` too early.

This is visible in:
- submit retry loops in `engine.py`
- download retry limits in `engine.py`
- upscale job retry exhaustion in `upscale_queue.py`

If the goal is "no prompt task fails unless it is structurally impossible", the architecture must move to stage-level durable retries.

## 5. Design Goals

The implementation direction should satisfy all of the following:

1. Do not reduce `foreman` count globally.
2. Keep poll/download/upscale highly parallel.
3. Reduce only pre-submit contention.
4. Increase probability that each prompt submit succeeds on the first real attempt.
5. Convert transient errors into stage retries, not task failure.
6. Preserve checkpoints across retries.
7. Expose waiting states explicitly in UI and logs.

## 6. Recommended Architecture

### 6.1 Keep foremen, but add per-account SubmitCoordinator

Do not reduce foremen.

Instead, split account execution into two layers:

- `Foreman layer`
  - many coroutines
  - good for queue draining, polling, downloading, upscale orchestration

- `SubmitCoordinator layer`
  - small number of fragile submit lanes per account
  - owns:
    - prewarm
    - reCAPTCHA recovery
    - gate check
    - adaptive burst
    - actual submit

Recommended initial model:
- `foremen/account`: keep current logic
- `submit_lanes/account`: 1 or 2

This preserves overall concurrency while preventing pre-submit collisions.

### 6.2 Add readiness lease before real submit

Before a task is allowed to enter `Submitting`, it should acquire a readiness lease for the account.

Lease should require:
- bridge connected
- no soft recovery running
- no reCAPTCHA recovery in progress
- no forced prewarm in progress
- token/header freshness acceptable
- submit lane available

If lease is not available, the task should move to a waiting state, not remain an ambiguous `0% RUNNING`.

### 6.3 Track pre-submit activity explicitly

Add a per-account counter or structured state tracker:
- `pre_submit_active[email]`

This should count tasks in:
- prewarm
- gate check
- reCAPTCHA recovery
- burst delay
- pre-submit frame upload

Then `_maybe_prewarm()` must skip when this count is non-zero.

This is the correct extension of the existing narrow submit-semaphore guard.

### 6.4 Promote waiting states to first-class runtime states

Introduce explicit internal states or at least explicit progress/status text for:
- `WAITING_SUBMIT_SLOT`
- `WAITING_CAPACITY`
- `WAITING_REQUIRED_ACCOUNT`
- `RECOVERING_RECAPTCHA`
- `PREWARMING`
- `BURST_DELAY`

This does not just improve UX.
It also makes debugging and watchdog logic materially safer.

## 7. Specific Fix Directions

### P1. Harden prewarm guard

Primary files:
- [engine.py:2735](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L2735)
- [engine.py:2782](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L2782)
- [engine.py:4190](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L4190)

Action:
- skip forced prewarm if any task on the account is in a fragile pre-submit phase
- re-check the same condition inside the per-account prewarm lock

Why:
- prevents page navigation from blowing away active page context
- directly reduces `Frame with ID 0 was removed`
- reduces false reCAPTCHA failures

### P2. Fix dispatcher reserve/requeue lifecycle

Primary files:
- [dispatcher.py:575](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L575)
- [dispatcher.py:661](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L661)
- [dispatcher.py:677](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L677)
- [dispatcher.py:2056](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L2056)

Action:
- strengthen dedup so a claimed task cannot be re-enqueued silently
- ensure `get_next_task()` will not hand out a task that is already in claimed/pre-submit ownership
- preserve progress for capacity waits
- keep D2 affinity semantics separate from capacity wait semantics

Why:
- removes repeated `READY -> RESERVED` spam
- prevents fake running pressure
- stops queue churn that blocks real progress

### P3. Replace sleep-based capacity churn with event-driven wait

Primary files:
- [engine.py:3977](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L3977)
- [engine.py:5203](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L5203)
- [engine.py:5356](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L5356)

Action:
- for worker-capacity requeue, use `preserve_progress=True`
- wait on worker-release events instead of pure timed sleep loops

Why:
- tasks no longer visually reset and churn
- avoids synchronized retry storms
- preserves throughput while reducing fake "stuck at 0%" perception

### P4. Keep D2 affinity requeue at `0%`, but show explicit reason

Relevant path:
- [engine.py:3996](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L3996)

Decision:
- D2 affinity mismatch should stay at `0%`
- but should set status text like `Waiting for required account`

Why:
- this is routing correction, not real progress regression
- preserving progress here would misrepresent actual work done

## 8. Retry-Until-Done Strategy

If the desired product rule is:

"No prompt task should fail for transient submit, 720p download, or upscale problems"

then the system must stop using task failure as the primary recovery mechanism for transient errors.

### 8.1 Error classes

Every stage error should be classified into one of three types:

1. `Transient`
   - timeout
   - reCAPTCHA not ready
   - 403 after stale session/recovery race
   - temporary download corruption
   - polling miss
   - temporary TRPC/FIFE/GCS failure

2. `Repairable`
   - stale media id
   - stale token/header
   - stale browser frame
   - prompt/body can be sanitized automatically

3. `Structural`
   - unsafe generation
   - permanently invalid input
   - policy/license restrictions
   - missing required local asset

Only structural errors should become hard task failure.

### 8.2 Submit path

Current path still relies on retry loops and then `fail_task()` in multiple places inside `engine.py`.

Direction:
- keep checkpoint
- on transient submit failure, requeue into `RECOVERING_SUBMIT`
- reacquire readiness lease
- retry same stage with bounded backoff and jitter
- no task-level failure for transient submit issues

### 8.3 720p download path

Current code already has auto re-generation logic for failed downloads:
- [engine.py:8015](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L8015)

Direction:
- keep this, but evolve it into a durable stage retry queue
- do not hard-fail task on transient 720p download issues
- task stays in a recoverable state until missing outputs are regenerated and downloaded

### 8.4 Upscale path

UpscaleQueue already has meaningful recovery structure:
- job-level retries
- partial retries
- poll retry logic
- TRPC/FIFE download fallback

Relevant locations:
- [upscale_queue.py:194](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L194)
- [upscale_queue.py:1690](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1690)
- [upscale_queue.py:1748](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1748)

But it still exhausts retries and then degrades completion.

Direction:
- for transient upscale submit/poll/download errors, keep the job in a durable retry queue
- use long backoff
- do not downgrade the parent task to "completed with warning" too early
- only stop when error is structural or policy-based

## 9. "No Task Fail" Semantics

The desired product behavior can be expressed as:

- transient error -> retry same stage until success
- repairable error -> repair then retry same stage
- structural error -> stop trying, but expose explicit blocked reason

That means the state machine should include:
- `RECOVERING_SUBMIT`
- `RECOVERING_DOWNLOAD`
- `RECOVERING_UPSCALE`
- `BLOCKED_POLICY`
- `BLOCKED_INPUT`

This is better than overusing `FAILED`.

Important:
- do not do infinite tight retry loops
- use durable retry with backoff
- preserve journal/checkpoint state
- surface retry reason to logs and UI

## 10. Recommended Priority Order

1. Fix prewarm collisions in `engine.py`
2. Fix dispatcher reserve/dedup churn in `dispatcher.py`
3. Introduce submit-lane coordination per account
4. Improve observability for wait states
5. Convert submit/download/upscale retries from task-failure semantics to stage-retry semantics

This order gives the best payoff:
- first stop active interference
- then stop queue churn
- then raise success rate
- then remove remaining user-visible "false stuck" states

## 11. Concrete Implementation Direction

### Phase A: Correctness first

- add `pre_submit_active` tracking
- skip forced prewarm if account has any active pre-submit work
- make recovery lock visible as a first-class wait state
- fix dispatcher duplicate reserve behavior

### Phase B: Submit throughput without reducing foremen

- add per-account `SubmitCoordinator`
- allocate `submit_lanes` independently from `foremen`
- allow many foremen for post-submit work
- allow only a small number of concurrent fragile pre-submit paths

### Phase C: Stage-level durable recovery

- submit recovery queue
- 720p regeneration/download recovery queue
- upscale durable retry queue
- structural-error classification to avoid infinite futile retry

## 12. Validation Checklist

After implementation, validate all of the following:

- same task id no longer logs repeated `READY -> RESERVED` spam
- forced prewarm logs `SKIP` while pre-submit activity exists
- tasks waiting for recovery or submit slot show explicit progress/status text
- transient submit failures do not produce `FAILED` task state
- 720p transient failures do not produce `FAILED` task state
- upscale transient failures do not complete task in degraded mode too early
- throughput remains high because foremen are still numerous
- submit success rate improves because fragile phases are coordinated

## 13. Final Recommendation

Do not solve this by lowering `foreman`.

Solve it by separating concerns:
- many foremen for asynchronous work after submit
- few coordinated submit lanes for fragile pre-submit work
- durable stage retry instead of premature task failure

That is the cleanest way to:
- reduce blocking
- preserve async submit speed
- improve per-prompt submit reliability
- and approach the requirement that no prompt task fails due to transient submit, download, or upscale issues

## 14. Additional Findings From `dev_logs_20260412_064520.txt`

This later log confirms that the original pre-submit analysis is still correct, but it also exposes two more gaps:
- failure semantics are still too coarse after `DOWNLOADED_720`
- target quality and preview data are not kept in sync

### 14.1 Failure handling is still not precise enough after `DOWNLOADED_720`

The current system still collapses several different upscale-submit outcomes into the same generic path:
- true submit failure
- idempotent conflict (`HTTP 409 Requested entity already exists`)
- ambiguous success (`HTTP 200` but `operations=[]`)

Observed in log:
- `06:31:03`, `06:31:29`, `06:31:32`, `06:32:14`, `06:32:44`, `06:32:48`, `06:32:53`, `06:33:03`, `06:33:33`, `06:33:56`, `06:37:01`, `06:37:30`
- the pattern is:
  - `submit_upscale ... HTTP 409 — Requested entity already exists`
  - then `HTTP 200 OK but NO operations returned`
  - then `No successful submits ... re-enqueue attempt 1/3`

This is semantically too weak.

`HTTP 409 already exists` is not equivalent to "submit failed".
It usually means the server believes the target upscale entity or request already exists.
Treating it as a normal failed submit wastes retry budget and increases queue age without increasing certainty.

Relevant retry-exhaustion path:
- [upscale_queue.py:1690](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1690)
- [upscale_queue.py:1714](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1714)
- [upscale_queue.py:1728](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1728)

Current behavior after retries exhaust:
- mark upscale failed
- update progress to `Upscale failed — 720p saved`
- call `complete_task()`

This directly conflicts with the product goal:
- transient or ambiguous stage errors should not become terminal task outcomes

### 14.2 `409 already exists` needs an idempotent recovery path

The missing state here is not "retry submit again exactly the same way".

The missing state is:
- `RECOVERING_UPSCALE_SUBMIT`

When upscale submit returns `409 already exists`, the system should assume:
- the upscale request may already have been accepted previously
- or the remote entity exists and the client has lost the operation binding

That means the next action should be a recovery lookup, not a generic submit retry.

Recommended handling direction:
- classify `409 already exists` as `idempotent ambiguous success`
- attempt to rediscover the existing upscale operation or output
- only if rediscovery fails should the job consume retry budget

Where this needs to be handled:
- the upscale submit response classification in the queue submit path
- the job state machine in [upscale_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py)

Why:
- the log shows repeated `409` conflicts interleaved with successful `1080p` downloads for nearby tasks
- this means the system is operating in an ambiguous idempotent environment, not a simple binary success/failure environment

### 14.3 Resume from `DOWNLOADED_720` still has weak progress semantics

The log repeatedly shows tasks like:
- `Task ...: RESUMING from stage downloaded_720 → concurrent pipeline`

But these tasks are also picked with:
- `[running/downloaded_720] progress=0%`

This produces two problems:
- the task looks like it regressed to zero even though it already has a valid `720p` artifact
- it hides the fact that the task is no longer in initial submit flow; it is in upscale-resume flow

Relevant resume path:
- [engine.py:7638](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L7638)
- [engine.py:7644](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L7644)
- [engine.py:7657](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L7657)

The code does update progress to `88` once it enters the inline resume path, but the persisted/picked state can still appear as `0%`.

Direction:
- `DOWNLOADED_720` should be treated as a real checkpoint with non-zero progress semantics
- a task resumed from this checkpoint should display a stage-specific label such as `Waiting for upscale`, `Resuming upscale`, or `Recovering upscale submit`
- it should not visually resemble a brand-new task

### 14.4 Target quality and thumbnail preview can diverge

This is the clearest target-data mismatch found in the code.

Current flow:
- after `720p` download, the engine generates thumbnail from the `720p` file
- later, video upscale download updates `file_upscaled` and `quality`
- but video upscale path does not regenerate thumbnail

720p thumbnail creation:
- [engine.py:5575](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L5575)
- [engine.py:5580](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L5580)

Video upscale download path explicitly disables thumbnail generation:
- [upscale_queue.py:2110](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2110)
- [upscale_queue.py:2150](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2150)
- [upscale_queue.py:2190](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2190)

After that, only `file_upscaled` and `quality` are updated:
- [upscale_queue.py:2205](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2205)
- [upscale_queue.py:2206](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2206)

But the UI DTO still exports both:
- `target_quality`
- `thumbnail_path`

Relevant UI payload fields:
- [app_controller.py:5511](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py#L5511)
- [app_controller.py:5520](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py#L5520)
- [app_controller.py:5550](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py#L5550)
- [app_controller.py:5575](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py#L5575)

Result:
- target/result can already be `1080p`
- `best_file` can resolve to `file_upscaled`
- but thumbnail can still be the old `720p` preview

That is exactly the mismatch reported by the user:
- target is upscale
- preview still shows `720p`

Important contrast:
- image upscale path already regenerates thumbnail after success
- see [upscale_queue.py:2775](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2775) to [upscale_queue.py:2788](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2788)
- video upscale path has no equivalent update

### 14.5 Some hard-fail paths still violate the "retry until done" goal

This is not limited to upscale submit.

There are still explicit bounded retry exhaustion paths that convert transient stage problems into terminal task outcomes.

Examples:
- download re-generation exhaustion -> `fail_task()`
  - [engine.py:9427](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L9427)
  - [engine.py:9440](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L9440)
- upscale job exhaustion -> degrade complete with `720p saved`
  - [upscale_queue.py:1714](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1714)
  - [upscale_queue.py:1729](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1729)

This means the current runtime is still:
- retry a few times
- then fail or degrade

It is not yet:
- durable stage retry until done, unless structurally impossible

## 15. Additional Fix Directions

### 15.1 Split upscale submit outcomes into distinct classes

Upscale submit needs at least four outcome classes:
- `SUCCESS_WITH_OPERATION`
- `IDEMPOTENT_ALREADY_EXISTS`
- `AMBIGUOUS_SUCCESS_NO_OPERATION`
- `TRUE_SUBMIT_FAILURE`

Why:
- these are operationally different
- they should not consume the same retry budget

### 15.2 Add rediscovery after `409` or `200 + operations=[]`

After idempotent or ambiguous submit outcomes, the next step should be:
- attempt to rediscover the existing upscale operation or final media
- bind it back to the task/job
- then continue with poll/download

This is the missing bridge between:
- "server may already have the upscale"
- and
- "client currently thinks no successful submit happened"

### 15.3 Make target data authoritative and preview-source explicit

The runtime currently mixes three concepts:
- requested target quality
- best available output file
- current thumbnail preview source

These should be tracked separately.

Recommended model:
- `target_quality`
- `final_quality`
- `preview_source_quality`
- `thumbnail_path`

Why:
- a task can legitimately be "target=1080p, final=1080p, preview_source=720p"
- that should be visible and temporary, not silently wrong

### 15.4 Regenerate video thumbnail after successful upscale download

This is the simplest correctness fix for the preview mismatch.

Direction:
- after video upscale download succeeds, regenerate thumbnail from `file_upscaled`
- update both `video_outputs[i].thumbnail_path` and task-level thumbnail collection

Why:
- image upscale path already does this
- video upscale path should follow the same principle

### 15.5 Promote `DOWNLOADED_720` and `UPSCALING` to durable UI checkpoints

A task that already has local `720p` is not a fresh `0%` task.

Direction:
- preserve non-zero progress/state across resume
- expose `Waiting for upscale`, `Retrying upscale submit`, `Recovering existing upscale`, `Downloading 1080p`

Why:
- prevents false regression
- makes long-running upscale queues understandable

### 15.6 Adjust the previous report: `preserve_progress` already exists

One correction to the earlier plan:
- `dispatcher.requeue_task(... preserve_progress=...)` is already implemented in [dispatcher.py:2056](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/dispatcher.py#L2056)

So the remaining issue is not "add preserve_progress support".

The remaining issue is:
- use it consistently at the right call sites
- pair it with explicit status text
- stop regressing resumed/upscale-owned tasks to visually ambiguous states

## 16. Updated Priority Order

Add the following to the original priority list:

1. Stop prewarm/recovery collisions in the pre-submit path.
2. Stop dispatcher reserve churn.
3. Introduce submit-lane coordination.
4. Reclassify upscale submit outcomes, especially `409` and `200 + operations=[]`.
5. Convert `DOWNLOADED_720 -> UPSCALING` into a durable, non-zero checkpoint path.
6. Regenerate video thumbnails from final upscaled output.
7. Remove bounded terminal failure for transient download/upscale paths.

## 17. Final Augmented Recommendation

The system now needs two additional guarantees beyond the original pre-submit fixes:

- failure handling must distinguish ambiguous/idempotent upscale submit from true failure
- target quality, final file, and preview thumbnail must be synchronized intentionally rather than incidentally

Without these two fixes:
- retry behavior will remain wasteful and sometimes terminal too early
- UI data will continue to say "target is upscale" while showing a stale `720p` preview

That is why the next report version should treat:
- `submit reliability`
- `durable stage recovery`
- `target/preview data coherence`

as one combined reliability problem, not three separate cosmetic issues.
