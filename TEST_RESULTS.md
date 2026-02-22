time="2026-02-22T18:31:37Z" level=warning msg="/home/gabriel/mikes-bs/docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-8.4.2, pluggy-1.6.0 -- /usr/local/bin/python
cachedir: .pytest_cache
rootdir: /app
plugins: anyio-4.12.1, asyncio-0.26.0
asyncio: mode=Mode.STRICT, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 159 items

tests/test_block_c_filters_and_votes.py::test_parse_candidate_filters_legacy_backcompat_mapping PASSED [  0%]
tests/test_block_c_filters_and_votes.py::test_parse_candidate_filters_unified_lists PASSED [  1%]
tests/test_block_c_filters_and_votes.py::test_vote_note_round_trip_extracts_actor PASSED [  1%]
tests/test_block_c_filters_and_votes.py::test_vote_note_extract_ignores_non_vote_notes PASSED [  2%]
tests/test_bundle_detection.py::test_canonical_owner_fallback_chain PASSED [  3%]
tests/test_bundle_detection.py::test_extract_zip PASSED                  [  3%]
tests/test_bundle_detection.py::test_fuzzy_match_min_length_gate PASSED  [  4%]
tests/test_bundle_detection.py::test_fuzzy_match_zip_gate PASSED         [  5%]
tests/test_bundle_detection.py::test_fuzzy_match_positive PASSED         [  5%]
tests/test_bundle_detection.py::test_bundle_ttl_staleness PASSED         [  6%]
tests/test_bundle_detection.py::test_bundle_invalidation_on_owner_or_geometry_change PASSED [  6%]
tests/test_dif.py::TestYMS::test_yms_splits_computed_correctly PASSED    [  7%]
tests/test_dif.py::TestYMS::test_yms_critical_area_deduction PASSED      [  8%]
tests/test_dif.py::TestYMS::test_yms_cap_at_20 PASSED                    [  8%]
tests/test_dif.py::TestYMS::test_yms_heuristic_always_present PASSED     [  9%]
tests/test_dif.py::TestYMS::test_yms_zero_splits_scores_zero PASSED      [ 10%]
tests/test_dif.py::TestYMS::test_yms_deduction_cannot_go_below_zero PASSED [ 10%]
tests/test_dif.py::TestYMS::test_yms_data_quality_full_with_zone PASSED  [ 11%]
tests/test_dif.py::TestYMS::test_yms_data_quality_partial_without_zone PASSED [ 11%]
tests/test_dif.py::TestEFI::test_efi_zero_friction_scores_high PASSED    [ 12%]
tests/test_dif.py::TestEFI::test_efi_mild_friction_scores_high PASSED    [ 13%]
tests/test_dif.py::TestEFI::test_efi_critical_area_only_friction PASSED  [ 13%]
tests/test_dif.py::TestEFI::test_efi_high_friction_scores_near_zero PASSED [ 14%]
tests/test_dif.py::TestEFI::test_efi_asymmetric_friction5_much_lower_than_friction3 PASSED [ 15%]
tests/test_dif.py::TestEFI::test_efi_slope_and_sewer_stubs_in_reasons PASSED [ 15%]
tests/test_dif.py::TestEFI::test_efi_data_quality_always_partial PASSED  [ 16%]
tests/test_dif.py::TestALS::test_als_session_none_returns_unavailable PASSED [ 16%]
tests/test_dif.py::TestALS::test_als_session_none_reason_codes PASSED    [ 17%]
tests/test_dif.py::TestALS::test_als_no_dom_always_present_with_session PASSED [ 18%]
tests/test_dif.py::TestCMS::test_cms_high_margin_scores_10 PASSED        [ 18%]
tests/test_dif.py::TestCMS::test_cms_30pct_margin_scores_10 PASSED       [ 19%]
tests/test_dif.py::TestCMS::test_cms_negative_margin_scores_zero PASSED  [ 20%]
tests/test_dif.py::TestCMS::test_cms_return_proxy_not_irr_always_present PASSED [ 20%]
tests/test_dif.py::TestCMS::test_cms_land_cost_source_reason_present PASSED [ 21%]
tests/test_dif.py::TestCMS::test_cms_last_sale_price_preferred_over_assessed PASSED [ 22%]
tests/test_dif.py::TestCMS::test_cms_data_quality_partial_without_session PASSED [ 22%]
tests/test_dif.py::TestCMS::test_cms_county_multiplier_applied PASSED    [ 23%]
tests/test_dif.py::TestSFI::test_sfi_long_ownership_trust_scores_high PASSED [ 23%]
tests/test_dif.py::TestSFI::test_sfi_trust_bonus_fires PASSED            [ 24%]
tests/test_dif.py::TestSFI::test_sfi_no_sale_date_partial_quality PASSED [ 25%]
tests/test_dif.py::TestSFI::test_sfi_no_sale_date_score_nonzero_with_low_imp PASSED [ 25%]
tests/test_dif.py::TestSFI::test_sfi_full_quality_with_sale_date PASSED  [ 26%]
tests/test_dif.py::TestSFI::test_sfi_short_ownership_no_bonus PASSED     [ 27%]
tests/test_dif.py::TestSFI::test_sfi_tax_delinquency_stubbed_always PASSED [ 27%]
tests/test_dif.py::TestSFI::test_sfi_score_capped_at_10 PASSED           [ 28%]
tests/test_dif.py::TestSFI::test_sfi_estate_pattern_triggers_trust_bonus PASSED [ 28%]
tests/test_dif.py::TestIntegration::test_composite_r5_beats_commercial PASSED [ 29%]
tests/test_dif.py::TestIntegration::test_dif_result_namedtuple_fields PASSED [ 30%]
tests/test_dif.py::TestIntegration::test_dif_components_dict_keys PASSED [ 30%]
tests/test_dif.py::TestIntegration::test_dif_data_confidence_range PASSED [ 31%]
tests/test_dif.py::TestIntegration::test_dif_delta_applied_reason_present PASSED [ 32%]
tests/test_dif_integration.py::TestHighFriction::test_high_friction_critical_area_efi_below_3 PASSED [ 32%]
tests/test_dif_integration.py::TestHighFriction::test_critical_area_only_efi_score PASSED [ 33%]
tests/test_dif_integration.py::TestHighFriction::test_max_friction_efi_score_near_zero PASSED [ 33%]
tests/test_dif_integration.py::TestYMSDataQuality::test_missing_zone_code_yields_partial_quality PASSED [ 34%]
tests/test_dif_integration.py::TestYMSDataQuality::test_zone_code_present_yields_full_quality PASSED [ 35%]
tests/test_dif_integration.py::TestYMSDataQuality::test_empty_zone_code_yields_partial PASSED [ 35%]
tests/test_dif_integration.py::TestDIFDeltaClamp::test_dif_delta_clamp_high PASSED [ 36%]
tests/test_dif_integration.py::TestDIFDeltaClamp::test_dif_delta_clamp_high_explicit PASSED [ 37%]
tests/test_dif_integration.py::TestDIFDeltaClamp::test_dif_delta_clamp_low_explicit PASSED [ 37%]
tests/test_dif_integration.py::TestDIFDeltaClamp::test_unclamped_delta_no_clamp_reason PASSED [ 38%]
tests/test_dif_integration.py::TestStubReasonCodes::test_slope_stubbed_in_efi_reasons PASSED [ 38%]
tests/test_dif_integration.py::TestStubReasonCodes::test_sewer_stubbed_in_efi_reasons PASSED [ 39%]
tests/test_dif_integration.py::TestStubReasonCodes::test_als_no_dom_in_als_reasons_no_session PASSED [ 40%]
tests/test_dif_integration.py::TestStubReasonCodes::test_als_no_session_in_als_reasons_no_session PASSED [ 40%]
tests/test_dif_integration.py::TestStubReasonCodes::test_tax_delinquency_stubbed_in_sfi_reasons PASSED [ 41%]
tests/test_dif_integration.py::TestStubReasonCodes::test_all_stub_codes_present_in_full_dif_result PASSED [ 42%]
tests/test_dif_integration.py::TestDataConfidence::test_data_confidence_partial_when_no_session PASSED [ 42%]
tests/test_dif_integration.py::TestDataConfidence::test_data_confidence_is_float PASSED [ 43%]
tests/test_discovery.py::TestDiscoveryOutputKeys::test_discovery_output_has_required_keys PASSED [ 44%]
tests/test_discovery.py::TestDiscoveryOutputKeys::test_discovery_total_analyzed_zero_for_empty_db PASSED [ 44%]
tests/test_discovery.py::TestDiscoveryTopN::test_discovery_top_n_a_respected PASSED [ 45%]
tests/test_discovery.py::TestDiscoveryTopN::test_discovery_top_n_b_respected PASSED [ 45%]
tests/test_discovery.py::TestDiscoverySorting::test_discovery_tier_a_sorted_descending PASSED [ 46%]
tests/test_discovery.py::TestDiscoverySorting::test_discovery_tier_b_sorted_descending PASSED [ 47%]
tests/test_discovery.py::TestDiscoveryRunId::test_discovery_run_id_is_valid_uuid PASSED [ 47%]
tests/test_discovery.py::TestDiscoveryRunId::test_discovery_run_id_unique_per_run PASSED [ 48%]
tests/test_discovery.py::TestDiscoveryJsonArtifact::test_discovery_json_artifact_written PASSED [ 49%]
tests/test_discovery.py::TestDiscoveryJsonArtifact::test_discovery_json_artifact_fixed_path PASSED [ 49%]
tests/test_discovery.py::TestDiscoveryCountyFilter::test_discovery_county_in_output PASSED [ 50%]
tests/test_discovery.py::TestDiscoveryCountyFilter::test_discovery_no_county_is_none PASSED [ 50%]
tests/test_discovery.py::TestDiscoveryAssumptionsVersion::test_discovery_assumptions_version_in_output PASSED [ 51%]
tests/test_discovery.py::TestDiscoveryCandidateShape::test_tier_a_candidate_has_required_keys PASSED [ 52%]
tests/test_discovery.py::TestDiscoveryCandidateShape::test_tier_b_candidate_has_required_keys PASSED [ 52%]
tests/test_feasibility.py::test_offline_parcel_load ERROR                [ 53%]
tests/test_feasibility.py::test_offline_buildable_area ERROR             [ 54%]
tests/test_feasibility.py::test_offline_layouts_generated ERROR          [ 54%]
tests/test_feasibility.py::test_offline_tags_present ERROR               [ 55%]
tests/test_feasibility.py::test_offline_export_paths ERROR               [ 55%]
tests/test_feasibility.py::test_feasibility_pipeline[0] SKIPPED (Par...) [ 56%]
tests/test_feasibility.py::test_feasibility_pipeline[1] SKIPPED (Par...) [ 57%]
tests/test_feasibility.py::test_feasibility_pipeline[2] SKIPPED (Par...) [ 57%]
tests/test_feasibility.py::test_feasibility_pipeline[3] SKIPPED (Par...) [ 58%]
tests/test_feasibility.py::test_feasibility_pipeline[4] SKIPPED (Par...) [ 59%]
tests/test_ingest.py::test_normalize_returns_geodataframe PASSED         [ 59%]
tests/test_ingest.py::test_normalize_field_mapping PASSED                [ 60%]
tests/test_ingest.py::test_normalize_handles_null_geometry PASSED        [ 61%]
tests/test_ingest.py::test_normalize_empty_features PASSED               [ 61%]
tests/test_ingest.py::test_normalize_valid_geometry PASSED               [ 62%]
tests/test_osint_bridge.py::test_is_entity_detection PASSED              [ 62%]
tests/test_osint_bridge.py::test_build_summary_variants PASSED           [ 63%]
tests/test_osint_bridge.py::test_owner_dedup_reuses_investigation_id PASSED [ 64%]
tests/test_osint_bridge.py::test_timeout_returns_failed_status PASSED    [ 64%]
tests/test_osint_bridge.py::test_batch_skips_when_health_down PASSED     [ 65%]
tests/test_profit.py::test_profit_calculation PASSED                     [ 66%]
tests/test_profit.py::test_profit_positive_case PASSED                   [ 66%]
tests/test_profit.py::test_no_comps_fallback PASSED                      [ 67%]
tests/test_scorer.py::test_score_to_tier_a PASSED                        [ 67%]
tests/test_scorer.py::test_score_to_tier_b FAILED                        [ 68%]
tests/test_scorer.py::test_score_to_tier_c FAILED                        [ 69%]
tests/test_scorer.py::test_score_to_tier_d FAILED                        [ 69%]
tests/test_scorer.py::test_score_to_tier_e FAILED                        [ 70%]
tests/test_scorer.py::test_score_to_tier_f FAILED                        [ 71%]
tests/test_scorer.py::test_tier_boundary_exact PASSED                    [ 71%]
tests/test_scorer.py::test_tier_just_below_a FAILED                      [ 72%]
tests/test_scorer.py::test_tier_just_below_b FAILED                      [ 72%]
tests/test_scorer.py::test_base_score_high_splits PASSED                 [ 73%]
tests/test_scorer.py::test_base_score_low_splits PASSED                  [ 74%]
tests/test_scorer.py::test_base_score_trust_owner PASSED                 [ 74%]
tests/test_scorer.py::test_base_score_capped_at_80 PASSED                [ 75%]
tests/test_scorer.py::test_base_score_zero_splits PASSED                 [ 76%]
tests/test_scoring_determinism.py::test_score_candidate_is_deterministic_for_identical_inputs PASSED [ 76%]
tests/test_scoring_determinism.py::test_learned_rule_adjustment_is_bounded_to_max_delta PASSED [ 77%]
tests/test_scoring_determinism.py::test_learned_rule_weight_decays_with_age PASSED [ 77%]
tests/test_subdivision.py::test_uldr_071ac_frontage_75_is_constrained_and_uncertain PASSED [ 78%]
tests/test_subdivision.py::test_null_frontage_is_fail_closed_low_confidence_with_reason PASSED [ 79%]
tests/test_subdivision.py::test_rural_r5_5ac_has_high_confidence_and_strong_splits PASSED [ 79%]
tests/test_subdivision.py::test_economic_gate_emits_loss_and_thin_margin_tags PASSED [ 80%]
tests/test_subdivision.py::test_arbitrage_depth_rural_outside_uga_with_ruta_is_high PASSED [ 81%]
tests/test_tagger.py::TestLSATag::test_r5_12_acres_gets_lsa_tag PASSED   [ 81%]
tests/test_tagger.py::TestLSATag::test_r5_12_acres_gets_rural_cluster_tag PASSED [ 82%]
tests/test_tagger.py::TestLSATag::test_r5_12_acres_uga_unknown PASSED    [ 83%]
tests/test_tagger.py::TestLotTooSmall::test_r5_3_acres_no_lsa_tag PASSED [ 83%]
tests/test_tagger.py::TestLotTooSmall::test_r5_3_acres_no_rural_cluster_tag PASSED [ 84%]
tests/test_tagger.py::TestHB1110::test_urban_zone_hb1110_not_configured_emits_risk PASSED [ 84%]
tests/test_tagger.py::TestHB1110::test_urban_zone_hb1110_configured_emits_edge PASSED [ 85%]
tests/test_tagger.py::TestCriticalAreas::test_critical_area_adds_risk_not_suppress_edge PASSED [ 86%]
tests/test_tagger.py::TestSepticWater::test_no_improvement_value_emits_septic_water_unknown PASSED [ 86%]
tests/test_tagger.py::TestRUTA::test_ruta_not_confirmed_emits_risk PASSED [ 87%]
tests/test_tagger.py::TestRUTA::test_ruta_confirmed_emits_edge PASSED    [ 88%]
tests/test_tagger.py::TestScoreBoost::test_edge_lsa_boosts_score PASSED  [ 88%]
tests/test_tagger.py::TestUserVoteTag::test_vote_net_threshold_applies_upvote_tag PASSED [ 89%]
tests/test_tagger.py::TestUserVoteTag::test_zero_vote_net_does_not_apply_upvote_tag PASSED [ 89%]
tests/test_uga_integration.py::test_uga_outside_emits_lsa_without_unknown PASSED [ 90%]
tests/test_uga_integration.py::test_uga_inside_suppresses_lsa PASSED     [ 91%]
tests/test_uga_integration.py::test_uga_none_emits_unknown PASSED        [ 91%]
tests/test_underwriting.py::test_base_proforma_has_all_required_fields PASSED [ 92%]
tests/test_underwriting.py::test_sensitivity_produces_8_scenarios PASSED [ 93%]
tests/test_underwriting.py::test_hard_cost_10pct_reduces_margin PASSED   [ 93%]
tests/test_underwriting.py::test_hard_cost_20pct_worse_than_10pct PASSED [ 94%]
tests/test_underwriting.py::test_price_down_5pct_reduces_margin PASSED   [ 94%]
tests/test_underwriting.py::test_delay_3mo_increases_total_cost PASSED   [ 95%]
tests/test_underwriting.py::test_rate_up_200bps_increases_financing PASSED [ 96%]
tests/test_underwriting.py::test_risk_class_a_at_25pct_margin PASSED     [ 96%]
tests/test_underwriting.py::test_risk_class_d_at_low_margin PASSED       [ 97%]
tests/test_underwriting.py::test_annualized_return_estimate_field_exists PASSED [ 98%]
tests/test_underwriting.py::test_no_irr_field_exists PASSED              [ 98%]
tests/test_underwriting.py::test_return_proxy_reason_in_reasons PASSED   [ 99%]
tests/test_underwriting.py::test_assumptions_version_recorded PASSED     [100%]

==================================== ERRORS ====================================
__________________ ERROR at setup of test_offline_parcel_load __________________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_offline_parcel_load0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad735846c10>

    @pytest.fixture()
    def offline_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SNOCO_OFFLINE", "true")
        out_dir = tmp_path / "offline" / OFFLINE_PARCEL_ID
    
        if _is_geo_mocked():
            def _phase2(ctx: AnalysisContext, _client: FeasibilityAPIClient) -> AnalysisContext:
                ctx.parcel_geom = _LenOne()
                ctx.parcel_attrs = {"GIS_SQ_FT": 153331}
                return ctx
    
            def _buildable(ctx: AnalysisContext) -> AnalysisContext:
                ctx.buildable_geom = _FakeBuildableGeom(area_sf=120000.0)
                return ctx
    
            def _layouts(ctx: AnalysisContext) -> AnalysisContext:
                ctx.layouts = [{"id": "layout_1"}, {"id": "layout_2"}]
                return ctx
    
            def _tags(ctx: AnalysisContext) -> AnalysisContext:
                ctx.add_tag("INFO_OFFLINE_FIXTURE")
                return ctx
    
            def _export(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
                export_dir = output_dir or (tmp_path / "offline_exports")
                export_dir.mkdir(parents=True, exist_ok=True)
                png = export_dir / "feasibility_map.png"
                gpkg = export_dir / "feasibility_layers.gpkg"
                png.write_bytes(b"offline")
                gpkg.write_bytes(b"offline")
                ctx.export_paths = {"output_dir": str(export_dir), "png": str(png), "gpkg": str(gpkg)}
                return ctx
    
            monkeypatch.setattr(orch, "phase2", _phase2)
            monkeypatch.setattr(orch, "PHASES", [(_buildable, False), (_layouts, False), (_tags, False)])
            monkeypatch.setattr(orch, "phase7", _export)
    
>       return run_feasibility(OFFLINE_PARCEL_ID, output_dir=out_dir)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_feasibility.py:76: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
openclaw/analysis/feasibility/orchestrator.py:78: in run_feasibility
    ctx = phase7(ctx, output_dir=output_dir)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
openclaw/analysis/feasibility/phase7_export.py:23: in run
    _write_geojson(ctx.parcel_geom, out_dir / "parcel.geojson")
openclaw/analysis/feasibility/phase7_export.py:15: in _write_geojson
    gdf.to_file(path, driver="GeoJSON")
/usr/local/lib/python3.11/site-packages/geopandas/geodataframe.py:1249: in to_file
    _to_file(self, filename, driver, schema, index, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:610: in _to_file
    _to_file_fiona(df, filename, driver, schema, crs, mode, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:619: in _to_file_fiona
    schema = infer_schema(df)
             ^^^^^^^^^^^^^^^^
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:692: in infer_schema
    [
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:693: in <listcomp>
    (col, convert_type(col, _type))
          ^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

column = 'Parcel_ID', in_type = <StringDtype(storage='python', na_value=nan)>

    def convert_type(column, in_type):
        if in_type == object:
            return "str"
        if in_type.name.startswith("datetime64"):
            # numpy datetime type regardless of frequency
            return "datetime"
        if str(in_type) in types:
            out_type = types[str(in_type)]
        else:
>           out_type = type(np.zeros(1, in_type).item()).__name__
                            ^^^^^^^^^^^^^^^^^^^^
E           TypeError: Cannot interpret '<StringDtype(storage='python', na_value=nan)>' as a data type

/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:686: TypeError
________________ ERROR at setup of test_offline_buildable_area _________________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_offline_buildable_area0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad72f480790>

    @pytest.fixture()
    def offline_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SNOCO_OFFLINE", "true")
        out_dir = tmp_path / "offline" / OFFLINE_PARCEL_ID
    
        if _is_geo_mocked():
            def _phase2(ctx: AnalysisContext, _client: FeasibilityAPIClient) -> AnalysisContext:
                ctx.parcel_geom = _LenOne()
                ctx.parcel_attrs = {"GIS_SQ_FT": 153331}
                return ctx
    
            def _buildable(ctx: AnalysisContext) -> AnalysisContext:
                ctx.buildable_geom = _FakeBuildableGeom(area_sf=120000.0)
                return ctx
    
            def _layouts(ctx: AnalysisContext) -> AnalysisContext:
                ctx.layouts = [{"id": "layout_1"}, {"id": "layout_2"}]
                return ctx
    
            def _tags(ctx: AnalysisContext) -> AnalysisContext:
                ctx.add_tag("INFO_OFFLINE_FIXTURE")
                return ctx
    
            def _export(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
                export_dir = output_dir or (tmp_path / "offline_exports")
                export_dir.mkdir(parents=True, exist_ok=True)
                png = export_dir / "feasibility_map.png"
                gpkg = export_dir / "feasibility_layers.gpkg"
                png.write_bytes(b"offline")
                gpkg.write_bytes(b"offline")
                ctx.export_paths = {"output_dir": str(export_dir), "png": str(png), "gpkg": str(gpkg)}
                return ctx
    
            monkeypatch.setattr(orch, "phase2", _phase2)
            monkeypatch.setattr(orch, "PHASES", [(_buildable, False), (_layouts, False), (_tags, False)])
            monkeypatch.setattr(orch, "phase7", _export)
    
>       return run_feasibility(OFFLINE_PARCEL_ID, output_dir=out_dir)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_feasibility.py:76: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
openclaw/analysis/feasibility/orchestrator.py:78: in run_feasibility
    ctx = phase7(ctx, output_dir=output_dir)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
openclaw/analysis/feasibility/phase7_export.py:23: in run
    _write_geojson(ctx.parcel_geom, out_dir / "parcel.geojson")
openclaw/analysis/feasibility/phase7_export.py:15: in _write_geojson
    gdf.to_file(path, driver="GeoJSON")
/usr/local/lib/python3.11/site-packages/geopandas/geodataframe.py:1249: in to_file
    _to_file(self, filename, driver, schema, index, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:610: in _to_file
    _to_file_fiona(df, filename, driver, schema, crs, mode, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:619: in _to_file_fiona
    schema = infer_schema(df)
             ^^^^^^^^^^^^^^^^
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:692: in infer_schema
    [
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:693: in <listcomp>
    (col, convert_type(col, _type))
          ^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

column = 'Parcel_ID', in_type = <StringDtype(storage='python', na_value=nan)>

    def convert_type(column, in_type):
        if in_type == object:
            return "str"
        if in_type.name.startswith("datetime64"):
            # numpy datetime type regardless of frequency
            return "datetime"
        if str(in_type) in types:
            out_type = types[str(in_type)]
        else:
>           out_type = type(np.zeros(1, in_type).item()).__name__
                            ^^^^^^^^^^^^^^^^^^^^
E           TypeError: Cannot interpret '<StringDtype(storage='python', na_value=nan)>' as a data type

/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:686: TypeError
_______________ ERROR at setup of test_offline_layouts_generated _______________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_offline_layouts_generated0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad72f45e3d0>

    @pytest.fixture()
    def offline_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SNOCO_OFFLINE", "true")
        out_dir = tmp_path / "offline" / OFFLINE_PARCEL_ID
    
        if _is_geo_mocked():
            def _phase2(ctx: AnalysisContext, _client: FeasibilityAPIClient) -> AnalysisContext:
                ctx.parcel_geom = _LenOne()
                ctx.parcel_attrs = {"GIS_SQ_FT": 153331}
                return ctx
    
            def _buildable(ctx: AnalysisContext) -> AnalysisContext:
                ctx.buildable_geom = _FakeBuildableGeom(area_sf=120000.0)
                return ctx
    
            def _layouts(ctx: AnalysisContext) -> AnalysisContext:
                ctx.layouts = [{"id": "layout_1"}, {"id": "layout_2"}]
                return ctx
    
            def _tags(ctx: AnalysisContext) -> AnalysisContext:
                ctx.add_tag("INFO_OFFLINE_FIXTURE")
                return ctx
    
            def _export(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
                export_dir = output_dir or (tmp_path / "offline_exports")
                export_dir.mkdir(parents=True, exist_ok=True)
                png = export_dir / "feasibility_map.png"
                gpkg = export_dir / "feasibility_layers.gpkg"
                png.write_bytes(b"offline")
                gpkg.write_bytes(b"offline")
                ctx.export_paths = {"output_dir": str(export_dir), "png": str(png), "gpkg": str(gpkg)}
                return ctx
    
            monkeypatch.setattr(orch, "phase2", _phase2)
            monkeypatch.setattr(orch, "PHASES", [(_buildable, False), (_layouts, False), (_tags, False)])
            monkeypatch.setattr(orch, "phase7", _export)
    
>       return run_feasibility(OFFLINE_PARCEL_ID, output_dir=out_dir)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_feasibility.py:76: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
openclaw/analysis/feasibility/orchestrator.py:78: in run_feasibility
    ctx = phase7(ctx, output_dir=output_dir)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
openclaw/analysis/feasibility/phase7_export.py:23: in run
    _write_geojson(ctx.parcel_geom, out_dir / "parcel.geojson")
openclaw/analysis/feasibility/phase7_export.py:15: in _write_geojson
    gdf.to_file(path, driver="GeoJSON")
/usr/local/lib/python3.11/site-packages/geopandas/geodataframe.py:1249: in to_file
    _to_file(self, filename, driver, schema, index, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:610: in _to_file
    _to_file_fiona(df, filename, driver, schema, crs, mode, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:619: in _to_file_fiona
    schema = infer_schema(df)
             ^^^^^^^^^^^^^^^^
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:692: in infer_schema
    [
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:693: in <listcomp>
    (col, convert_type(col, _type))
          ^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

column = 'Parcel_ID', in_type = <StringDtype(storage='python', na_value=nan)>

    def convert_type(column, in_type):
        if in_type == object:
            return "str"
        if in_type.name.startswith("datetime64"):
            # numpy datetime type regardless of frequency
            return "datetime"
        if str(in_type) in types:
            out_type = types[str(in_type)]
        else:
>           out_type = type(np.zeros(1, in_type).item()).__name__
                            ^^^^^^^^^^^^^^^^^^^^
E           TypeError: Cannot interpret '<StringDtype(storage='python', na_value=nan)>' as a data type

/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:686: TypeError
_________________ ERROR at setup of test_offline_tags_present __________________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_offline_tags_present0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad735821810>

    @pytest.fixture()
    def offline_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SNOCO_OFFLINE", "true")
        out_dir = tmp_path / "offline" / OFFLINE_PARCEL_ID
    
        if _is_geo_mocked():
            def _phase2(ctx: AnalysisContext, _client: FeasibilityAPIClient) -> AnalysisContext:
                ctx.parcel_geom = _LenOne()
                ctx.parcel_attrs = {"GIS_SQ_FT": 153331}
                return ctx
    
            def _buildable(ctx: AnalysisContext) -> AnalysisContext:
                ctx.buildable_geom = _FakeBuildableGeom(area_sf=120000.0)
                return ctx
    
            def _layouts(ctx: AnalysisContext) -> AnalysisContext:
                ctx.layouts = [{"id": "layout_1"}, {"id": "layout_2"}]
                return ctx
    
            def _tags(ctx: AnalysisContext) -> AnalysisContext:
                ctx.add_tag("INFO_OFFLINE_FIXTURE")
                return ctx
    
            def _export(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
                export_dir = output_dir or (tmp_path / "offline_exports")
                export_dir.mkdir(parents=True, exist_ok=True)
                png = export_dir / "feasibility_map.png"
                gpkg = export_dir / "feasibility_layers.gpkg"
                png.write_bytes(b"offline")
                gpkg.write_bytes(b"offline")
                ctx.export_paths = {"output_dir": str(export_dir), "png": str(png), "gpkg": str(gpkg)}
                return ctx
    
            monkeypatch.setattr(orch, "phase2", _phase2)
            monkeypatch.setattr(orch, "PHASES", [(_buildable, False), (_layouts, False), (_tags, False)])
            monkeypatch.setattr(orch, "phase7", _export)
    
>       return run_feasibility(OFFLINE_PARCEL_ID, output_dir=out_dir)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_feasibility.py:76: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
openclaw/analysis/feasibility/orchestrator.py:78: in run_feasibility
    ctx = phase7(ctx, output_dir=output_dir)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
openclaw/analysis/feasibility/phase7_export.py:23: in run
    _write_geojson(ctx.parcel_geom, out_dir / "parcel.geojson")
openclaw/analysis/feasibility/phase7_export.py:15: in _write_geojson
    gdf.to_file(path, driver="GeoJSON")
/usr/local/lib/python3.11/site-packages/geopandas/geodataframe.py:1249: in to_file
    _to_file(self, filename, driver, schema, index, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:610: in _to_file
    _to_file_fiona(df, filename, driver, schema, crs, mode, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:619: in _to_file_fiona
    schema = infer_schema(df)
             ^^^^^^^^^^^^^^^^
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:692: in infer_schema
    [
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:693: in <listcomp>
    (col, convert_type(col, _type))
          ^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

column = 'Parcel_ID', in_type = <StringDtype(storage='python', na_value=nan)>

    def convert_type(column, in_type):
        if in_type == object:
            return "str"
        if in_type.name.startswith("datetime64"):
            # numpy datetime type regardless of frequency
            return "datetime"
        if str(in_type) in types:
            out_type = types[str(in_type)]
        else:
>           out_type = type(np.zeros(1, in_type).item()).__name__
                            ^^^^^^^^^^^^^^^^^^^^
E           TypeError: Cannot interpret '<StringDtype(storage='python', na_value=nan)>' as a data type

/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:686: TypeError
_________________ ERROR at setup of test_offline_export_paths __________________

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-1/test_offline_export_paths0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad72f483250>

    @pytest.fixture()
    def offline_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SNOCO_OFFLINE", "true")
        out_dir = tmp_path / "offline" / OFFLINE_PARCEL_ID
    
        if _is_geo_mocked():
            def _phase2(ctx: AnalysisContext, _client: FeasibilityAPIClient) -> AnalysisContext:
                ctx.parcel_geom = _LenOne()
                ctx.parcel_attrs = {"GIS_SQ_FT": 153331}
                return ctx
    
            def _buildable(ctx: AnalysisContext) -> AnalysisContext:
                ctx.buildable_geom = _FakeBuildableGeom(area_sf=120000.0)
                return ctx
    
            def _layouts(ctx: AnalysisContext) -> AnalysisContext:
                ctx.layouts = [{"id": "layout_1"}, {"id": "layout_2"}]
                return ctx
    
            def _tags(ctx: AnalysisContext) -> AnalysisContext:
                ctx.add_tag("INFO_OFFLINE_FIXTURE")
                return ctx
    
            def _export(ctx: AnalysisContext, output_dir: Path | None = None) -> AnalysisContext:
                export_dir = output_dir or (tmp_path / "offline_exports")
                export_dir.mkdir(parents=True, exist_ok=True)
                png = export_dir / "feasibility_map.png"
                gpkg = export_dir / "feasibility_layers.gpkg"
                png.write_bytes(b"offline")
                gpkg.write_bytes(b"offline")
                ctx.export_paths = {"output_dir": str(export_dir), "png": str(png), "gpkg": str(gpkg)}
                return ctx
    
            monkeypatch.setattr(orch, "phase2", _phase2)
            monkeypatch.setattr(orch, "PHASES", [(_buildable, False), (_layouts, False), (_tags, False)])
            monkeypatch.setattr(orch, "phase7", _export)
    
>       return run_feasibility(OFFLINE_PARCEL_ID, output_dir=out_dir)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_feasibility.py:76: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
openclaw/analysis/feasibility/orchestrator.py:78: in run_feasibility
    ctx = phase7(ctx, output_dir=output_dir)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
openclaw/analysis/feasibility/phase7_export.py:23: in run
    _write_geojson(ctx.parcel_geom, out_dir / "parcel.geojson")
openclaw/analysis/feasibility/phase7_export.py:15: in _write_geojson
    gdf.to_file(path, driver="GeoJSON")
/usr/local/lib/python3.11/site-packages/geopandas/geodataframe.py:1249: in to_file
    _to_file(self, filename, driver, schema, index, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:610: in _to_file
    _to_file_fiona(df, filename, driver, schema, crs, mode, **kwargs)
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:619: in _to_file_fiona
    schema = infer_schema(df)
             ^^^^^^^^^^^^^^^^
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:692: in infer_schema
    [
/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:693: in <listcomp>
    (col, convert_type(col, _type))
          ^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

column = 'Parcel_ID', in_type = <StringDtype(storage='python', na_value=nan)>

    def convert_type(column, in_type):
        if in_type == object:
            return "str"
        if in_type.name.startswith("datetime64"):
            # numpy datetime type regardless of frequency
            return "datetime"
        if str(in_type) in types:
            out_type = types[str(in_type)]
        else:
>           out_type = type(np.zeros(1, in_type).item()).__name__
                            ^^^^^^^^^^^^^^^^^^^^
E           TypeError: Cannot interpret '<StringDtype(storage='python', na_value=nan)>' as a data type

/usr/local/lib/python3.11/site-packages/geopandas/io/file.py:686: TypeError
=================================== FAILURES ===================================
_____________________________ test_score_to_tier_b _____________________________

    def test_score_to_tier_b():
        """Scores >= 65 but < 80 → B tier."""
        assert score_to_tier(65) == "B"
>       assert score_to_tier(79) == "B"
E       AssertionError: assert 'A' == 'B'
E         
E         - B
E         + A

tests/test_scorer.py:22: AssertionError
_____________________________ test_score_to_tier_c _____________________________

    def test_score_to_tier_c():
        """Scores >= 50 but < 65 → C tier."""
        assert score_to_tier(50) == "C"
>       assert score_to_tier(64) == "C"
E       AssertionError: assert 'B' == 'C'
E         
E         - C
E         + B

tests/test_scorer.py:28: AssertionError
_____________________________ test_score_to_tier_d _____________________________

    def test_score_to_tier_d():
        """Scores >= 35 but < 50 → D tier."""
        assert score_to_tier(35) == "D"
>       assert score_to_tier(49) == "D"
E       AssertionError: assert 'C' == 'D'
E         
E         - D
E         + C

tests/test_scorer.py:34: AssertionError
_____________________________ test_score_to_tier_e _____________________________

    def test_score_to_tier_e():
        """Scores >= 20 but < 35 → E tier."""
        assert score_to_tier(20) == "E"
>       assert score_to_tier(34) == "E"
E       AssertionError: assert 'D' == 'E'
E         
E         - E
E         + D

tests/test_scorer.py:40: AssertionError
_____________________________ test_score_to_tier_f _____________________________

    def test_score_to_tier_f():
        """Scores < 20 → F tier."""
        assert score_to_tier(0) == "F"
>       assert score_to_tier(19) == "F"
E       AssertionError: assert 'E' == 'F'
E         
E         - F
E         + E

tests/test_scorer.py:46: AssertionError
____________________________ test_tier_just_below_a ____________________________

    def test_tier_just_below_a():
        """Score just below A threshold → B."""
>       assert score_to_tier(79) == "B"
E       AssertionError: assert 'A' == 'B'
E         
E         - B
E         + A

tests/test_scorer.py:57: AssertionError
____________________________ test_tier_just_below_b ____________________________

    def test_tier_just_below_b():
        """Score just below B threshold → C."""
>       assert score_to_tier(64) == "C"
E       AssertionError: assert 'B' == 'C'
E         
E         - C
E         + B

tests/test_scorer.py:62: AssertionError
=============================== warnings summary ===============================
../usr/local/lib/python3.11/site-packages/geopandas/_compat.py:10
  /usr/local/lib/python3.11/site-packages/geopandas/_compat.py:10: DeprecationWarning: The 'shapely.geos' module is deprecated, and will be removed in a future version. All attributes of 'shapely.geos' are available directly from the top-level 'shapely' namespace (since shapely 2.0.0).
    import shapely.geos

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_scorer.py::test_score_to_tier_b - AssertionError: assert 'A...
FAILED tests/test_scorer.py::test_score_to_tier_c - AssertionError: assert 'B...
FAILED tests/test_scorer.py::test_score_to_tier_d - AssertionError: assert 'C...
FAILED tests/test_scorer.py::test_score_to_tier_e - AssertionError: assert 'D...
FAILED tests/test_scorer.py::test_score_to_tier_f - AssertionError: assert 'E...
FAILED tests/test_scorer.py::test_tier_just_below_a - AssertionError: assert ...
FAILED tests/test_scorer.py::test_tier_just_below_b - AssertionError: assert ...
ERROR tests/test_feasibility.py::test_offline_parcel_load - TypeError: Cannot...
ERROR tests/test_feasibility.py::test_offline_buildable_area - TypeError: Can...
ERROR tests/test_feasibility.py::test_offline_layouts_generated - TypeError: ...
ERROR tests/test_feasibility.py::test_offline_tags_present - TypeError: Canno...
ERROR tests/test_feasibility.py::test_offline_export_paths - TypeError: Canno...
======== 7 failed, 142 passed, 5 skipped, 1 warning, 5 errors in 25.63s ========
