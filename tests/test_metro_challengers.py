import numpy as np
import pandas as pd
import pytest

from src import metro_challengers as metro


def fixture_frame(n=150):
    rng = np.random.default_rng(12)
    frame = pd.DataFrame({"ID": [f"synthetic-{i}" for i in range(n)],
        "Start_Time": pd.date_range("2017-01-01", periods=n, freq="3h"),
        "Start_Lat": 41+np.arange(n)%20*.025, "Start_Lng": -96+np.arange(n)%15*.025,
        "Severity": 1+np.arange(n)%4, "Source": np.where(np.arange(n)%2, "Source1", "Source2"),
        "weather_group": "clear", "Wind_Direction": "N", "is_night": np.arange(n)%2,
        "duration_min": 10.+np.arange(n)%20, "naip_year": 2022})
    frame["End_Time"] = frame.Start_Time+pd.to_timedelta(frame.duration_min, unit="m")
    frame["log_duration"] = np.log1p(frame.duration_min)
    embed = pd.DataFrame(rng.normal(size=(n, 512)), columns=metro.EMB)
    return pd.concat([frame, embed], axis=1)


def test_original_outer_test_ids_preserved_and_both_fit_boundaries_embargoed():
    frame = fixture_frame(100)
    frame.loc[63, "End_Time"] = frame.Start_Time[65]
    frame.loc[79, "End_Time"] = frame.Start_Time[81]
    masks, _, meta = metro.frozen_split(frame)
    assert np.array_equal(np.flatnonzero(masks["test"]), np.arange(80, 100))
    assert not masks["inner_train"][63] and not masks["outer_train"][79]
    assert not masks["validation"][79]
    assert meta["inner_label_embargo"] == 1 and meta["outer_label_embargo"] == 1
    assert meta["original_test_id_sha256"] == meta["id_sha256"]["test"]
    assert (frame.End_Time[masks["inner_train"]] < pd.Timestamp(meta["inner_start"])).all()
    assert (frame.End_Time[masks["outer_train"]] < pd.Timestamp(meta["outer_test_start"])).all()


def test_spatial_forward_training_and_test_cells_do_not_overlap():
    frame = fixture_frame(1000)
    masks, groups, _ = metro.frozen_split(frame, "spatial_future")
    assert not set(groups[masks["inner_train"]]) & set(groups[masks["validation"]])
    assert not set(groups[masks["outer_train"]]) & set(groups[masks["test"]])
    assert (frame.Start_Time[masks["inner_train"]].max() < frame.Start_Time[masks["validation"]].min())


def test_history_uses_only_ended_fit_events_not_holdout_outcomes():
    frame = fixture_frame(5)
    frame["Start_Lat"], frame["Start_Lng"] = 41., -96.
    frame["Start_Time"] = pd.to_datetime(["2020-01-01 00:00", "2020-01-01 00:10", "2020-01-01 00:25", "2020-01-01 00:40", "2020-01-01 00:50"])
    frame["End_Time"] = pd.to_datetime(["2020-01-01 00:30", "2020-01-01 00:20", "2020-01-01 00:26", "2020-01-01 00:41", "2020-01-01 01:00"])
    mask = np.array([True, True, False, False, False])
    first = metro.frozen_neighborhood(frame, mask)
    assert first.nb_count.tolist() == [0, 0, 1, 2, 2]
    assert first.nb_mean_severity[2] == frame.Severity[1]
    modified = frame.copy(); modified.loc[~mask, "Severity"] = 4; modified.loc[~mask, "log_duration"] = 999.
    pd.testing.assert_frame_equal(first, metro.frozen_neighborhood(modified, mask))


def test_pca_and_categories_are_fitted_on_training_only():
    frame = fixture_frame(80)
    columns = ["Source", "Start_Lat", "img_pca_0", "img_pca_1"]
    design = metro.MetroDesign(columns, pca_components=2).fit(frame.iloc[:50])
    original_mean = design.pca.mean_.copy(); original_vocab = dict(design.vocab)
    test = frame.iloc[50:].copy(); test[metro.EMB] = test[metro.EMB]+10000; test["Source"] = "test-only-feed"
    transformed = design.transform(test)
    assert transformed[:, design.feature_names.index("Source=<unseen>")].min() == 1
    np.testing.assert_array_equal(design.pca.mean_, original_mean)
    assert design.vocab == original_vocab
    assert "test-only-feed" not in design.vocab["Source"]


def test_absent_imagery_remains_missing_instead_of_fabricated_embeddings():
    frame = fixture_frame(40); frame.loc[30:, "naip_year"] = np.nan
    design = metro.MetroDesign(["img_pca_0", "img_pca_1"], pca_components=2).fit(frame.iloc[:30])
    assert np.isnan(design.transform(frame.iloc[30:])).all()


def test_four_class_metrics_and_rare_validation_rule_preserve_class_one():
    y = np.array([1, 1]+[2]*10+[3]*10+[4]*10)
    p = np.full((len(y), 4), .1); p[np.arange(len(y)), y-1] = .7
    decision = metro.fit_decision(y, p)
    assert decision["class_weights"][0] == 1
    assert decision["low_support_classes_weights_frozen"] == [1]
    labels, calibrated = metro.apply_decision(p, decision)
    scored = metro.class_metrics(y, labels, calibrated)
    assert scored["per_class"]["1"]["support"] == 2
    assert set(scored["per_class"]) == {"1", "2", "3", "4"}
    assert scored["balanced_accuracy"] == 1 and scored["macro_f1"] == 1


def test_source_recency_constants_never_use_holdout_labels_and_pure_image_has_no_source():
    frame = fixture_frame(10)
    frame["Start_Time"] = pd.date_range("2018-01-01", periods=10, freq="100D")
    frame["log_duration"] = np.arange(10, dtype=float)
    x = np.zeros((10, 1))
    model = metro.fit_regression("recent_source_mean", x, frame, use_source=True)
    assert model["fit_rows"] == 4
    assert model["by_source"]["Source1"] == 8
    assert model["by_source"]["Source2"] == 7
    pure = metro.fit_regression("recent_source_mean", x, frame, use_source=False)
    assert pure["by_source"] == {}
    assert pure["value"] == 7.5
    frame["log_duration"] = 9999.
    assert np.all(metro.predict_regression(pure, x, frame) == 7.5)
    assert np.all(metro.predict_regression(pure, x, frame.drop(columns="Source")) == 7.5)


def test_duration_selection_uses_declared_metric_and_shared_bounds():
    y = np.log1p([1, 1, 1, 1000])
    predictions = {"log": np.log1p([1, 1, 1, 100]), "minute": np.log1p([10, 10, 10, 1000]), "bad": np.log1p([100, 100, 100, 100])}
    selection = metro.choose_duration_blend(y, predictions, "MAE_min")
    assert selection["member_a"] == "minute"
    assert selection["validation"]["MAE_min"] == pytest.approx(6.75)
    scored = metro.duration_metrics(np.log1p([1, 10080]), np.array([-100., 100.]))
    assert scored["MAE_min"] == pytest.approx(.5)


def test_all_five_ablations_preserve_their_declared_modalities():
    features = metro.feature_sets()
    assert list(features) == ["A_tabular", "B_tabular+gis", "C_imagery", "D_tabular+gis+imagery", "E_D+neighborhood"]
    assert "Source" in features["A_tabular"]
    assert "Source" not in features["C_imagery"]
    assert set(features["E_D+neighborhood"])-set(features["D_tabular+gis+imagery"]) == set(metro.NEIGHBORHOOD)
    assert not set(features["D_tabular+gis+imagery"]) & {"Severity", "duration_min", "End_Time", "Distance(mi)"}


def test_tree_recipes_disable_implicit_random_early_stopping():
    for name in metro.CLASSIFIERS:
        if name.endswith("hgb"):
            assert metro.classifier(name).early_stopping is False


def test_small_protocol_saves_auditable_predictions_without_touching_originals(tmp_path, monkeypatch):
    from sklearn.ensemble import HistGradientBoostingClassifier
    frame = fixture_frame(100)
    monkeypatch.setattr(metro, "feature_sets", lambda: {"D_tabular+gis+imagery": ["Source", "is_night"],
                                                     "E_D+neighborhood": ["Source", "is_night"]+metro.NEIGHBORHOOD})
    monkeypatch.setattr(metro, "classifier", lambda name, seed: HistGradientBoostingClassifier(max_iter=2, early_stopping=False, random_state=seed))
    original_fit = metro.fit_regression
    monkeypatch.setattr(metro, "fit_regression", lambda name, x, frame, use_source, seed:
                        original_fit("training_mean", x, frame, use_source, seed))
    monkeypatch.setattr(metro, "TRUSTED_MODEL_ROOT", tmp_path/"models")
    result = metro.run_protocol(frame, "temporal", tmp_path, draws=0)
    row = result["ablations"][0]
    assert result["split"]["counts"]["test"] == 20
    assert set(row["classification_challenger"]["per_class"]) == {"1", "2", "3", "4"}
    assert set(row["duration_blends"]) == {"MSE_log", "MAE_min"}
    prediction_file = next(tmp_path.rglob("*.predictions.parquet"))
    predictions = pd.read_parquet(prediction_file)
    assert predictions.ID.tolist() == frame.ID.iloc[80:].tolist()
    assert row["artifact_sha256"] == metro.digest(row["artifact"])
    for row in result["ablations"]:
        from pathlib import Path
        artifact = Path(row["artifact"])
        archived = pd.read_parquet(artifact.with_suffix(".predictions.parquet"))
        query = frame.iloc[80:].copy()
        for column in metro.NEIGHBORHOOD:
            query[column] = 999999.
        replay = metro.predict_artifact(query, artifact)
        assert replay["research_only"] and not replay["commercial_eligible"]
        np.testing.assert_array_equal(replay["severity_class"], archived.severity_challenger)
        np.testing.assert_allclose(replay["duration_blends"]["MAE_min"]["log_duration"], archived.log_duration_mae_blend)
        np.testing.assert_allclose(replay["duration_blends"]["MSE_log"]["log_duration"], archived.log_duration_r2_blend)
        if artifact.stem == "E":
            history = pd.read_parquet(artifact.with_suffix(".history.parquet"))
            history.loc[0, "Severity"] = 99
            history.to_parquet(artifact.with_suffix(".history.parquet"), index=False)
            with pytest.raises(ValueError, match="digest mismatch"):
                metro.predict_artifact(query, artifact)


def test_reload_rejects_untrusted_model_paths(tmp_path):
    with pytest.raises(ValueError, match="fixed trusted"):
        metro.predict_artifact(fixture_frame(5), tmp_path/"arbitrary.joblib")
