"""텔레그램 알림 포맷 + 전송.

스타일 원칙:
- 해설/요약 문구 금지 (숫자와 상태만)
- 구분선은 정보 블록 구분용 1회
- 이모지는 상태(🟢🟡🔴) / 결과(✅❌) / 경고(🚨)만 최소
"""

import requests
from enum import Enum
from typing import Optional, Dict, Any

from config import TELEGRAM, get_logger

logger = get_logger("telegram")

USDKRW = 1470
SEP = "─" * 28


def _krw(usd: float) -> str:
    krw = usd * USDKRW
    if abs(krw) >= 1000:
        return f"₩{krw:+,.0f}"
    return f"₩{krw:+.0f}"


def _regime_ko(regime: str) -> str:
    return {
        "TRENDING_UP": "상승추세",
        "TRENDING_DOWN": "하락추세",
        "RANGING": "횡보",
        "HIGH_VOL": "고변동",
    }.get(regime.upper(), regime)


def _direction_ko(direction: str) -> str:
    return "LONG" if "LONG" in direction.upper() else "SHORT"


def _fmt_hold(raw: str) -> str:
    return raw if raw and raw != "?" else "—"


class AlertPriority(Enum):
    P0_EMERGENCY = "emergency"
    P1_TRADE = "trade"
    P2_INFO = "info"


class TelegramNotifier:
    """Bybit → HERMES → 사용자로 이어지는 마지막 레이어. 모든 메시지를 동기 전송."""

    def __init__(self):
        self.bot_token = TELEGRAM.BOT_TOKEN
        self.chat_id = TELEGRAM.CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        if not self.bot_token or not self.chat_id:
            logger.warning("텔레그램 설정 누락")

    def _send_request(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False
        try:
            payload = {"chat_id": self.chat_id, "text": message}
            response = requests.post(self.base_url, json=payload, timeout=5)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"텔레그램 전송 실패: {e}")
            return False

    def send(self, message: str, priority: AlertPriority = AlertPriority.P2_INFO) -> bool:
        return self._send_request(message)

    def emergency(self, message: str) -> bool:
        return self.send(message, AlertPriority.P0_EMERGENCY)

    def trade(self, message: str) -> bool:
        return self.send(message, AlertPriority.P1_TRADE)

    def info(self, message: str) -> bool:
        return self.send(message, AlertPriority.P2_INFO)

    def status(self, message: str) -> bool:
        return self.send(message, AlertPriority.P2_INFO)

    # ================================================================
    # 시스템
    # ================================================================

    def send_system_start(self, balance: float, position_info=None, is_restart=False):
        pos = "없음"
        if position_info:
            d = position_info.get("direction", "?")
            l = position_info.get("leverage", 0)
            pos = f"{d} {l}x" if l else f"{d}"

        return self.info(
            f"🟢 HERMES 가동\n"
            f"{SEP}\n"
            f"잔고  ${balance:,.2f} ({_krw(balance).replace('+', '')})\n"
            f"포지션  {pos}"
        )

    def send_periodic_summary(
        self,
        balance: float,
        daily_stats: dict,
        peak_balance: float = 0,
        active_positions: int = 0,
    ):
        daily_pnl = daily_stats.get("daily_pnl", 0)
        trades = daily_stats.get("trades", 0)
        wins = daily_stats.get("wins", 0)
        losses = daily_stats.get("losses", 0)
        cons_loss = daily_stats.get("consecutive_losses", 0)

        win_rate = f"{100*wins/trades:.0f}%" if trades > 0 else "—"

        dd_str = "—"
        if peak_balance > 0:
            dd = (peak_balance - balance) / peak_balance * 100
            if dd >= 12:
                dd_str = f"🔴 {dd:.1f}% (사이즈 25%)"
            elif dd >= 8:
                dd_str = f"🟠 {dd:.1f}% (사이즈 50%)"
            elif dd >= 5:
                dd_str = f"🟡 {dd:.1f}% (사이즈 75%)"
            else:
                dd_str = f"🟢 {dd:.1f}%"

        pnl_emoji = "🟢" if daily_pnl >= 0 else "🔴"

        return self.info(
            f"📊 30분 요약\n"
            f"{SEP}\n"
            f"잔고  ${balance:,.2f} ({_krw(balance).replace('+', '')})\n"
            f"DD    {dd_str}\n"
            f"오늘  {trades}거래 · {wins}승 {losses}패 ({win_rate})\n"
            f"PnL   {pnl_emoji} ${daily_pnl:+.2f} ({_krw(daily_pnl)})\n"
            f"연패  {cons_loss} · 활성 {active_positions}"
        )

    def send_system_error(self, error_type, error_msg, location):
        return self.emergency(
            f"🚨 시스템 오류\n"
            f"{SEP}\n"
            f"위치  {location}\n"
            f"유형  {error_type}\n"
            f"{error_msg}"
        )

    # ================================================================
    # 4H 레짐 판독
    # ================================================================

    def send_regime_update(self, symbol: str, regime: str, indicators: dict,
                           changed: bool, old_regime: str = ""):
        coin = symbol.replace("USDT", "")
        regime_ko = _regime_ko(regime)

        adx = indicators.get("adx", 0)
        atr = indicators.get("atr_pct", 0)
        ema9 = indicators.get("ema_9", 0)
        ema21 = indicators.get("ema_21", 0)
        plus_di = indicators.get("plus_di", 0)
        minus_di = indicators.get("minus_di", 0)
        atr_pctl = indicators.get("atr_percentile", 0)
        close = indicators.get("close", 0)

        if changed:
            old_ko = _regime_ko(old_regime)
            header = f"[{coin}] 레짐 {old_ko} → {regime_ko}"
        else:
            header = f"[{coin}] 레짐 · {regime_ko}"

        ema_arrow = ">" if ema9 > ema21 else "<"

        return self.info(
            f"{header}\n"
            f"{SEP}\n"
            f"가격  ${close:,.2f}\n"
            f"ADX   {adx:.1f} (+DI {plus_di:.0f} / -DI {minus_di:.0f})\n"
            f"ATR   {atr:.2f}% (상위 {atr_pctl:.0f}%)\n"
            f"EMA9 {ema_arrow} EMA21  ({ema9:,.2f} / {ema21:,.2f})"
        )

    # ================================================================
    # 1H 시그널 체크
    # ================================================================

    def send_signal_check(self, symbol: str, regime: str, indicators: dict,
                          signal_result=None, reject_reason: str = "",
                          orderbook=None, funding_rate: float = 0,
                          daily_trend: Optional[Dict[str, Any]] = None):
        coin = symbol.replace("USDT", "")
        close = indicators.get("close", 0)
        rsi = indicators.get("rsi", 0)
        atr = indicators.get("atr_pct", 0)
        ema_f = indicators.get("ema_fast", 0)
        vol = indicators.get("volume_ratio", 0)
        bb_pos = indicators.get("price_position", 50)

        ema_dist = abs(close - ema_f) / ema_f * 100 if ema_f > 0 else 0
        ema_dir = "위" if close > ema_f else "아래"

        regime_ko = _regime_ko(regime)

        rsi_tag = ""
        if rsi >= 70:
            rsi_tag = " 과매수"
        elif rsi <= 30:
            rsi_tag = " 과매도"

        extra_lines = []

        # 1D 필터
        if daily_trend:
            from config import PARAM_REGISTRY
            mode = int(PARAM_REGISTRY.get("d1_filter_mode"))
            period = int(PARAM_REGISTRY.get("d1_ema_period"))
            if mode == 0:
                d1_dir_map = {"UP": "상승", "DOWN": "하락", "FLAT": "평탄"}
                d1_dir = d1_dir_map.get(daily_trend.get("direction", "FLAT"), "평탄")
                d1_slope = daily_trend.get("slope_pct", 0)
                extra_lines.append(f"1D EMA{period}  {d1_dir} ({d1_slope:+.3f}%)")
            else:
                d1_close = daily_trend.get("close", 0)
                d1_ema = daily_trend.get("ema", 0)
                pos = "위" if d1_close > d1_ema else ("아래" if d1_close < d1_ema else "같음")
                gap_pct = ((d1_close - d1_ema) / d1_ema * 100) if d1_ema else 0
                extra_lines.append(f"1D EMA{period}  ${d1_close:,.2f} {pos} ${d1_ema:,.2f} ({gap_pct:+.2f}%)")

        if orderbook:
            bid = orderbook.get("bid_ratio", 0.5)
            extra_lines.append(f"오더북  매수 {bid*100:.0f}% / 매도 {(1-bid)*100:.0f}%")

        if funding_rate != 0:
            extra_lines.append(f"펀딩   {funding_rate*100:+.4f}%")

        extra = ("\n".join(extra_lines) + "\n") if extra_lines else ""

        msg = (
            f"[{coin}] 1H · {regime_ko}\n"
            f"{SEP}\n"
            f"가격  ${close:,.2f} (EMA {ema_dir} {ema_dist:.2f}%)\n"
            f"RSI   {rsi:.1f}{rsi_tag} · ATR {atr:.2f}% · Vol {vol:.1f}x · BB {bb_pos:.0f}%\n"
            f"{extra}"
            f"{SEP}\n"
        )

        if signal_result:
            dir_ko = _direction_ko(signal_result.direction)
            rr = signal_result.tp_pct / signal_result.sl_pct if signal_result.sl_pct else 0
            msg += (
                f"✅ 진입 · {dir_ko} · 점수 {signal_result.score}/100\n"
                f"SL -{signal_result.sl_pct:.2f}% / TP +{signal_result.tp_pct:.2f}% / RR 1:{rr:.1f}"
            )
        else:
            msg += f"❌ 패스 · {reject_reason}"

        return self.info(msg)

    # ================================================================
    # 포지션 진입
    # ================================================================

    def send_position_opened(self, direction, leverage, entry_price, qty,
                             stop_loss, take_profit, margin_used,
                             strategy="", entry_fee=0, score=0):
        coin_sym = direction.split()[0] if " " in direction else direction
        dir_type = direction.split()[-1] if " " in direction else direction
        dir_ko = _direction_ko(dir_type)

        sl_pct = abs((stop_loss - entry_price) / entry_price * 100)
        tp_pct = abs((take_profit - entry_price) / entry_price * 100)
        rr = tp_pct / sl_pct if sl_pct > 0 else 0

        if "LONG" in dir_type:
            expected_profit = (take_profit - entry_price) * qty
            expected_loss = (entry_price - stop_loss) * qty
        else:
            expected_profit = (entry_price - take_profit) * qty
            expected_loss = (stop_loss - entry_price) * qty

        fee_estimate = entry_price * qty * 0.00055 * 2
        net_profit = expected_profit - fee_estimate
        net_loss = expected_loss + fee_estimate

        profit_pct_m = (net_profit / margin_used * 100) if margin_used > 0 else 0
        loss_pct_m = (net_loss / margin_used * 100) if margin_used > 0 else 0

        return self.trade(
            f"✅ [{coin_sym}] 진입 · {dir_ko} · {leverage}x\n"
            f"{SEP}\n"
            f"전략  {strategy} · 점수 {score:.0f}\n"
            f"진입  ${entry_price:,.2f} · 수량 {qty}\n"
            f"마진  ${margin_used:.2f} · 수수료 ~${fee_estimate:.2f}\n"
            f"{SEP}\n"
            f"TP  ${take_profit:,.2f}  +{tp_pct:.2f}%  →  +${net_profit:.2f} ({_krw(net_profit)}) / 마진 {profit_pct_m:+.1f}%\n"
            f"SL  ${stop_loss:,.2f}  -{sl_pct:.2f}%  →  -${net_loss:.2f} ({_krw(-net_loss)}) / 마진 {loss_pct_m:-.1f}%\n"
            f"RR  1:{rr:.1f}"
        )

    # ================================================================
    # 포지션 청산
    # ================================================================

    def send_position_closed(self, direction, reason, entry_price, exit_price,
                             pnl, pnl_pct, hold_time="", total_fee=0, strategy=""):
        coin_sym = direction.split()[0] if " " in direction else direction
        dir_type = direction.split()[-1] if " " in direction else direction
        dir_ko = _direction_ko(dir_type)

        is_profit = pnl > 0
        result_emoji = "🟢" if is_profit else "🔴"

        label_map = {
            "LIQUIDATION": "강제청산",
            "DEAD_MANS_SWITCH": "긴급청산",
            "TAKE_PROFIT": "익절",
            "TRAILING_STOP": "트레일링 익절" if is_profit else "트레일링 손절",
            "STOP_LOSS": "트레일링 익절" if is_profit else "손절",
            "SERVER_TRIGGERED": "서버 체결",
        }
        label = label_map.get(reason, reason)

        price_change = (exit_price - entry_price) / entry_price * 100
        hold_str = _fmt_hold(hold_time)

        return self.trade(
            f"{result_emoji} [{coin_sym}] 청산 · {label}\n"
            f"{SEP}\n"
            f"방향  {dir_ko} · {strategy} · 보유 {hold_str}\n"
            f"진입 ${entry_price:,.2f}  →  청산 ${exit_price:,.2f} ({price_change:+.2f}%)\n"
            f"수수료  ~${total_fee:.2f}\n"
            f"{SEP}\n"
            f"PnL   {pnl:+.2f} USDT ({_krw(pnl)})\n"
            f"마진  {pnl_pct:+.2f}%"
        )

    # ================================================================
    # 레짐 변경 (하위호환)
    # ================================================================

    def send_regime_change(self, old, new, detail=""):
        body = f"{_regime_ko(old)} → {_regime_ko(new)}"
        if detail:
            body += f"\n{detail}"
        return self.info(
            f"[HERMES] 레짐 변경\n"
            f"{SEP}\n"
            f"{body}"
        )

    # ================================================================
    # 리스크 알림
    # ================================================================

    def send_risk_alert(self, alert_type, detail=""):
        type_map = {
            "TRADE_HALTED": "거래 중단",
            "EMERGENCY_HIGH_VOL": "긴급 고변동",
            "SERVER_CLOSE": "서버 청산 감지",
            "DD_WARNING": "드로다운 경고",
            "SHUTDOWN": "시스템 셧다운",
        }
        title = type_map.get(alert_type, alert_type)

        body = f"{title}"
        if detail:
            body += f"\n{detail}"

        return self.emergency(
            f"🚨 리스크\n"
            f"{SEP}\n"
            f"{body}"
        )

    def send_cooldown_activated(self, reason, minutes):
        return self.info(
            f"⏸ 쿨다운 {minutes}분\n"
            f"{SEP}\n"
            f"{reason}"
        )


telegram_notifier = TelegramNotifier()
