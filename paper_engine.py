"""Persistent PAPER-ONLY binary-contract simulator; no exchange order endpoints."""
import datetime as dt
import sqlite3
from decimal import Decimal as D
from risk_engine import PaperAccount, check_paper_trade


def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


class PaperEngine:
    def __init__(self, path='paper_ledger.sqlite3'):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('''CREATE TABLE IF NOT EXISTS trades (
            signal_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, side TEXT NOT NULL,
            price TEXT NOT NULL, contracts INTEGER NOT NULL, fee TEXT NOT NULL,
            status TEXT NOT NULL, opened_day TEXT NOT NULL,
            settled_day TEXT, payout TEXT, pnl TEXT)''')

    def close(self):
        self.db.close()

    def account(self, day=None):
        day = day or today()
        open_rows = self.db.execute("SELECT price,contracts,fee FROM trades WHERE status='OPEN'").fetchall()
        exposure = sum((D(p)*n+D(f) for p,n,f in open_rows), D('0'))
        all_pnl = sum((D(r[0]) for r in self.db.execute("SELECT pnl FROM trades WHERE status='SETTLED'")), D('0'))
        daily_pnl = sum((D(r[0]) for r in self.db.execute("SELECT pnl FROM trades WHERE status='SETTLED' AND settled_day=?", (day,))), D('0'))
        return PaperAccount(cash=D('5000')+all_pnl-exposure, open_exposure=exposure,
                            realized_daily_pnl=daily_pnl)

    def enter(self, *, signal_id, ticker, side, ask, ask_size, contracts, fee, day=None):
        """Record an assumed fill at a supplied ask; quote freshness is caller's duty."""
        day = day or today()
        if not signal_id or not ticker:
            return False, 'Missing signal ID or ticker'
        if not isinstance(ask_size, int) or isinstance(ask_size, bool) or ask_size < 0:
            return False, 'Invalid displayed liquidity'
        if not isinstance(contracts, int) or isinstance(contracts, bool) or contracts > ask_size:
            return False, 'Insufficient displayed liquidity'
        try:
            ask, fee = D(str(ask)), D(str(fee))
            if not ask.is_finite() or not fee.is_finite():
                return False, 'Non-finite price or fee'
        except Exception:
            return False, 'Invalid price or fee'
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM trades WHERE signal_id=?', (signal_id,)).fetchone():
                self.db.execute('ROLLBACK')
                return False, 'Duplicate signal'
            ok, reason = check_paper_trade(self.account(day), side, ask, contracts, fee)
            if not ok:
                self.db.execute('ROLLBACK')
                return False, reason
            self.db.execute('''INSERT INTO trades
                (signal_id,ticker,side,price,contracts,fee,status,opened_day)
                VALUES (?,?,?,?,?,?,'OPEN',?)''',
                (signal_id,ticker,side,str(ask),contracts,str(fee),day))
            self.db.execute('COMMIT')
            return True, 'PAPER fill recorded (assumed at supplied ask)'
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def settle(self, signal_id, winning_side, day=None):
        """Caller must verify official settlement; never infer winning side."""
        if winning_side not in ('YES','NO'):
            return False, 'Invalid outcome'
        day = day or today()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT side,price,contracts,fee,status FROM trades WHERE signal_id=?', (signal_id,)).fetchone()
            if not row or row[4] != 'OPEN':
                self.db.execute('ROLLBACK')
                return False, 'Position missing or already settled'
            side,price,n,fee,_ = row
            payout = D(n) if side == winning_side else D('0')
            pnl = payout-D(price)*n-D(fee)
            self.db.execute("UPDATE trades SET status='SETTLED',settled_day=?,payout=?,pnl=? WHERE signal_id=?",
                            (day,str(payout),str(pnl),signal_id))
            self.db.execute('COMMIT')
            return True, str(pnl)
        except Exception:
            self.db.execute('ROLLBACK')
            raise
