from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class WeatherEdgeflowGuardedStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    startup_candle_count = 80
    can_short = False

    minimal_roi = {
        "0": 0.018,
        "45": 0.01,
        "120": 0.0,
    }
    stoploss = -0.012
    trailing_stop = True
    trailing_stop_positive = 0.006
    trailing_stop_positive_offset = 0.012
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {
        "entry": "gtc",
        "exit": "gtc",
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"]
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, 1e-12)

        dataframe["rsi"] = 100 - (100 / (1 + rs))
        dataframe["ema_fast"] = close.ewm(span=12, adjust=False).mean()
        dataframe["ema_slow"] = close.ewm(span=26, adjust=False).mean()
        dataframe["sma_fast"] = close.rolling(20).mean()
        dataframe["sma_slow"] = close.rolling(50).mean()
        dataframe["volume_sma"] = dataframe["volume"].rolling(20).mean()
        dataframe["range_pct"] = (dataframe["high"] - dataframe["low"]) / close
        dataframe["range_pct_sma"] = dataframe["range_pct"].rolling(30).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (dataframe["volume"] > dataframe["volume_sma"] * 0.75)
                & (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["sma_fast"] > dataframe["sma_slow"])
                & (dataframe["close"] > dataframe["sma_fast"])
                & (dataframe["rsi"] > 52)
                & (dataframe["rsi"] < 68)
                & (dataframe["range_pct"] < dataframe["range_pct_sma"] * 2.2)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    (dataframe["rsi"] > 74)
                    | (dataframe["ema_fast"] < dataframe["ema_slow"])
                    | (dataframe["close"] < dataframe["sma_fast"] * 0.988)
                )
            ),
            "exit_long",
        ] = 1
        return dataframe
