# Ops Growth Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable operations growth loop without removing existing MediaCrawler features.

**Architecture:** Reuse existing research models and routers. Add compatible service modules for tracking-pack scheduling, content fingerprinting, creator tiering, auto-pooling, competitor automation, and keyword sampling advice. Existing APIs continue to work; new endpoints layer on top of current scene packs, content trackers, creator candidates, and monitor pools.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async ORM, pytest, React/Vite/TypeScript.

---

## File Structure

- Create `research/tracking_packs.py`: build effective keyword packs from scene packs and keywords, create daily sampling jobs, and expose run summaries.
- Create `research/content_fingerprint.py`: deterministic text-only content summaries and fingerprints for posts.
- Create `research/candidate_tiering.py`: A/B/C creator tier scoring, evidence, and auto-pool eligibility.
- Create `research/auto_pooling.py`: add A-tier creators into monitor pools with guardrails and daily caps.
- Modify `research/postprocess.py`: run content fingerprinting, creator rebuild, candidate extraction, tiering, auto-pooling, tracker snapshots, heat snapshots, and competitor snapshots after crawl.
- Modify `research/keyword_heat.py`: add sample-confidence advice to heat outputs.
- Modify `research/monitor_pools.py`: support monitor levels and compatible schedule intervals through payload metadata.
- Modify `api/routers/keyword_library.py`: add tracking-pack preview and daily sampling endpoints.
- Modify `api/routers/creator_search.py`: add candidate tiering and auto-pool endpoints.
- Modify `api/routers/content_tracking.py`: expose fingerprint analysis in content tracking responses.
- Modify `api/routers/competitors.py`: add account URL creation helper and rebuild-all endpoint.
- Modify `api/webui/src/pages/ResearchModulePages.tsx`: add operational controls to existing pages, without touching Overview.
- Add focused tests in `tests/test_tracking_packs.py`, `tests/test_candidate_tiering.py`, `tests/test_auto_pooling.py`, `tests/test_ops_postprocess_workflow.py`, and extend existing API tests.

## Task 1: Tracking Pack Scheduling

- [ ] Add tests for building effective keywords from scene-pack keywords, platform filtering, negative keyword separation, and daily sample job creation.
- [ ] Implement `build_tracking_pack()` and `create_daily_sampling_jobs()` in `research/tracking_packs.py`.
- [ ] Add `POST /api/keyword-library/scene-packs/{id}/sampling-jobs` and `GET /api/keyword-library/scene-packs/{id}/tracking-pack`.
- [ ] Verify with `pytest tests/test_tracking_packs.py tests/test_keyword_library_api.py -q`.

## Task 2: Text Content Fingerprints

- [ ] Add tests for deterministic text fingerprints from posts with audience, topic, pain point, content type, conversion intent, summary, and confidence.
- [ ] Implement `build_content_fingerprint()` and `analyze_posts_for_tracking()`.
- [ ] Include fingerprints in `/api/content-tracking/analyze` responses.
- [ ] Verify with `pytest tests/test_content_tracking_workflow.py tests/test_content_tracking_api.py -q`.

## Task 3: Creator A/B/C Tiering

- [ ] Add tests for A/B/C thresholds, negative flags, evidence completeness, and representative posts.
- [ ] Implement `tier_creator_candidate()` and `tier_creator_candidates()`.
- [ ] Add candidate response fields without schema-breaking database migration by storing tier metadata in `evidence_json`.
- [ ] Verify with `pytest tests/test_candidate_tiering.py tests/test_creator_discovery_scoring.py -q`.

## Task 4: Auto-Pooling Guardrails

- [ ] Add tests for score >= 75 auto-add, daily cap, negative flag blocking, duplicate blocking, and B/C no auto-add.
- [ ] Implement `auto_pool_a_tier_candidates()` using existing monitor-pool methods.
- [ ] Add `POST /api/creator-search/candidate-pool/auto-pool`.
- [ ] Verify with `pytest tests/test_auto_pooling.py tests/test_monitor_pools.py -q`.

## Task 5: Post-Crawl Workflow

- [ ] Add tests proving `run_post_crawl_analysis()` runs tagging, profile rebuild, candidate extraction, tiering, auto-pooling, content snapshot, heat snapshot, and competitor composition snapshot when methods exist.
- [ ] Modify `research/postprocess.py` to orchestrate these steps compatibly.
- [ ] Keep existing skip behavior when repository methods are unavailable.
- [ ] Verify with `pytest tests/test_creator_discovery_postprocess.py tests/test_ops_postprocess_workflow.py -q`.

## Task 6: Keyword Heat Confidence Advice

- [ ] Add tests for low sample advice, medium confidence advice, and high-confidence no-op advice.
- [ ] Add `sampling_advice` to heat signal evidence outputs.
- [ ] Persist advice in keyword heat snapshot evidence.
- [ ] Verify with `pytest tests/test_keyword_heat.py tests/test_keyword_heat_dual_track.py tests/test_keyword_opportunities.py -q`.

## Task 7: Competitor Automation

- [ ] Add tests for creating competitors from profile URL/account id and rebuilding all enabled competitor composition snapshots.
- [ ] Add URL parser helpers for xhs/dy profile URLs.
- [ ] Add `POST /api/competitors/from-url` and `POST /api/competitors/composition/rebuild-all`.
- [ ] Verify with `pytest tests/test_competitor_monitoring.py tests/test_competitor_composition.py -q`.

## Task 8: Frontend Operations Controls

- [ ] Add non-destructive controls to existing keyword, creator, content, and competitor pages.
- [ ] Do not modify Overview page layout or route behavior.
- [ ] Show tracking pack preview, sampling-job action, A/B/C tier badges, auto-pool action, fingerprint summary, and heat sampling advice.
- [ ] Verify with `npm.cmd run build`.

## Task 9: Full Verification

- [ ] Run `pytest tests/test_tracking_packs.py tests/test_candidate_tiering.py tests/test_auto_pooling.py tests/test_ops_postprocess_workflow.py -q`.
- [ ] Run `pytest tests/test_creator_discovery_scoring.py tests/test_creator_discovery_workflow_api.py tests/test_content_tracking_workflow.py tests/test_content_tracking_api.py tests/test_competitor_monitoring.py tests/test_competitor_composition.py tests/test_keyword_heat.py tests/test_keyword_opportunities.py -q`.
- [ ] Run `npm.cmd run build`.
- [ ] Confirm no existing route or page is removed.
