"""Train the models, test them honestly, and produce the 7-day forecast.

For every forecast horizon (1 to 7 trading days ahead) we train three models:
  - Ridge regression   (a simple straight-line model)
  - XGBoost            (gradient-boosted decision trees)
  - LightGBM           (another, faster gradient-boosted trees library)
We average the three, then shrink that average toward "no change" by an amount
learned on validation data. Oil prices are close to a random walk, so a model
that knows when to be modest usually beats one that makes bold calls.

The data is split by time, never shuffled, so the models are always tested on
days that come *after* everything they were trained on:
  |------------ train 70% ------------|-- validation 15% --|-- test 15% --|
"""

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from .preprocess import build_features, build_target
from .utils import log

HORIZONS = range(1, 8)  # 1..7 trading days ahead
SEED = 42


def make_models() -> dict:
    """Three deliberately simple (heavily regularized) models.

    Daily oil moves are mostly noise. Bigger, more flexible models memorize
    that noise and score worse on the test period, so we keep these small.
    """
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1000.0)),
        "xgboost": XGBRegressor(
            n_estimators=150, max_depth=2, learning_rate=0.02, min_child_weight=30,
            subsample=0.7, colsample_bytree=0.7, reg_lambda=10, random_state=SEED, n_jobs=2,
        ),
        "lightgbm": LGBMRegressor(
            n_estimators=150, num_leaves=7, learning_rate=0.02, min_child_samples=60,
            subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=10,
            random_state=SEED, verbose=-1, n_jobs=2,
        ),
    }


def split_by_time(n: int, horizon: int):
    """Row positions for train / validation / test.

    We leave a gap of `horizon` rows between parts: a 7-day target from the last
    training day would otherwise overlap with the first validation days.
    """
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)
    train = np.arange(0, train_end - horizon)
    val = np.arange(train_end, val_end - horizon)
    test = np.arange(val_end, n)
    return train, val, test


def trust_factor(predictions: np.ndarray, actual: np.ndarray) -> float:
    """How much to trust the averaged prediction, between 0 and 1 (fit on validation data).

    1 means "use the models' average as is"; 0 means "just predict no change".
    It's the least-squares scale factor for the average, clipped to [0, 1].
    """
    average = predictions.mean(axis=1)
    scale = np.dot(average, actual) / max(np.dot(average, average), 1e-12)
    return float(np.clip(scale, 0.0, 1.0))


def forecast_asset(data: pd.DataFrame, asset: str) -> dict:
    """Run the full train/test/forecast cycle for one asset."""
    price = data[asset]
    features = build_features(data, asset)
    last_date = features.index[-1]
    last_row = features.iloc[[-1]]  # today's features -> tomorrow's forecast

    forecast, metrics, backtest = [], {}, []
    future_dates = pd.bdate_range(last_date + pd.offsets.BDay(1), periods=max(HORIZONS))

    for h in HORIZONS:
        target = build_target(price, h)
        rows = features.notna().all(axis=1) & target.notna()
        X, y, base_price = features[rows], target[rows], price[rows]
        train, val, test = split_by_time(len(X), h)

        # 1) Train each model on the training part, predict validation + test
        val_preds, test_preds = [], []
        for model in make_models().values():
            model.fit(X.iloc[train], y.iloc[train])
            val_preds.append(model.predict(X.iloc[val]))
            test_preds.append(model.predict(X.iloc[test]))
        val_preds, test_preds = np.column_stack(val_preds), np.column_stack(test_preds)

        # 2) Learn how much to trust the models, using validation data
        trust = trust_factor(val_preds, y.iloc[val].to_numpy())

        # 3) Score on the untouched test period, in dollars
        test_ret = trust * test_preds.mean(axis=1)
        p0 = base_price.iloc[test].to_numpy()
        actual = p0 * np.exp(y.iloc[test].to_numpy())
        predicted = p0 * np.exp(test_ret)
        up_actual = actual > p0
        metrics[h] = {
            "model_mae": round(float(np.mean(np.abs(predicted - actual))), 3),
            # "Naive" baseline: assume the price won't change at all
            "naive_mae": round(float(np.mean(np.abs(p0 - actual))), 3),
            "direction_accuracy": round(float(np.mean((test_ret > 0) == up_actual)) * 100, 1),
            "always_up_accuracy": round(float(np.mean(up_actual)) * 100, 1),
            "test_days": int(len(test)),
            "test_start": X.index[test[0]].strftime("%Y-%m-%d"),
            "trust": round(trust, 3),
        }

        # 80% range: how far off were we on 8 out of 10 test days?
        errors = y.iloc[test].to_numpy() - test_ret
        low_q, high_q = np.quantile(errors, [0.10, 0.90])

        if h == 1:
            target_dates = X.index[test] + pd.offsets.BDay(1)
            backtest = [
                {"date": d.strftime("%Y-%m-%d"), "actual": round(float(a), 2), "predicted": round(float(p), 2)}
                for d, a, p in zip(target_dates, actual, predicted)
            ]

        # 4) Retrain on ALL data (train + validation + test) and forecast from today
        final_preds = []
        for model in make_models().values():
            model.fit(X, y)
            final_preds.append(model.predict(last_row)[0])
        ret = trust * float(np.mean(final_preds))
        today = float(price.iloc[-1])
        forecast.append({
            "horizon": h,
            "date": future_dates[h - 1].strftime("%Y-%m-%d"),
            "price": round(today * np.exp(ret), 2),
            "low": round(today * np.exp(ret + low_q), 2),
            "high": round(today * np.exp(ret + high_q), 2),
            "change_pct": round((np.exp(ret) - 1) * 100, 2),
        })
        log(asset.upper(), f"h={h}: forecast ${forecast[-1]['price']:.2f} | "
            f"test MAE ${metrics[h]['model_mae']:.2f} vs naive ${metrics[h]['naive_mae']:.2f} | "
            f"direction {metrics[h]['direction_accuracy']:.0f}%")

    history = price.iloc[-250:]
    return {
        "last_date": last_date.strftime("%Y-%m-%d"),
        "last_price": round(float(price.iloc[-1]), 2),
        "prev_price": round(float(price.iloc[-2]), 2),
        "history": [{"date": d.strftime("%Y-%m-%d"), "price": round(float(p), 2)} for d, p in history.items()],
        "forecast": forecast,
        "metrics": {str(h): m for h, m in metrics.items()},
        "backtest": backtest[-120:],
        "features_used": list(features.columns),
    }
