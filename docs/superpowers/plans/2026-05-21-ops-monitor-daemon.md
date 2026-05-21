# Ops Monitor Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single long-running operations monitor entrypoint that syncs competitor monitor jobs, schedules due research jobs, and runs the existing crawl worker loop.

**Architecture:** Add a small orchestration module that composes existing services instead of replacing them: `create_competitor_monitor_jobs`, `ResearchScheduler`, and `ResearchWorker`. Provide a script entrypoint for local Windows use and later server deployment, with `--once` for safe validation.

**Tech Stack:** Python asyncio, existing MediaCrawler research repository, scheduler, worker, crawler manager, pytest.

---

### Task 1: Orchestration Module

**Files:**
- Create: `research/ops_monitor.py`
- Test: `tests/test_ops_monitor.py`

- [ ] **Step 1: Write tests for one cycle**

Create a fake repository, scheduler, and worker. Verify one cycle syncs competitor jobs, schedules pending jobs, and runs the worker a configured number of times.

- [ ] **Step 2: Implement `OpsMonitorService.run_once`**

Add a class that accepts injected dependencies for testability and returns a structured stats dictionary.

- [ ] **Step 3: Run test**

Run: `pytest tests/test_ops_monitor.py -q`
Expected: PASS.

### Task 2: CLI Entrypoint

**Files:**
- Create: `scripts/run_ops_monitor.py`
- Modify: `research/ops_monitor.py`
- Test: `tests/test_ops_monitor.py`

- [ ] **Step 1: Add CLI parser**

Support `--once`, `--interval`, `--worker-id`, `--worker-iterations`, `--monitor-interval-minutes`, `--latest-limit`, `--save-option`, and `--headless`.

- [ ] **Step 2: Add loop function**

Loop by calling `run_once`, sleeping for `--interval` seconds between cycles.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_ops_monitor.py -q`
Expected: PASS.

### Task 3: Documentation

**Files:**
- Create: `docs/ops-monitor-daemon.md`

- [ ] **Step 1: Document local commands**

Include one-shot validation and long-running commands for PowerShell.

- [ ] **Step 2: Document production notes**

Explain that public traffic means public content and public engagement metrics, and that the process must keep running for scheduled monitoring.

### Task 4: Verification

**Files:**
- Existing tests only.

- [ ] **Step 1: Run focused backend tests**

Run: `pytest tests/test_ops_monitor.py tests/test_competitor_public_flow.py tests/test_research_crawl_units.py -q`
Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run: `npm.cmd run build`
Expected: PASS with only existing chunk-size warning.
