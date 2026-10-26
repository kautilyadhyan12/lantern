# PROOF M0
Commit: 19b483a6a6d2474cce8f510669336ff8cfd11906
Code tree: 155db6d4093bb4b23420a21a2c487eb949a043fd96b024178b987df8defbd704
UTC: 2026-10-26T09:06:45.941163+00:00
Platform: Linux-6.8.0-1064-azure-x86_64-with-glibc2.31

## Check 1
Exit: 0; duration: 0.033 seconds
```text
uv run ruff check .
All checks passed!
```

## Check 2
Exit: 0; duration: 0.032 seconds
```text
uv run ruff format --check src scripts tests
35 files already formatted
```

## Check 3
Exit: 0; duration: 0.672 seconds
```text
uv run python scripts/lint_custom.py

```

## Check 4
Exit: 0; duration: 0.189 seconds
```text
uv run lint-imports

╔══╗─────────▶╔╗ ╔╗      ╔╗◀───┐
╚╣╠╝◀─────┐  ╔╝╚╗║║────▶╔╝╚╗   │
 ║║   ╔══╦══╦╩╗╔╝║║  ╔╦═╩╗╔╝╔═╦══╗
 ║║╔══╣╔╗║╔╗║╔╣║ ║║ ╔╬╣╔╗║║ ║│║╔═╝
╔╣╠╣║║║╚╝║╚╝║║║╚╗║╚═╝║║║║║╚╗║═╣║
╚══╩╩╩╣╔═╩══╩╝╚═╝╚═══╩╩╝╚╩═╩╩═╩╝
  └──▶║║                    ▲ 
      ╚╝────────────────────┘


---------
Contracts
---------

Analyzed 5 files, 3 dependencies.
---------------------------------

CLI depends on database, never the reverse KEPT

Contracts: 1 kept, 0 broken.
```

## Check 5
Exit: 0; duration: 0.344 seconds
```text
uv run mypy --strict
Success: no issues found in 16 source files
```

## Check 6
Exit: 0; duration: 62.460 seconds
```text
uv run --offline pytest --cov --cov-report=term-missing --cov-report=json:coverage.json
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 85%]
..................................................                       [100%]
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.12.1-final-0 ________________

Name                                                  Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------------------
scripts/__init__.py                                       0      0      0      0   100%
scripts/audit_dependencies.py                            54      1     14      0    99%   88
scripts/check_acceptance_ids.py                          65      0     32      1    99%   38->35
scripts/check_dependencies.py                            26      0      2      0   100%
scripts/checks.py                                        58      0     12      0   100%
scripts/code_tree.py                                     34      4      4      1    87%   15, 55-57
scripts/coverage_gate.py                                 72      3     22      1    94%   82-84
scripts/lint_custom.py                                  117      5     60      1    97%   47, 151-154
scripts/prove.py                                         92      7     28      2    92%   112-113, 127-128, 137->139, 140-144
src/lantern/__init__.py                                   0      0      0      0   100%
src/lantern/cli.py                                       22      2      0      0    91%   27-28
src/lantern/config.py                                    17      0      2      0   100%
src/lantern/db/__init__.py                                0      0      0      0   100%
src/lantern/db/migrate.py                                15      0      0      0   100%
src/lantern/db/migrations/env.py                         18      0      0      0   100%
src/lantern/db/migrations/versions/0001_baseline.py       6      2      0      0    67%   8, 12
-------------------------------------------------------------------------------------------------
TOTAL                                                   596     24    176      6    96%
Coverage JSON written to file coverage.json
338 passed in 61.76s (0:01:01)
```

## Check 7
Exit: 0; duration: 0.207 seconds
```text
uv run python scripts/coverage_gate.py
src/lantern/core: not present
src/lantern/policy: not present
src/lantern/egress: not present
src/lantern/db/events.py: not present
src/lantern/tools/gateway.py: not present
src/lantern/llm/gateway.py: not present
src/lantern/report/render_html.py: not present
scripts/hooks: not present
Total coverage: 95.85492227979275%
```

## Check 8
Exit: 0; duration: 0.310 seconds
```text
uv run python scripts/check_dependencies.py
Prohibited dependencies: none
```

## Check 9
Exit: 0; duration: 0.688 seconds
```text
uv run bandit -r src/lantern scripts
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: None
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	running on Python 3.12.1
Run started:2026-10-26 09:07:50.726653+00:00

Test results:
	No issues identified.

Code scanned:
	Total lines of code: 799
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 5

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 0
Files skipped (0):
```

## Check 10
Exit: 0; duration: 3.808 seconds
```text
uv run python scripts/audit_dependencies.py
WARNING:pip_audit._cli:--no-deps is supported, but users are encouraged to fully hash their pinned dependencies
WARNING:pip_audit._cli:Consider using a tool like `pip-compile`: https://pip-tools.readthedocs.io/en/latest/#using-hashes
WARNING:pip_audit._cache:Failed to write to cache directory, performance may be degraded: [Errno 30] Read-only file system: '/home/codespace/.cache/pip-audit/d/b/8/f/2/tmpaupj9h1n'
No known vulnerabilities found
```

## Check 11
Exit: 0; duration: 0.098 seconds
```text
uv run python scripts/check_acceptance_ids.py S0.1 S0.2 --backlog docs/06_ROADMAP_BACKLOG.md
S0.1-AC1 -> tests/test_skeleton.py::test_placeholder, tests/test_skeleton.py::test_console_help, tests/test_skeleton.py::test_python_pin_and_lockfile, tests/test_skeleton.py::test_make_check_commands_and_failure_propagation, tests/test_skeleton.py::test_db_targets
S0.1-AC2 -> tests/test_tooling.py::test_required_tooling_keys, tests/test_tooling.py::test_per_file_lint_ignores, tests/test_tooling.py::test_src_package_and_console_entry, tests/test_tooling.py::test_dependency_security_policy
S0.1-AC3 -> tests/e2e/test_database.py::test_compose_loopback_healthcheck, tests/e2e/test_database.py::test_upgrade_records_baseline, tests/e2e/test_database.py::test_upgrade_is_idempotent, tests/e2e/test_database.py::test_missing_database_guidance, tests/e2e/test_database.py::test_cli_never_echoes_credentials, tests/test_config.py::test_database_url_valid_driver, tests/test_config.py::test_reject_other_drivers, tests/test_config.py::test_missing_or_malformed_url, tests/test_config.py::test_secrets_hidden_in_errors_and_repr, tests/test_config.py::test_valid_url_property, tests/test_config.py::test_invalid_driver_property
S0.1-AC4 -> tests/test_hooks.py::test_all_hooks_are_local_uv_commands, tests/test_hooks.py::test_expected_hooks_present, tests/test_hooks.py::test_make_hooks_installs, tests/test_hooks.py::test_whitespace_fixers_change_temp_file, tests/test_hooks.py::test_secret_scanner_detects_synthetic_token, tests/test_hooks.py::test_secret_scanner_allows_review_fingerprints_but_checks_notes
S0.1-AC5 -> tests/review/test_m0_r1_adversarial.py::test_reference_lint_rule_table, tests/review/test_m0_r1_adversarial.py::test_bare_skip_decorators_require_issue, tests/review/test_m0_r1_adversarial.py::test_unrelated_local_import_does_not_hide_forbidden_sleep, tests/test_lint_custom.py::test_broad_handler_rules, tests/test_lint_custom.py::test_broad_handlers_allow_reraise_and_exception_logging, tests/test_lint_custom.py::test_nested_function_does_not_rescue_broad_handler, tests/test_lint_custom.py::test_suppression_requires_reason, tests/test_lint_custom.py::test_suppression_with_reason_allowed, tests/test_lint_custom.py::test_skip_requires_issue_url, tests/test_lint_custom.py::test_skip_with_issue_url_allowed, tests/test_lint_custom.py::test_skip_decorator_with_issue_url_allowed, tests/test_lint_custom.py::test_bare_decorator_with_issue_comment_allowed, tests/test_lint_custom.py::test_unrelated_imports_preserve_alias_rule_results, tests/test_lint_custom.py::test_scope_rules_for_methods_and_decorators, tests/test_lint_custom.py::test_class_imports_do_not_leak_into_expression_scopes, tests/test_lint_custom.py::test_first_comprehension_iterable_uses_enclosing_class_scope, tests/test_lint_custom.py::test_sleep_only_forbidden_in_src, tests/test_lint_custom.py::test_shell_requires_literal_false, tests/test_lint_custom.py::test_subprocess_without_shell_or_literal_false_allowed, tests/test_lint_custom.py::test_print_only_forbidden_in_src, tests/test_lint_custom.py::test_clean_code, tests/test_lint_custom.py::test_valid_python_never_raises, tests/test_lint_custom.py::test_line_positions_and_determinism, tests/test_lint_custom.py::test_rules_have_stable_distinct_ids, tests/test_lint_custom.py::test_cli_exit_and_diagnostics, tests/test_lint_custom.py::test_script_exit_and_diagnostics
S0.1-AC6 -> tests/test_devcontainer_setup.py::test_image_is_maintained_and_digest_pinned, tests/test_devcontainer_setup.py::test_setup_registered_and_tools_selected_first, tests/test_devcontainer_setup.py::test_verified_archives_produce_working_tools, tests/test_devcontainer_setup.py::test_bad_digest_never_extracts_or_installs, tests/test_devcontainer_setup.py::test_last_download_failure_keeps_previous_installation, tests/test_devcontainer_setup.py::test_unsupported_architecture_rejected_before_download, tests/test_devcontainer_setup.py::test_default_setup_selects_node_after_shell_initialization, tests/test_workspace.py::test_pack_files_unchanged, tests/test_workspace.py::test_gitignore_protects_local_material, tests/test_workspace.py::test_no_tracked_env, tests/test_workspace.py::test_example_settings_complete, tests/test_workspace.py::test_development_commands_available
S0.1-AC7 -> tests/test_readme.py::test_readme_explains_product_and_codespaces, tests/test_readme.py::test_readme_has_setup_commands, tests/test_readme.py::test_readme_has_only_placeholder_credentials
S0.2-AC1 -> tests/test_audit_dependencies.py::test_complete_inventory_and_single_local_exception, tests/test_audit_dependencies.py::test_invalid_inventory_fails_before_audit, tests/test_audit_dependencies.py::test_strict_arguments_status_and_manifest_cleanup, tests/test_audit_dependencies.py::test_real_process_boundary_and_error_output, tests/test_audit_dependencies.py::test_inventory_pins_are_sorted_and_order_independent, tests/test_check_pipeline.py::test_required_order, tests/test_check_pipeline.py::test_stops_at_each_failure, tests/test_check_pipeline.py::test_run_step_captures_exit_duration_and_last_30_lines, tests/test_check_pipeline.py::test_spawn_and_timeout_fail, tests/test_check_pipeline.py::test_invalid_step_result_rejected, tests/test_check_pipeline.py::test_make_uses_shared_runner, tests/test_check_pipeline.py::test_import_contract_blocks_reverse_dependency, tests/test_check_pipeline.py::test_standalone_scripts_have_working_cli, tests/test_proof_boundaries.py::test_runner_boundary_failure_is_recorded_and_later_steps_run, tests/test_skeleton.py::test_make_check_commands_and_failure_propagation
S0.2-AC2 -> tests/review/test_m0_r1_adversarial.py::test_reference_coverage_threshold, tests/review/test_m0_r1_adversarial.py::test_coverage_rejects_nonfinite_and_missing_counts, tests/test_coverage_gate.py::test_total_boundary, tests/test_coverage_gate.py::test_critical_boundary, tests/test_coverage_gate.py::test_weighted_directory_coverage, tests/test_coverage_gate.py::test_missing_path_is_reported, tests/test_coverage_gate.py::test_existing_unmeasured_path_fails, tests/test_coverage_gate.py::test_no_prefix_collision, tests/test_coverage_gate.py::test_summary_validation, tests/test_coverage_gate.py::test_threshold_validation, tests/test_coverage_gate.py::test_rounded_percentage_cannot_hide_failure, tests/test_coverage_gate.py::test_existing_file_missing_from_measured_directory_fails, tests/test_coverage_gate.py::test_malformed_or_nonfinite_report_fails, tests/test_coverage_gate.py::test_cli_status, tests/test_coverage_gate.py::test_increasing_counts_cannot_break_pass, tests/test_coverage_gate.py::test_aggregation_bounds_and_order
S0.2-AC3 -> tests/review/test_m0_r1_adversarial.py::test_reference_backlog_order, tests/review/test_m0_r1_adversarial.py::test_reference_literal_markers, tests/test_acceptance_ids.py::test_selected_story_ids, tests/test_acceptance_ids.py::test_class_test_names, tests/test_acceptance_ids.py::test_literal_marker_required, tests/test_acceptance_ids.py::test_unknown_marker_anywhere_fails, tests/test_acceptance_ids.py::test_missing_ac_fails, tests/test_acceptance_ids.py::test_unknown_story_fails, tests/test_acceptance_ids.py::test_never_imports_test_modules, tests/test_acceptance_ids.py::test_invalid_source_fails_cleanly, tests/test_acceptance_ids.py::test_unrelated_stories_and_duplicates_do_not_change_selection, tests/test_acceptance_ids.py::test_strings_are_data_and_file_order_does_not_change_mappings, tests/test_proof_boundaries.py::test_nested_function_is_not_a_collected_test, tests/test_proof_boundaries.py::test_malformed_or_uncollected_marker_cannot_satisfy_requirement
S0.2-AC4 -> tests/review/test_m0_r1_adversarial.py::test_reference_hash_with_unicode_and_prefix_collisions, tests/review/test_m0_r1_adversarial.py::test_reference_proof_result_and_timezone, tests/review/test_m0_r1_adversarial.py::test_proof_rejects_naive_and_oversized_story, tests/test_code_tree.py::test_git_entries_match_digest, tests/test_code_tree.py::test_docs_changes_do_not_change_hash, tests/test_code_tree.py::test_code_changes_change_hash, tests/test_code_tree.py::test_extra_exclusions_and_prefix_boundaries, tests/test_code_tree.py::test_unusual_paths, tests/test_code_tree.py::test_hash_exclusions_preserve_exact_entry_bytes, tests/test_code_tree.py::test_hash_order_is_significant, tests/test_code_tree.py::test_code_tree_cli, tests/test_prove.py::test_dirty_code_refused, tests/test_prove.py::test_docs_only_changes_allowed, tests/test_prove.py::test_renamed_or_untracked_code_refused, tests/test_prove.py::test_all_steps_run_after_failure, tests/test_prove.py::test_defaults_and_combined_ac_stories, tests/test_prove.py::test_report_metadata_and_last_30_lines, tests/test_prove.py::test_head_or_code_change_fails, tests/test_prove.py::test_no_stale_coverage_pass, tests/test_prove.py::test_coverage_cleanup_does_not_delete_symlink_target, tests/test_prove.py::test_sensitive_values_redacted, tests/test_prove.py::test_runner_redacts_sensitive_environment, tests/test_prove.py::test_story_path_traversal_rejected, tests/test_prove.py::test_make_variables_are_data, tests/test_prove.py::test_cli_positional_and_environment_ids, tests/test_prove.py::test_render_preserves_key_numbers, tests/test_prove.py::test_render_arbitrary_backticks_and_failure, tests/test_prove.py::test_proof_context_requires_timezone
S0.2-AC5 -> tests/test_check_pipeline.py::test_quality_configuration_and_sources, tests/test_check_pipeline.py::test_critical_paths_exact
S0.2-AC6 -> tests/review/test_m0_r1_adversarial.py::test_reference_dependency_names, tests/test_dependencies.py::test_each_denied_name_fails, tests/test_dependencies.py::test_normalized_names, tests/test_dependencies.py::test_allowed_image_packages, tests/test_dependencies.py::test_transitive_package_is_checked, tests/test_dependencies.py::test_invalid_lock_fails, tests/test_dependencies.py::test_cli_status, tests/test_dependencies.py::test_normalization_is_idempotent_and_case_equivalent
```

RESULT: PASS
