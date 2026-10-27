"""Paper-only risk checks. No exchange connectivity or order placement."""
from dataclasses import dataclass
from decimal import Decimal

D = Decimal

@dataclass(frozen=True)
class RiskLimits:
    max_position_loss: Decimal = D('50')
    daily_loss_cutoff: Decimal = D('150')
    max_open_exposure: Decimal = D('500')

@dataclass(frozen=True)
class PaperAccount:
    cash: Decimal = D('5000')
    open_exposure: Decimal = D('0')
    realized_daily_pnl: Decimal = D('0')
    unrealized_daily_pnl: Decimal = D('0')


def check_paper_trade(account: PaperAccount, side: str, price: Decimal,
                      contracts: int, estimated_fees: Decimal = D('0'),
                      limits: RiskLimits = RiskLimits()) -> tuple[bool, str]:
    """Conservative full-stake-at-risk check for a new binary contract position.

    The caller must supply a conservative estimate of all execution fees.
    State updates must be atomic when multiple signals arrive concurrently.
    """
    if side not in ('YES', 'NO'):
        return False, 'Invalid side'
    if not isinstance(contracts, int) or isinstance(contracts, bool) or contracts <= 0:
        return False, 'Contracts must be a positive integer'
    if not (D('0') < price < D('1')) or estimated_fees < 0:
        return False, 'Invalid price or fees'
    if account.cash < 0 or account.open_exposure < 0:
        return False, 'Invalid account state'
    if account.realized_daily_pnl + account.unrealized_daily_pnl <= -limits.daily_loss_cutoff:
        return False, 'Daily loss cutoff reached'
    cost = price * contracts + estimated_fees
    if cost > limits.max_position_loss:
        return False, 'Position loss limit exceeded'
    if account.open_exposure + cost > limits.max_open_exposure:
        return False, 'Open exposure limit exceeded'
    if cost > account.cash:
        return False, 'Insufficient paper cash'
    return True, 'Approved for paper simulation only'
