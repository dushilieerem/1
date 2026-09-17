import numpy as np
import pandas as pd
import pytest

from app.services.factor.tool import (
    mad_winsorize,
    neutralize,
    normalize,
    preprocess_factor_values,
    rank,
    standardize_data,
    winsorize,
    winsorize_data,
    zscore,
)


@pytest.fixture
def values():
    return pd.DataFrame(
        [[1.0, 2.0, 100.0, np.nan], [5.0, 5.0, 5.0, np.nan]],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        columns=["A", "B", "C", "D"],
    )


def test_winsorize_by_cross_section_and_validate_bounds(values):
    result = winsorize(values, 0.0, 0.5)
    assert result.loc[values.index[0], "C"] == 2.0
    assert pd.isna(result.loc[values.index[0], "D"])
    with pytest.raises(ValueError):
        winsorize(values, 0.8, 0.2)


def test_mad_winsorize_and_zero_mad(values):
    result = mad_winsorize(values, n=1.0)
    assert result.iloc[0, 2] < values.iloc[0, 2]
    assert result.iloc[1, :3].tolist() == [5.0, 5.0, 5.0]
    assert pd.isna(result.iloc[1, 3])


def test_zscore_rank_and_normalize_preserve_missing_values(values):
    standardized = zscore(values)
    assert standardized.iloc[0, :3].mean() == pytest.approx(0.0)
    assert standardized.iloc[1, :3].tolist() == [0.0, 0.0, 0.0]
    assert pd.isna(standardized.iloc[0, 3])

    assert rank(values).iloc[0, :3].tolist() == [pytest.approx(1 / 3), pytest.approx(2 / 3), 1.0]
    normalized = normalize(values)
    assert normalized.iloc[0, :3].abs().sum() == pytest.approx(1.0)
    assert normalized.iloc[1, :3].tolist() == [pytest.approx(1 / 3)] * 3
    assert pd.isna(normalized.iloc[1, 3])


def test_external_factor_preprocessing_uses_date_cross_sections():
    values = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0, 100.0], [1.0, 2.0, 3.0, np.nan, 5.0]],
        index=pd.date_range("2024-01-02", periods=2),
        columns=list("ABCDE"),
    )

    mad = winsorize_data(values, method=1)
    assert mad.iloc[0, 4] == pytest.approx(8.2)
    assert pd.isna(mad.iloc[1, 3])

    ranked = standardize_data(values.iloc[:, :3], method=2)
    assert ranked.iloc[0].mean() == pytest.approx(0.0)
    assert ranked.iloc[0].std() == pytest.approx(1.0)

    minmax = standardize_data(values.iloc[:, :3], method=3)
    assert minmax.iloc[0].tolist() == pytest.approx([0.0, 0.5, 1.0])

    combined = preprocess_factor_values(values, winsorize=1, standardize=2)
    expected = standardize_data(mad, method=2)
    pd.testing.assert_frame_equal(combined, expected)

    with pytest.raises(ValueError):
        winsorize_data(values, method=4)
    with pytest.raises(ValueError):
        standardize_data(values, method=4)


def test_neutralize_removes_industry_and_log_market_cap_exposures():
    dates = pd.to_datetime(["2024-01-02"])
    symbols = ["A", "B", "C", "D", "E", "F"]
    industry = pd.Series(["bank", "bank", "tech", "tech", "bank", "tech"], index=symbols)
    caps = pd.DataFrame([[10, 20, 10, 20, 40, 40]], index=dates, columns=symbols)
    # 行业效应 + 对数市值效应；回归后的残差应与各暴露正交。
    y = 3.0 + (industry == "tech").to_numpy() * 7.0 + 2.0 * np.log(caps.iloc[0].to_numpy())
    y += np.array([-1.0, 1.0, -2.0, 2.0, 0.5, -0.5])
    values = pd.DataFrame([y], index=dates, columns=symbols)

    result = neutralize(values, industry=industry, market_cap=caps)
    residual = result.iloc[0].to_numpy()
    design = np.column_stack(
        [
            np.ones(len(symbols)),
            (industry == "tech").to_numpy(dtype=float),
            np.log(caps.iloc[0].to_numpy()),
        ]
    )
    assert design.T @ residual == pytest.approx(np.zeros(3), abs=1e-10)


def test_neutralize_validates_inputs_and_returns_nan_for_insufficient_samples():
    values = pd.DataFrame([[1.0, 2.0]], columns=["A", "B"])
    with pytest.raises(ValueError):
        neutralize(values)
    result = neutralize(values, market_cap=pd.DataFrame([[10.0, 20.0]], columns=["A", "B"]))
    assert result.iloc[0].isna().all()
