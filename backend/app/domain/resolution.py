from __future__ import annotations

from typing import Any

from app.clients.polymarket import parse_json_list


class ResolutionEngine:
    def extract_winner(self, market: dict[str, Any]) -> tuple[str | None, str | None]:
        if not _is_closed_or_resolved(market):
            return None, None
        outcomes = [str(item) for item in parse_json_list(market.get("outcomes"))]
        token_ids = [str(item) for item in parse_json_list(market.get("clobTokenIds") or market.get("clob_token_ids"))]
        winner = (
            market.get("winningOutcome")
            or market.get("winning_outcome")
            or market.get("winner")
            or market.get("resolvedOutcome")
            or market.get("resolution")
        )
        if winner is not None:
            winner_label = str(winner)
            for label, token_id in zip(outcomes, token_ids, strict=False):
                if label.lower() == winner_label.lower():
                    return token_id, label
            if winner_label in token_ids:
                idx = token_ids.index(winner_label)
                return winner_label, outcomes[idx] if idx < len(outcomes) else None
            return None, winner_label
        prices = parse_json_list(market.get("outcomePrices"))
        if outcomes and token_ids and prices and len(prices) == len(token_ids):
            numeric = []
            for price in prices:
                try:
                    numeric.append(float(price))
                except (TypeError, ValueError):
                    numeric.append(0.0)
            if numeric and max(numeric) >= 0.99:
                idx = numeric.index(max(numeric))
                return token_ids[idx], outcomes[idx]
        return None, None


def _is_closed_or_resolved(market: dict[str, Any]) -> bool:
    for key in ("closed", "resolved", "archived"):
        value = market.get(key)
        if value is True or str(value).lower() == "true":
            return True
    return False

