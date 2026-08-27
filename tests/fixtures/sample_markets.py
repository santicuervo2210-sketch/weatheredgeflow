from __future__ import annotations


BUENOS_AIRES_MULTI = {
    "id": "m-ba-max",
    "eventId": "e-ba-weather",
    "conditionId": "0xabc",
    "question": "What will the highest temperature in Buenos Aires, Argentina be on August 27?",
    "slug": "highest-temperature-buenos-aires-august-27",
    "resolutionSource": "https://weather.com/weather/today/l/Buenos+Aires",
    "endDate": "2026-08-28T03:00:00Z",
    "outcomes": '["18°C","19°C","20°C","21°C"]',
    "clobTokenIds": '["t18","t19","t20","t21"]',
    "feeSchedule": {"rate": 0.05, "exponent": 1, "takerOnly": True, "rebateRate": 0.25},
    "orderPriceMinTickSize": 0.01,
    "orderMinSize": 1,
}


NYC_BINARY = {
    "id": "m-nyc-max",
    "eventId": "e-nyc-weather",
    "conditionId": "0xdef",
    "question": "Will the highest temperature in New York City, US be 80°F or higher on August 27?",
    "slug": "nyc-high-temp-80f-august-27",
    "resolutionSource": "National Weather Service station KNYC",
    "endDate": "2026-08-28T04:00:00Z",
    "outcomes": '["Yes","No"]',
    "clobTokenIds": '["yes-token","no-token"]',
}


UNSUPPORTED_RAIN = {
    "id": "m-rain",
    "eventId": "e-rain",
    "question": "Will it rain in London on August 27?",
    "resolutionSource": "weather.com",
    "outcomes": '["Yes","No"]',
    "clobTokenIds": '["yes","no"]',
}


KALSHI_NYC_HIGH_LESS = {
    "event_ticker": "KXHIGHNY-26AUG27",
    "series_ticker": "KXHIGHNY",
    "ticker": "KXHIGHNY-26AUG27-T80",
    "title": "Will the maximum temperature be <80° on Aug 27, 2026?",
    "strike_type": "less",
    "cap_strike": 80,
    "close_time": "2026-08-28T05:00:00Z",
    "yes_sub_title": "79° or below",
    "no_sub_title": "80° or above",
    "rules_primary": "If the maximum temperature recorded at New York City (CLINYC) for Aug 27, 2026, is less than 80° fahrenheit according to The Weather Company, then the market resolves to Yes.",
    "rules_secondary": "The official and final value used to determine this market is the maximum/minimum temperature as reported by the Weather Company.",
}


KALSHI_ORDERBOOK = {
    "orderbook_fp": {
        "yes_dollars": [["0.3400", "26.74"], ["0.3200", "65.61"]],
        "no_dollars": [["0.6400", "261.00"], ["0.6300", "175.00"]],
    }
}
