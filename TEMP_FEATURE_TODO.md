# Temporary Feature Todo (Master Ordered Backlog)

Status: Temporary working document
Created: 2026-04-09
Intent: A single ordered list of feature additions to consider for Companion V3.

## Practical Priority Override (April 2026)

Use this override when selecting work, even if lower items appear earlier in the master list.

1. Local model setup and operability features are first-priority.
2. Computer-use tangible UX/safety features are second-priority.
3. Memory reliability and pilot gating features are third-priority.

## First 15 Features To Execute

1. One-command local model bootstrap.
2. Local model profile presets.
3. Local-model readiness details in health payload.
4. Local fallback reason-code contracts.
5. Browser step-by-step preview before execution.
6. Browser action replay from audit log entries.
7. Screenshot/video artifact viewer for browser jobs.
8. Anti-stuck browser recovery loops with safe abort paths.
9. Policy explanation panel for denied/blocked tool actions.
10. mem0 readiness doctor command for local/dev setup validation.
11. Strict post-restart recall benchmark harness.
12. Hermes OFF->ON pilot go/no-go automation.
13. Pilot comparator summary endpoint.
14. Sustained and burst throughput benchmark suites.
15. Quality posture re-score publisher.

1. Automate Hermes OFF->ON pilot go/no-go gate with explicit pass/fail thresholds.
2. Add a pilot comparator summary endpoint that reports OFF vs ON deltas in one payload.
3. Add one-command rollback from pilot mode to main orchestration mode.
4. Add strict pilot mode that blocks fallback if pilot contracts are invalid.
5. Add traffic-split controls for pilot percentage and sticky session routing.
6. Add pilot endpoint token rotation support with zero-downtime reload.
7. Add immutable pilot decision audit records for each routed request.
8. Add canary dry-run mode that computes pilot decisions without user-visible routing changes.
9. Add pilot health scorecard endpoint for latency, error rate, and fallback rate.
10. Add weekly pilot report generation with trend comparisons.
11. Add mem0 readiness doctor command for local/dev setup validation.
12. Add explicit memory-backend mode indicator in UI and health payloads.
13. Add automatic mem0 reconnect with exponential backoff and bounded retries.
14. Add embeddings provider failover chain with deterministic fallback reason codes.
15. Add poison-message handling for memory write queue failures.
16. Add idempotent replay keys for memory write queue replays.
17. Add scheduled queue replay windows and replay rate controls.
18. Add strict post-restart recall benchmark harness as a first-class script.
19. Add curated recall regression prompt dataset for repeatable testing.
20. Add contradiction clustering in memory review UX.
21. Add dedup similarity threshold controls in memory review settings.
22. Add memory pinning so critical facts are never decayed by default.
23. Add memory archive/restore flows for low-value historical facts.
24. Add per-workspace memory retention policy controls.
25. Add per-session privacy mode that skips memory writes.
26. Add memory export/import flows with schema versioning.
27. Add source trust scoring to memory provenance payloads.
28. Add citation snippet previews in memory provenance drill-down.
29. Add chat-level memory correction action to fix incorrect stored facts.
30. Add optional memory TTL (forget-after-days) rules.
31. Add hybrid lexical + vector retrieval for better first-pass recall.
32. Add reranker stage with explainable scoring contributions.
33. Add retrieval query rewriting for underspecified user prompts.
34. Add retrieval freshness weighting with recency decay tuning.
35. Add retrieval filters for workspace, source type, and time range.
36. Add no-result fallback suggestions for retrieval misses.
37. Add retrieval trace-diff tool for comparing run-to-run ranking changes.
38. Add ingestion pipeline status UI for uploaded knowledge files.
39. Add large-file ingestion progress and resumable indexing jobs.
40. Add OCR extraction for image/PDF knowledge ingestion.
41. Add entity linking and lightweight relationship graph for knowledge.
42. Add related-document recommendations after retrieval responses.
43. Add incremental re-index scheduler for changed files.
44. Add duplicate-document detection in upload/index flows.
45. Add pagination and faceting to semantic search APIs.
46. Add shared knowledge collections across selected workspaces.
47. Add citation anchors with stable file/chunk offsets.
48. Add configurable source trust policy profiles.
49. Add external connector sync scheduler for knowledge connectors.
50. Add connector conflict resolution workflows for changed remote content.
51. Add slash commands in chat for common actions.
52. Add message edit-and-regenerate with branch history.
53. Add branch comparison view for alternative assistant answers.
54. Add pinned chats for long-running conversations.
55. Add folders/tags for organizing conversations.
56. Add global search across conversations, memories, and files.
57. Add one-click conversation summary cards.
58. Add daily briefing card with tasks, reminders, and continuity highlights.
59. Add proactive follow-up suggestions after completed tasks.
60. Add composer autocomplete from memory/goals context.
61. Add response modes (concise, balanced, deep-dive, planner).
62. Add citation confidence badges in chat responses.
63. Add a "why this answer" explainability drawer.
64. Add keyboard command palette for power-user navigation.
65. Add full accessibility pass targeting WCAG 2.2 AA.
66. Add mobile-first responsive layout polish for all primary panels.
67. Add unified notification center for jobs, approvals, and failures.
68. Add actionable toast deep-links to related logs or settings.
69. Add offline outgoing prompt queue with later retry.
70. Add crash-safe session restore for draft prompts and panel state.
71. Add workflow template library with starter automations.
72. Add workflow template editor with validation and preview.
73. Add workflow dry-run simulator with mocked side effects.
74. Add workflow step debugger with variable inspection.
75. Add workflow version history and compare view.
76. Add workflow rollback to prior known-good revisions.
77. Add workflow import/export packs.
78. Add task dependency graph and critical-path visualization.
79. Add natural-language recurring schedule editor.
80. Add schedule conflict detector with auto-suggestion fixes.
81. Add overdue-task SLA reminders with escalation options.
82. Add bulk approve/reject actions in approval queue.
83. Add background job retries with backoff and failure classification.
84. Add cancellation with cleanup hooks for running jobs.
85. Add per-workspace job quotas and budget limits.
86. Add routine success/failure analytics dashboard.
87. Add routine recommendation engine from usage patterns.
88. Add workflow-triggered continuity snapshot generation.
89. Add workflow-triggered browser task execution.
90. Add webhook-triggered workflow entrypoint with signature validation.
91. Add tool-policy presets (strict, balanced, lab) for quick switching.
92. Add per-tool cooldown windows.
93. Add per-tool request rate limits.
94. Add two-step confirmation for destructive tool actions.
95. Add policy explanation panel for denied/blocked tool actions.
96. Add browser step-by-step preview before execution.
97. Add browser action replay from audit log entries.
98. Add screenshot/video artifact viewer for browser jobs.
99. Add anti-stuck browser recovery loops with safe abort paths.
100. Add clipboard/file boundary prompts for computer-use actions.
101. Add domain allowlist learning mode with explicit approvals.
102. Add high-risk action simulation mode (no-op execution path).
103. Add script upload safety scan before execution.
104. Add prompt-injection detection on tool call plans.
105. Add secret redaction layer before tool dispatch and logging.
106. Add room/zone scene control for smart-home integrations.
107. Add safe automation windows (quiet hours and lockout intervals).
108. Add occupancy-aware routine decisions.
109. Add device capability discovery UI.
110. Add device state drift reconciliation and auto-retry logic.
111. Add integration health dashboard for all external systems.
112. Add integration credential vault UI with rotation reminders.
113. Add calendar integration for events and reminders.
114. Add email integration for summaries and action extraction.
115. Add notes integration for external knowledge capture.
116. Add messaging integration (opt-in channels) for alerts and reminders.
117. Add provider contract canary background service.
118. Add key pool health analytics and proactive rotation alerts.
119. Add latency/cost budget policy enforcement.
120. Add sustained and burst throughput benchmark suites.
121. Add queue pressure alerts with threshold-based severity.
122. Add dead-letter queue viewer and selective replay controls.
123. Add trace explorer UI for request-level diagnostics.
124. Add one-click diagnostics bundle export for support/debugging.
125. Add release checklist automation with pass/fail gating.
126. Add environment doctor command for dependency/runtime checks.
127. Add backup/restore snapshots for memory and workflow state.
128. Add migration readiness advisor with actionable recommendations.
129. Add role-based access control (admin, operator, viewer).
130. Add optional SSO/OAuth auth mode.
131. Add scoped API tokens per workspace and capability.
132. Add compliance audit export (JSON/CSV) for governance review.
133. Add data retention and deletion center for user-controlled lifecycle.
134. Add optional encryption-at-rest for memory databases and artifacts.
135. Add CI performance regression gate tied to baseline artifacts.
136. Add nightly end-to-end reliability suite.
137. Add chaos test suite for provider, memory, and network failures.
138. Add flaky-test quarantine automation and reporting.
139. Add in-app changelog feed linked to shipped features.
140. Add user feedback ingestion and triage pipeline mapped to roadmap items.
