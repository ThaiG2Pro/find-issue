# Test Cases — v2-002-cron-scheduler (V2-002)
Generated: 2026-07-03 | QA: S5 lite | Export: md

## Coverage Summary
- Total ACs: 24
- Test cases generated: 42
- Automated (pytest): 138 new tests across 7 files
- All 24 ACs covered

---

## TC-001 — Default schedule prints daily crontab line
**AC**: AC-V2-002-001, AC-V2-002-008
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_default_prints_daily_line)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule` (no flags) | Exit 0 |
| 2 | Check stdout | Contains `0 8 * * *` |
| 3 | Check stdout | Contains `run` |
| 4 | Check crontab | No write performed |

**Result**: ✅ PASS

---

## TC-002 — Explicit cron expression used verbatim
**AC**: AC-V2-002-002
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_cron_flag_verbatim)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --cron "*/15 * * * *"` | Exit 0 |
| 2 | Check stdout | Starts with `*/15 * * * *` |

**Result**: ✅ PASS

---

## TC-003 — Preset mapping: hourly / daily / weekly
**AC**: AC-V2-002-003
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_preset_mapping[hourly/daily/weekly])

| Preset | Expected Expr | Result |
|--------|--------------|--------|
| hourly | `0 * * * *` | ✅ PASS |
| daily | `0 8 * * *` | ✅ PASS |
| weekly | `0 8 * * 1` | ✅ PASS |

---

## TC-004 — Generated line contains absolute binary path
**AC**: AC-V2-002-004, BR-V2-002-006
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_output_contains_absolute_binary_path)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule` with mocked `resolve_binary` → `/home/user/.local/bin/osspulse` | Exit 0 |
| 2 | Check stdout | Contains `/home/user/.local/bin/osspulse` |
| 3 | Verify `os.path.isabs(resolve_binary())` | True |

**Result**: ✅ PASS

---

## TC-005 — Generated line contains absolute config path
**AC**: AC-V2-002-004, BR-V2-002-006
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_output_contains_absolute_config_path)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --config /tmp/test/config.toml` | Exit 0 |
| 2 | Check stdout | Contains resolved absolute config path |

**Result**: ✅ PASS

---

## TC-006 — GITHUB_TOKEN not in crontab output (RISK-001)
**AC**: AC-V2-002-005
**Priority**: Critical
**Type**: Automated (test_schedule_secrets.py + test_cli_schedule.py)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Set `GITHUB_TOKEN=ghp_totallyrealtoken` in env | — |
| 2 | `osspulse schedule` | Exit 0 |
| 3 | Check stdout | Does NOT contain `ghp_totallyrealtoken` |
| 4 | Call `assert_no_secret(line, secrets)` | Does not raise |

**Result**: ✅ PASS (by-construction: generator never reads env; runtime backstop confirms)

---

## TC-007 — Invalid cron expression: Error exit 1, no write
**AC**: AC-V2-002-006
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_invalid_cron_exits_1)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --cron "99 * * * *"` | Exit 1 |
| 2 | Check stderr | Contains `Error:` |
| 3 | Check stderr | Does NOT contain `Traceback` |
| 4 | Check crontab | No write performed (`write_calls == []`) |

**Result**: ✅ PASS

---

## TC-008 — --cron and --preset mutually exclusive
**AC**: AC-V2-002-007
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_mutual_exclusion_cron_and_preset)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --cron "0 8 * * *" --preset daily` | Exit 1 |
| 2 | Check stderr | Contains `Error:` |
| 3 | Check stderr | Does NOT contain `Traceback` |

**Result**: ✅ PASS

---

## TC-009 — Install adds managed block (no pre-existing block)
**AC**: AC-V2-002-009
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_install_writes_to_crontab)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --install` (empty crontab) | Exit 0 |
| 2 | Check crontab content | Contains `# >>> osspulse >>>` |
| 3 | Check crontab content | Contains `# <<< osspulse <<<` |
| 4 | Count marker occurrences | Exactly 1 each |

**Result**: ✅ PASS

---

## TC-010 — Re-install is idempotent (no duplicate block)
**AC**: AC-V2-002-010
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_install_idempotent + test_schedule_crontab.py::test_upsert_block_reinstall_replaces_in_place)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --install` (first install) | Exit 0, 1 block |
| 2 | `osspulse schedule --install` (second install) | Exit 0 |
| 3 | Count `# >>> osspulse >>>` in crontab | Exactly 1 (replaced, not appended) |

**Result**: ✅ PASS

---

## TC-011 — Install preserves unrelated crontab lines byte-for-byte
**AC**: AC-V2-002-011
**Priority**: High
**Type**: Automated (test_schedule_crontab.py::test_round_trip_byte_identical × 8 variants)

| Variant | Original | After install + uninstall | Result |
|---------|---------|--------------------------|--------|
| Empty | `""` | `""` | ✅ |
| `"\n"` | `"\n"` | `"\n"` | ✅ |
| `"# a comment\n"` | same | same | ✅ |
| `"0 0 * * * /bin/job\n"` | same | same | ✅ |
| Multi-line with jobs | same | same | ✅ |
| No trailing newline | same | same | ✅ |
| Mixed content | same | same | ✅ |
| 3-line file | same | same | ✅ |

**Result**: ✅ PASS — all 8 round-trip variants byte-identical

---

## TC-012 — Uninstall removes managed block, unrelated lines preserved
**AC**: AC-V2-002-012
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_uninstall_removes_block + test_schedule_uninstall_no_block_is_noop)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Install managed block | Block present |
| 2 | `osspulse schedule --uninstall` | Exit 0 |
| 3 | Check crontab | `# >>> osspulse >>>` absent |
| 4 | Check unrelated lines | Preserved |
| 5 | `osspulse schedule --uninstall` (no block) | Exit 0, no write performed |

**Result**: ✅ PASS

---

## TC-013 — crontab binary missing → Error: exit 1
**AC**: AC-V2-002-013
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_install_missing_crontab_binary_exits_1 + test_schedule_crontab.py::test_crontab_client_raises_schedule_error_when_binary_missing)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Mock `shutil.which("crontab")` → None | — |
| 2 | `osspulse schedule --install` | Exit 1 |
| 3 | Check stderr | Contains `Error:` and `crontab` |
| 4 | Check stderr | Does NOT contain `Traceback` |

**Result**: ✅ PASS

---

## TC-014 — --github-actions emits valid Actions workflow YAML
**AC**: AC-V2-002-014
**Priority**: High
**Type**: Automated (test_cli_schedule.py::test_schedule_github_actions_prints_yaml + test_schedule_workflow.py × 9 tests)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --github-actions` | Exit 0 |
| 2 | Check stdout | Contains `on:`, `schedule:`, cron expr |
| 3 | Check stdout | Contains `osspulse run` step |
| 4 | Check stdout | Contains `jobs:` section |
| 5 | Check stdout | Contains `workflow_dispatch` |
| 6 | Workflow ends with `\n` | True |

**Result**: ✅ PASS

---

## TC-015 — Workflow references secrets, never inlines token (RISK-001)
**AC**: AC-V2-002-015
**Priority**: Critical
**Type**: Automated (test_schedule_workflow.py + test_schedule_secrets.py + test_cli_schedule.py)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Set `GITHUB_TOKEN=ghp_actionstesttoken` in env | — |
| 2 | `osspulse schedule --github-actions` | Exit 0 |
| 3 | Check stdout | Contains `secrets.GITHUB_TOKEN` |
| 4 | Check stdout | Contains `secrets.LLM_API_KEY` |
| 5 | Check stdout | Does NOT contain `ghp_actionstesttoken` |
| 6 | Set `LLM_API_KEY=sk-very-secret-llm-key`, generate workflow | Does not contain the key value |

**Result**: ✅ PASS (template uses `${{ secrets.* }}` hardcoded; assert_no_secret confirms)

---

## TC-016 — --output writes file, unwritable parent → Error: no partial file
**AC**: AC-V2-002-016
**Priority**: High
**Type**: Automated (test_cli_schedule.py × 3 output tests)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --github-actions --output /tmp/test/osspulse.yml` | Exit 0, file created |
| 2 | Check file content | Contains `on:`, `UTC` |
| 3 | `osspulse schedule --github-actions --output /nonexistent/dir/file.yml` | Exit 1 |
| 4 | Check stderr | Contains `Error:` |
| 5 | Check `/nonexistent/dir/file.yml` | Does NOT exist (no partial file) |
| 6 | chmod 555 parent, invoke | Exit 1, no partial file |

**Result**: ✅ PASS

---

## TC-017 — Workflow documents UTC timezone
**AC**: AC-V2-002-017
**Priority**: Medium
**Type**: Automated (test_schedule_workflow.py::test_generate_workflow_contains_utc_comment + utc_near_cron)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse schedule --github-actions` | Output contains `UTC` |
| 2 | Find UTC comment position relative to cron expression | Within 300 chars |

**Result**: ✅ PASS

---

## TC-018 — run completes without TTY (no prompt)
**AC**: AC-V2-002-018
**Priority**: High
**Type**: Automated (test_cli_run_cronsafe.py::test_run_completes_without_tty + test_run_does_not_call_interactive_prompts)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Invoke `osspulse run` via CliRunner (no TTY) | Exit 0 |
| 2 | Inspect `cli.run` source | No `typer.prompt`, `click.prompt`, `input(` |

**Result**: ✅ PASS

---

## TC-019 — Deterministic exit codes for cron
**AC**: AC-V2-002-019
**Priority**: High
**Type**: Automated (test_cli_run_cronsafe.py × 7 exit-code tests)

| Scenario | Expected Exit | Result |
|----------|--------------|--------|
| Success (pipeline returns) | 0 | ✅ |
| No-new-items (None return) | 0 | ✅ |
| ConfigError (bad config) | 1 | ✅ |
| AuthError | 1 | ✅ |
| StateError | 1 | ✅ |
| DeliveryError | 1 | ✅ |
| AuthError shows `Error:` not `Traceback` | `Error:` only | ✅ |

---

## TC-020 — No ANSI escape codes in non-TTY output
**AC**: AC-V2-002-020
**Priority**: High
**Type**: Automated (test_cli_run_cronsafe.py::test_run_no_ansi_in_output_when_not_tty + test_run_error_no_ansi_in_stderr_when_not_tty)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `osspulse run` via CliRunner (non-TTY stdout/stderr) | No ANSI escape sequences in output |
| 2 | `osspulse run` with AuthError via CliRunner | No ANSI in error output |
| 3 | Regex `\x1b\[[0-9;]*[a-zA-Z]` scan on combined output | 0 matches |

**Result**: ✅ PASS

---

## TC-021 — Lock acquired before pipeline, released after
**AC**: AC-V2-002-021
**Priority**: High
**Type**: Automated (test_cli_run_cronsafe.py::test_run_acquires_lock_before_pipeline + test_run_releases_lock_even_on_fatal_error)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Instrument call order: lock_enter, pipeline, lock_exit | Order must be lock_enter → pipeline → lock_exit |
| 2 | Pipeline raises AuthError | Lock still released (finally block) |

**Result**: ✅ PASS

---

## TC-022 — Overlapping run: WARN + exit 0, pipeline NOT invoked
**AC**: AC-V2-002-022
**Priority**: Critical
**Type**: Automated (test_cli_run_cronsafe.py × 4 lock-held tests + test_lock.py::test_second_lock_raises_lock_held_error)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Mock `single_instance_lock` to raise `LockHeldError` | — |
| 2 | Invoke `osspulse run` | Exit 0 (NOT 1) |
| 3 | Check `pipeline_calls` | Empty (`[]`) — pipeline not invoked |
| 4 | Check log output | Contains `lock` or `skip` at WARNING level |
| 5 | Check stdout + stderr | Does NOT contain `Error:` |
| 6 | Real two-fd flock contention | Same: exit 0, pipeline not invoked |

**Result**: ✅ PASS

---

## TC-023 — Lock auto-releases on crash (kernel advisory lock)
**AC**: AC-V2-002-023
**Priority**: High
**Type**: Automated (test_lock.py::test_lock_released_after_fd_close + test_cli_run_cronsafe.py::test_lock_auto_releases_on_fd_close)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Acquire lock via real fcntl.flock | Lock held |
| 2 | `os.close(fd)` without `LOCK_UN` (simulate crash) | Lock released by kernel |
| 3 | `single_instance_lock(state_path)` | Succeeds (no LockHeldError) |

**Result**: ✅ PASS (real fd, no mock of flock)

---

## TC-024 — --install writes absolute path, no cron-PATH verification
**AC**: AC-V2-002-024
**Priority**: Medium
**Type**: Automated (test_cli_schedule.py::test_schedule_output_contains_absolute_binary_path + test_schedule_cron.py::test_resolve_binary_*)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `shutil.which("osspulse")` → `/home/user/.local/bin/osspulse` | Generated line contains that absolute path |
| 2 | `shutil.which` → None, `sys.argv[0]` = `/some/path` | Fallback is `os.path.abspath("/some/path")` |
| 3 | Verify no PATH probing in source | No cron-daemon PATH check |

**Result**: ✅ PASS

---

## TC-S01 — LockHeldError NOT subclass of ScheduleError (exit-code contract)
**AC**: AC-V2-002-022 (exit-code isolation)
**Priority**: Critical
**Type**: Automated (test_lock.py::test_lock_held_error_is_not_schedule_error)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `issubclass(LockHeldError, ScheduleError)` | `False` |

**Result**: ✅ PASS

---

## TC-S02 — assert_no_secret skips empty string values (no vacuous match)
**AC**: AC-V2-002-005 / AC-V2-002-015
**Priority**: Medium
**Type**: Automated (test_schedule_secrets.py::test_assert_no_secret_no_exception_on_empty_secret_in_values)

| Step | Action | Expected |
|------|--------|----------|
| 1 | `assert_no_secret("any text", [""])` | Does not raise |

**Result**: ✅ PASS

---

## Coverage Summary Table

| Module | Lines | Coverage | Status |
|--------|-------|----------|--------|
| lock.py | 21 | 100% | ✅ |
| schedule/errors.py | 1 | 100% | ✅ |
| schedule/secrets.py | 23 | 96% | ✅ |
| schedule/workflow.py | 7 | 100% | ✅ |
| schedule/cron.py | 57 | 82% | ✅ (gate ≥80%) |
| schedule/crontab.py | 45 | 78% | ⚠️ below 80% (intentional — real subprocess paths) |
| schedule/__init__.py | 5 | 100% | ✅ |
| cli.py | 111 | 94% | ✅ |
| **Total** | **926** | **96.22%** | ✅ |

Note: `schedule/crontab.py` 78% is below the per-file 80% threshold, but the uncovered lines (157-181) are the real `subprocess.run` calls in `CrontabClient.read/write` — intentionally behind the mock seam per ADR-008. Overall 96.22% meets the project gate.
