# Trading Session Audit Report: `session_20261116_014905_817_b562`

- **Session ID**: `session_20261116_014905_817_b562`
- **Target Asset**: `xyz:SKHX-PERP`
- **Network**: Hyperliquid `Mainnet`
- **Execution Mode**: REAL EXCHANGE ORDERS (LIVE)
- **Session Start**: 2026-11-16T01:49:05
- **Session End**: 2026-11-16 11:52:58
- **Duration**: 603m 52s (36232.8s)
- **Master CSV**: [`all_trades.csv`](all_trades.csv)
- **Detailed Event Stream**: [`trades_audit.jsonl`](trades_audit.jsonl)

---

## 1. Real On-Chain Hyperliquid Execution (Exchange Reconciled)

> [!IMPORTANT]
> The figures below represent **actual on-chain fills and cash settlements** verified directly against the Hyperliquid clearinghouse API for this trading session.

| Metric | Real Value (Exchange Settled) |
| :--- | :---: |
| **Total Real Fills** | 6 (0 Maker / 6 Taker) |
| **Real Executed Volume** | 1.3880 xyz:SKHX |
| **Real Closed PnL** | $-0.8654 USDC |
| **Real Fees Paid to Hyperliquid** | $0.1053 USDC |
| **Real Net Realized PnL** | **-$0.9708 USDC** |
| **On-Chain Fills CSV** | [`live_exchange_fills.csv`](live_exchange_fills.csv) |

---

## 2. Theoretical Paper-Simulation Benchmark

| Strategy | Trades | Win Rate | Volume (XYZ:SKHX) | Net Fees/Reb ($) | Net PnL ($) | Return (bps) | Profit Factor | Strategy Audit File |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Convexity_Cascade** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv) |
| **Hedged_Convexity** | 1 | 0.0% | 0.2200 | -$0.03 | **$-0.31** | -16.6 bps | 0.00 | [`Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv) |
| **Momentum_Expansion** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv) |
| **Queue_Replenishment** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Queue_Replenishment.csv`](strategies/Queue_Replenishment.csv) |
| **Stock_Microstructure_Alpha** | 0 | 0.0% | 0.0000 | +$0.00 | **+$0.00** | +0.0 bps | 0.00 | [`Stock_Microstructure_Alpha.csv`](strategies/Stock_Microstructure_Alpha.csv) |

---

## 2. Individual Trade Logs per Strategy

### Strategy: `Convexity_Cascade`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Convexity_Cascade.csv`](strategies/Convexity_Cascade.csv)

_No trades were opened/closed for Convexity_Cascade during this session._

### Strategy: `Hedged_Convexity`

- **Total Executed Trades**: 1 | **Wins**: 0 | **Losses**: 1 | **Win Rate**: 0.0% | **Net PnL**: $-0.31
- **Audit CSV**: [`strategies/Hedged_Convexity.csv`](strategies/Hedged_Convexity.csv)

| # | Trade ID | Side | Size (XYZ:SKHX) | Entry Time | Entry Px | Exit Time | Exit Px | Hold (s) | Exit Reason | Fees ($) | Net PnL ($) | Return (bps) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `HC-0001` | SHORT | 0.2200 | 05:15:04 | $842.7 | 05:15:36 | $843.9 | 31.8s | `REALTIME_WS_FILL` | -$0.03 | **-$0.31** | -16.6 bps |

### Strategy: `Momentum_Expansion`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Momentum_Expansion.csv`](strategies/Momentum_Expansion.csv)

_No trades were opened/closed for Momentum_Expansion during this session._

### Strategy: `Queue_Replenishment`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Queue_Replenishment.csv`](strategies/Queue_Replenishment.csv)

_No trades were opened/closed for Queue_Replenishment during this session._

### Strategy: `Stock_Microstructure_Alpha`

- **Total Executed Trades**: 0 | **Wins**: 0 | **Losses**: 0 | **Win Rate**: 0.0% | **Net PnL**: $+0.00
- **Audit CSV**: [`strategies/Stock_Microstructure_Alpha.csv`](strategies/Stock_Microstructure_Alpha.csv)

_No trades were opened/closed for Stock_Microstructure_Alpha during this session._


---

## 3. Real Exchange Order Audit Log (Hyperliquid API)

| Event ID | Time | Event | Side | Size (XYZ:SKHX) | Price | TIF | OID | Status | Signal Score | Error |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `EVT-0001` | 05:15:01 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0002` | 05:15:05 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0003` | 05:15:06 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0004` | 05:15:07 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0005` | 05:15:08 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0006` | 05:15:09 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0007` | 05:15:10 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0008` | 05:15:11 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0009` | 05:15:12 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0010` | 05:15:12 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0011` | 05:15:13 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0012` | 05:15:14 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0013` | 05:15:15 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0014` | 05:15:16 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0015` | 05:15:17 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0016` | 05:15:18 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0017` | 05:15:19 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0018` | 05:15:20 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0019` | 05:15:21 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0020` | 05:15:22 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0021` | 05:15:23 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0022` | 05:15:24 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0023` | 05:15:25 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0024` | 05:15:26 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0025` | 05:15:27 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0026` | 05:15:28 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0027` | 05:15:29 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0028` | 05:15:30 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0029` | 05:15:31 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0030` | 05:15:32 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0031` | 05:15:32 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0032` | 05:15:33 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0033` | 05:15:34 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.889 | Insufficient margin to place order. asset=110022 |
| `EVT-0034` | 05:15:35 | **REJECTED** | SELL | 0.2370 | $842.5 | `Ioc` | - | `rejected` | -0.883 | Insufficient margin to place order. asset=110022 |
| `EVT-0035` | 05:15:37 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.184 | - |
| `EVT-0036` | 05:15:37 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.184 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0037` | 05:15:40 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.183 | - |
| `EVT-0038` | 05:15:40 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.183 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0039` | 05:15:41 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `606693323252` | `ok` | +0.000 | - |
| `EVT-0040` | 05:15:42 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.183 | - |
| `EVT-0041` | 05:15:43 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.183 | Reduce only order would increase position. asset=110022 |
| `EVT-0042` | 05:15:48 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.182 | - |
| `EVT-0043` | 05:15:49 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.182 | Reduce only order would increase position. asset=110022 |
| `EVT-0044` | 05:15:54 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.188 | - |
| `EVT-0045` | 05:15:54 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.188 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0046` | 05:15:59 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.187 | - |
| `EVT-0047` | 05:15:59 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.187 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0048` | 05:16:05 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.188 | - |
| `EVT-0049` | 05:16:05 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.188 | Reduce only order would increase position. asset=110022 |
| `EVT-0050` | 05:16:11 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.188 | - |
| `EVT-0051` | 05:16:11 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.188 | Reduce only order would increase position. asset=110022 |
| `EVT-0052` | 05:16:14 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `606693323252` | `ok` | +0.000 | - |
| `EVT-0053` | 05:16:15 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.002 | - |
| `EVT-0054` | 05:16:15 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.002 | Reduce only order would increase position. asset=110022 |
| `EVT-0055` | 05:16:19 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.001 | - |
| `EVT-0056` | 05:16:19 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.001 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0057` | 05:16:25 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.002 | - |
| `EVT-0058` | 05:16:26 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.002 | Reduce only order would increase position. asset=110022 |
| `EVT-0059` | 05:16:30 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | +0.005 | - |
| `EVT-0060` | 05:16:31 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | +0.005 | Reduce only order would increase position. asset=110022 |
| `EVT-0061` | 05:16:36 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | +0.003 | - |
| `EVT-0062` | 05:16:36 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | +0.003 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0063` | 05:16:42 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | +0.008 | - |
| `EVT-0064` | 05:16:42 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | +0.008 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0065` | 05:16:45 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `606693323252` | `ok` | +0.000 | - |
| `EVT-0066` | 05:16:46 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | +0.005 | - |
| `EVT-0067` | 05:16:46 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | +0.005 | Reduce only order would increase position. asset=110022 |
| `EVT-0068` | 05:16:50 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | +0.007 | - |
| `EVT-0069` | 05:16:50 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | +0.007 | Reduce only order would increase position. asset=110022 |
| `EVT-0070` | 05:16:56 | **SUBMIT** | BUY | 0.6940 | $843.4 | `Ioc` | - | `submitting` | -0.047 | - |
| `EVT-0071` | 05:16:56 | **REJECTED** | BUY | 0.6940 | $843.4 | `Ioc` | - | `rejected` | -0.047 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0072` | 05:16:57 | **ERROR** | BUY | 0.6940 | $843.6 | `Ioc` | - | `exception` | -0.393 | (429, None, 'null', None, {'Content-Type': 'application/json', 'Content-Length': '4', 'Connection': 'keep-alive', 'Server': 'nginx/1.30.3', 'Date': 'Mon, 16 Nov 2026 05:16:57 GMT', 'access-control-expose-headers': '*', 'access-control-allow-origin': '*', 'vary': 'origin, access-control-request-method, access-control-request-headers', 'X-Cache': 'Error from cloudfront', 'Via': '1.1 0448444ece782fee77bace5748242ab6.cloudfront.net (CloudFront)', 'X-Amz-Cf-Pop': 'LHR5-P5', 'X-Amz-Cf-Id': 'lztn3GXGyHLi-unz5a_d4GW0Dpx0u_9Uuhg3he2swEe24lYRD8R72g=='}) |
| `EVT-0073` | 05:16:58 | **ERROR** | BUY | 0.6940 | $843.6 | `Ioc` | - | `exception` | -0.443 | (429, None, 'null', None, {'Content-Type': 'application/json', 'Content-Length': '4', 'Connection': 'keep-alive', 'Server': 'nginx/1.30.3', 'Date': 'Mon, 16 Nov 2026 05:16:58 GMT', 'access-control-expose-headers': '*', 'access-control-allow-origin': '*', 'vary': 'origin, access-control-request-method, access-control-request-headers', 'X-Cache': 'Error from cloudfront', 'Via': '1.1 0448444ece782fee77bace5748242ab6.cloudfront.net (CloudFront)', 'X-Amz-Cf-Pop': 'LHR5-P5', 'X-Amz-Cf-Id': 'VMoSiVstU48WiF7008GowIc_pFLxbvgO3dxkrJBwB-8uwuKwMCX3gQ=='}) |
| `EVT-0074` | 05:16:59 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.442 | - |
| `EVT-0075` | 05:16:59 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.442 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0076` | 05:17:00 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `606693323252` | `ok` | +0.000 | - |
| `EVT-0077` | 05:17:01 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.442 | - |
| `EVT-0078` | 05:17:01 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.442 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0079` | 05:17:03 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.442 | - |
| `EVT-0080` | 05:17:03 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.442 | Reduce only order would increase position. asset=110022 |
| `EVT-0081` | 05:17:04 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.463 | - |
| `EVT-0082` | 05:17:05 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.463 | Reduce only order would increase position. asset=110022 |
| `EVT-0083` | 05:17:06 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.474 | - |
| `EVT-0084` | 05:17:06 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.474 | Reduce only order would increase position. asset=110022 |
| `EVT-0085` | 05:17:08 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.474 | - |
| `EVT-0086` | 05:17:08 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.474 | Reduce only order would increase position. asset=110022 |
| `EVT-0087` | 05:17:09 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.476 | - |
| `EVT-0088` | 05:17:10 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.476 | Reduce only order would increase position. asset=110022 |
| `EVT-0089` | 05:17:11 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `606693323252` | `ok` | +0.000 | - |
| `EVT-0090` | 05:17:12 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.474 | - |
| `EVT-0091` | 05:17:13 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.474 | Reduce only order would increase position. asset=110022 |
| `EVT-0092` | 05:17:14 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.474 | - |
| `EVT-0093` | 05:17:14 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.474 | Reduce only order would increase position. asset=110022 |
| `EVT-0094` | 05:17:15 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.471 | - |
| `EVT-0095` | 05:17:15 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.471 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0096` | 05:17:17 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.472 | - |
| `EVT-0097` | 05:17:17 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.472 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0098` | 05:17:18 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.472 | - |
| `EVT-0099` | 05:17:18 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.472 | Reduce only order would increase position. asset=110022 |
| `EVT-0100` | 05:17:19 | **SUBMIT** | BUY | 0.6940 | $843.6 | `Ioc` | - | `submitting` | -0.473 | - |
| `EVT-0101` | 05:17:20 | **REJECTED** | BUY | 0.6940 | $843.6 | `Ioc` | - | `rejected` | -0.473 | Reduce only order would increase position. asset=110022 |
| `EVT-0102` | 05:17:21 | **SUBMIT** | BUY | 0.6940 | $844.0 | `Ioc` | - | `submitting` | -0.389 | - |
| `EVT-0103` | 05:17:22 | **REJECTED** | BUY | 0.6940 | $844.0 | `Ioc` | - | `rejected` | -0.389 | Reduce only order would increase position. asset=110022 |
| `EVT-0104` | 05:17:23 | **CANCEL** | UNKNOWN | 0.0000 | $0.0 | `Alo` | `606693323252` | `ok` | +0.000 | - |
| `EVT-0105` | 05:17:24 | **SUBMIT** | BUY | 0.6940 | $844.0 | `Ioc` | - | `submitting` | -0.389 | - |
| `EVT-0106` | 05:17:24 | **REJECTED** | BUY | 0.6940 | $844.0 | `Ioc` | - | `rejected` | -0.389 | Order could not immediately match against any resting orders. asset=110022 |
| `EVT-0107` | 05:17:25 | **SUBMIT** | BUY | 0.6940 | $844.0 | `Ioc` | - | `submitting` | -0.385 | - |
| `EVT-0108` | 05:17:25 | **REJECTED** | BUY | 0.6940 | $844.0 | `Ioc` | - | `rejected` | -0.385 | Order could not immediately match against any resting orders. asset=110022 |

