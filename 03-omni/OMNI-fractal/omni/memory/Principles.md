### OMNI Trading System - Trading Principles (Ver 5.0 - Genesis)

### FIXED SECTION (DO NOT MODIFY)

#### System Architecture (How OMNI Operates)
1.  **Phase 1 (Scan):** Scan market for high-potential candidates based on Dynamic Rules.
2.  **Phase 2 (Select):** Deep-dive on candidates to select the single best coin.
3.  **Phase 3 (Strategize):** Formulate a precise entry, target, and stop-loss plan.
4.  **Phase 4 (Execute):** Place orders and monitor the trade automatically.
5.  **Phase 5 (Evolve):** Analyze the result and update the Dynamic Rules.
**※ BTC market condition is the highest priority variable.**

#### Core System Constraints
* **Single Entry/Exit:** One entry, one target, one stop per trade.
* **No Manual Intervention:** Fully autonomous once initiated.
* **All-In, All-Out:** No partial profit taking.
* **No Averaging Down:** No adding to losing positions.
* **Sequential:** One trade at a time.

---

### DYNAMIC SECTION (Continuously updated by the AI)

#### Market State Analysis
* **Overheat Filter:** If a coin's 1h volume > 200% of average, avoid entry (pump & dump risk).
* **BTC Weakness Filter:** If BTC 1h change < -0.5%, pause new long entries.

#### Position Sizing
* **Market Trend Multiplier:** BULL: 100%, SIDEWAYS: 60%, BEAR: 30% of base position size.

#### Core Strategy: DOs & DON'Ts

##### DO THIS: Only Enter in These Situations
1.  **Energy Condensation (Pre-Breakout):** Find coins in a tight, low-volatility consolidation range on the 4H chart. This is the primary signal to look for.
2.  **Stealth Accumulation:** Within that range, look for signs of quiet buying (e.g., rising On-Balance Volume (OBV) while price is flat).
3.  **Seller Exhaustion (Reversal):** Look for signs that sellers are losing power at a key support level (e.g., Bullish Divergence on RSI).

##### DON'T DO THIS: Absolutely Avoid These Situations
1.  **Chasing Pumps:** Never buy a coin that has already broken out and is moving fast. We enter BEFORE the pump, not during.
2.  **Fighting the Trend:** Do not try to catch a free-falling coin. Wait for it to form a clear base (consolidation).
3.  **Unconfirmed Moves:** Ignore any price action not backed by evidence of accumulation or seller exhaustion.

#### Exit Rules
* **Stop-Loss:** Place stop slightly below the identified consolidation range or confirmed support level.
* **Take-Profit:** Aim for a high Risk:Reward ratio (minimum 1:3), targeting a major resistance level.
* **Early Exit (Failure):** If a coin breaks out of consolidation but fails to gain momentum and falls back into the range, exit immediately at breakeven.

#### Quick Decision Checklist
* □ **Pre-Breakout Signal:** Does the coin show clear signs of energy condensation (e.g., BB Squeeze)? (If NO → CANCEL)
* □ **Accumulation Evidence:** Is there evidence of smart money accumulating (e.g., rising OBV)? (If NO → CANCEL)
* □ **High R:R Setup:** Is the Risk:Reward ratio at least 1:3 with a clear stop-loss? (If NO → CANCEL)
* □ **BTC Filter:** Is BTC stable or rising? (If NO → CANCEL)

**Only when all checks are passed, execute the trade with the calculated position size.**