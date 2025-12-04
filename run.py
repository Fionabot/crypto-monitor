import ccxt
import time
from flask import Flask, render_template_string, jsonify
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区域 =================
TARGET_PAIRS = ['XTER/USDT', 'PALIO/USDT']

# 深度报警阈值 (USDT)
ALERT_THRESHOLD = 2000 
# ===========================================

app = Flask(__name__)

# 定义交易所列表 (已移除 KuCoin 以提升稳定性)
# 顺序：Bybit -> Bitget -> Gate -> MEXC -> HTX
exchange_instances = [
    ccxt.bybit(),
    ccxt.bitget(),
    ccxt.bithumb(),
    ccxt.gateio(),
    ccxt.mexc(),
    ccxt.kraken(),
    ccxt.lbank(),
    ccxt.htx()
]

# 网页前端代码
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>全网深度 & 价差监控</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', Roboto, sans-serif; padding: 20px; }
        .card { border: none; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 25px; overflow: hidden; }
        
        /* 标题栏样式 */
        .card-header { 
            background: #2c3e50; 
            color: #fff; 
            padding: 15px 20px;
        }
        .header-stats {
            font-size: 0.9rem;
            background: rgba(255,255,255,0.1);
            padding: 5px 10px;
            border-radius: 5px;
            margin-left: 10px;
        }
        
        .table th { font-size: 0.85rem; color: #6c757d; border-top: none; }
        .table td { vertical-align: middle; font-weight: 500; font-size: 0.95rem; }
        
        /* 深度报警 - 红色 */
        .depth-danger { background-color: #ffebee !important; color: #c62828; font-weight: bold; }
        /* 深度健康 - 绿色 */
        .depth-good { color: #2e7d32; }

        /* 价差样式 */
        .spread-high { color: #d32f2f; font-weight: bold; } /* 价差过大 */
        .spread-low { color: #388e3c; } /* 价差优秀 */
        
        .loading-text { text-align: center; color: #888; margin-top: 50px; }
        .price-tag { font-family: 'Courier New', monospace; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h3 class="text-center mb-4">🚀 全网流动性监控面板</h3>
        <div class="text-center mb-4">
            <span class="badge bg-danger p-2">单所深度报警: < {{ threshold }} USDT</span>
            <span class="badge bg-secondary p-2" id="time-badge">连接中...</span>
        </div>
        <div id="content-area" class="row">
            <div class="loading-text">正在从各个交易所抓取数据...<br>Bybit, Bitget, Gate, MEXC, HTX</div>
        </div>
    </div>

    <script>
        async function updateData() {
            try {
                let response = await fetch('/api/data');
                let data = await response.json();
                render(data);
                document.getElementById('time-badge').innerText = '更新时间: ' + new Date().toLocaleTimeString();
            } catch (e) {
                console.log("等待数据...");
            }
        }

        function render(data) {
            const container = document.getElementById('content-area');
            if (!data || data.length === 0) return;

            container.innerHTML = '';
            let pairs = [...new Set(data.map(item => item.symbol))];

            pairs.forEach(pair => {
                let pairRows = data.filter(d => d.symbol === pair);
                
                // --- 新功能 1：计算全网总深度 ---
                let totalBid = 0;
                let totalAsk = 0;
                pairRows.forEach(r => {
                    if (r.status === 'Active') {
                        totalBid += r.bid_depth;
                        totalAsk += r.ask_depth;
                    }
                });
                
                // 格式化数字 K/M
                const formatNum = (num) => num > 1000000 ? (num/1000000).toFixed(2)+'M' : (num/1000).toFixed(1)+'K';

                let html = `
                <div class="col-md-12">
                    <div class="card">
                        <div class="card-header d-flex justify-content-between align-items-center flex-wrap">
                            <span class="h5 mb-0">🪙 ${pair}</span>
                            <div class="d-flex gap-2">
                                <span class="header-stats">📉 总买盘支撑: $${formatNum(totalBid)}</span>
                                <span class="header-stats">📈 总卖盘压力: $${formatNum(totalAsk)}</span>
                            </div>
                        </div>
                        <div class="card-body p-0">
                            <table class="table table-striped text-center mb-0">
                                <thead class="table-light">
                                    <tr>
                                        <th>交易所</th>
                                        <th>最新价格</th>
                                        <th>价差 (Spread)</th>
                                        <th>-2% 买盘 (USDT)</th>
                                        <th>+2% 卖盘 (USDT)</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                pairRows.forEach(row => {
                    if (row.status === 'Not Listed') return;

                    // 深度颜色判断
                    let bidClass = (row.bid_depth < {{ threshold }}) ? 'depth-danger' : 'depth-good';
                    let askClass = (row.ask_depth < {{ threshold }}) ? 'depth-danger' : 'depth-good';
                    
                    // --- 新功能 2：价差颜色判断 ---
                    // 如果价差超过 0.5% 标红，否则标绿
                    let spreadVal = parseFloat(row.spread);
                    let spreadClass = (spreadVal > 0.5) ? 'spread-high' : 'spread-low';
                    let spreadDisplay = row.spread === '-' ? '-' : row.spread + '%';

                    if(row.status === 'Error') {
                         html += `<tr><td>${row.exchange}</td><td colspan="4" class="text-muted">请求超时 (API限制)</td></tr>`;
                    } else {
                        html += `
                        <tr>
                            <td class="fw-bold">${row.exchange}</td>
                            <td class="price-tag">$${row.price}</td>
                            <td class="${spreadClass}">${spreadDisplay}</td>
                            <td class="${bidClass}">${parseInt(row.bid_depth).toLocaleString()}</td>
                            <td class="${askClass}">${parseInt(row.ask_depth).toLocaleString()}</td>
                        </tr>`;
                    }
                });

                html += `</tbody></table></div></div></div>`;
                container.innerHTML += html;
            });
        }

        updateData();
        setInterval(updateData, 4000);
    </script>
</body>
</html>
"""

def calculate_metrics(exchange, symbol, orderbook, ticker):
    """ 计算深度和价差 """
    if not orderbook or not ticker:
        return 0, 0, '-'

    price = ticker['last']
    if not price: return 0, 0, '-'

    # 1. 计算深度
    limit_down = price * 0.98
    limit_up = price * 1.02
    
    bid_sum = 0
    for p, amount in orderbook['bids']:
        if p >= limit_down: bid_sum += p * amount
        else: break
            
    ask_sum = 0
    for p, amount in orderbook['asks']:
        if p <= limit_up: ask_sum += p * amount
        else: break

    # 2. 计算价差 (Spread)
    # spread % = (ask - bid) / ask * 100
    spread_str = '-'
    try:
        best_bid = ticker['bid']
        best_ask = ticker['ask']
        if best_bid and best_ask and best_ask > 0:
            spread = ((best_ask - best_bid) / best_ask) * 100
            spread_str = "{:.2f}".format(spread)
    except:
        pass

    return bid_sum, ask_sum, spread_str

def fetch_one_exchange(exchange):
    results = []
    ex_name = exchange.id.upper()
    
    try:
        exchange.load_markets()
    except:
        return results

    for symbol in TARGET_PAIRS:
        item = {
            'exchange': ex_name, 
            'symbol': symbol, 
            'status': 'Not Listed', 
            'price': 0, 
            'bid_depth': 0, 
            'ask_depth': 0,
            'spread': '-'
        }
        
        if symbol in exchange.markets:
            try:
                # 同时获取 Ticker (为了算价差) 和 OrderBook
                ticker = exchange.fetch_ticker(symbol)
                orderbook = exchange.fetch_order_book(symbol, limit=200)
                
                bid_val, ask_val, spread_val = calculate_metrics(exchange, symbol, orderbook, ticker)
                
                item['price'] = ticker['last']
                item['bid_depth'] = bid_val
                item['ask_depth'] = ask_val
                item['spread'] = spread_val
                item['status'] = 'Active'
            except Exception as e:
                # print(f"Error {ex_name}: {e}") # 调试用
                item['status'] = 'Error'
        
        results.append(item)
    return results

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, threshold=ALERT_THRESHOLD)

@app.route('/api/data')
def get_data():
    final_data = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_one_exchange, ex) for ex in exchange_instances]
        for f in futures:
            final_data.extend(f.result())
    return jsonify(final_data)

if __name__ == '__main__':
    # 允许所有IP访问
    app.run(debug=True, port=5000, host='0.0.0.0')