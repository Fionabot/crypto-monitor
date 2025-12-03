import ccxt
import time
from flask import Flask, render_template_string, jsonify
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区域 =================
# 这里是你想要监控的币种，格式必须是大写，中间用 / 隔开
# 为了测试工具是否好用，我加了 'ETH/USDT' 作为参照，你可以随时删除它
TARGET_PAIRS = ['XTER/USDT', 'PAL/USDT']

# 这里是资金警戒线，低于这个金额（USDT）会变红报警
ALERT_THRESHOLD = 2000 
# ===========================================

app = Flask(__name__)

# 定义要查询的交易所（排在前面的会优先显示）
exchange_instances = [
    ccxt.bybit(),   # 放在第一个
    ccxt.bitget(),  # 放在第二个
    ccxt.gateio(),
    ccxt.mexc(),
    ccxt.htx(),
    ccxt.kucoin()
]

# 网页的 HTML 代码（前端页面）
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>深度监控面板</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; }
        .card { border: none; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; overflow: hidden; }
        .card-header { background: #343a40; color: #fff; font-weight: 600; padding: 12px 20px; }
        .table { margin-bottom: 0; }
        .table th { font-size: 0.85rem; color: #6c757d; font-weight: 600; border-top: none; }
        .table td { vertical-align: middle; font-weight: 500; }
        
        /* 深度不足报警色 - 红色 */
        .depth-danger { background-color: #ffebee !important; color: #c62828; font-weight: bold; border: 1px solid #ffcdd2; }
        
        /* 深度健康色 - 绿色 */
        .depth-good { color: #2e7d32; }
        
        .loading-text { text-align: center; color: #888; margin-top: 50px; }
        .price-tag { font-family: 'Courier New', monospace; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h3 class="text-center mb-4">🚀 交易所深度监控 (±2%)</h3>
        <div class="text-center mb-4">
            <span class="badge bg-danger p-2">报警阈值: < {{ threshold }} USDT</span>
            <span class="badge bg-secondary p-2" id="time-badge">等待刷新...</span>
        </div>
        <div id="content-area" class="row">
            <div class="loading-text">正在连接交易所 API，请稍候...</div>
        </div>
    </div>

    <script>
        // 自动刷新逻辑
        async function updateData() {
            try {
                let response = await fetch('/api/data');
                let data = await response.json();
                render(data);
                document.getElementById('time-badge').innerText = '最后更新: ' + new Date().toLocaleTimeString();
            } catch (e) {
                console.log("网络请求错误或等待中...");
            }
        }

        function render(data) {
            const container = document.getElementById('content-area');
            if (data.length === 0) {
                container.innerHTML = '<div class="alert alert-warning text-center">所有交易所均未查询到数据，请检查代币名称是否正确。</div>';
                return;
            }

            container.innerHTML = '';
            // 按币种分组
            let pairs = [...new Set(data.map(item => item.symbol))];

            pairs.forEach(pair => {
                let pairRows = data.filter(d => d.symbol === pair);
                
                // 开始构建卡片 HTML
                let html = `
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header d-flex justify-content-between">
                            <span>${pair}</span>
                        </div>
                        <div class="card-body p-0">
                            <table class="table table-striped text-center">
                                <thead>
                                    <tr>
                                        <th>交易所</th>
                                        <th>价格</th>
                                        <th>-2% 买盘厚度</th>
                                        <th>+2% 卖盘厚度</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                pairRows.forEach(row => {
                    // 如果交易所没上这个币，直接跳过不显示
                    if (row.status === 'Not Listed') return;

                    // 判断是否需要红色高亮
                    let bidClass = (row.bid_depth < {{ threshold }}) ? 'depth-danger' : 'depth-good';
                    let askClass = (row.ask_depth < {{ threshold }}) ? 'depth-danger' : 'depth-good';
                    
                    let priceDisplay = row.price ? '$' + row.price : '-';
                    let bidDisplay = row.bid_depth ? parseInt(row.bid_depth).toLocaleString() : '0';
                    let askDisplay = row.ask_depth ? parseInt(row.ask_depth).toLocaleString() : '0';

                    if(row.status === 'Error') {
                         html += `<tr><td>${row.exchange}</td><td colspan="3" class="text-muted">请求超时/受限</td></tr>`;
                    } else {
                        html += `
                        <tr>
                            <td>${row.exchange}</td>
                            <td class="price-tag">${priceDisplay}</td>
                            <td class="${bidClass}">${bidDisplay}</td>
                            <td class="${askClass}">${askDisplay}</td>
                        </tr>`;
                    }
                });

                html += `</tbody></table></div></div></div>`;
                container.innerHTML += html;
            });
        }

        // 启动时运行一次，然后每 4 秒刷新一次
        updateData();
        setInterval(updateData, 4000);
    </script>
</body>
</html>
"""

def calculate_depth(orderbook, price):
    if not orderbook or not price: return 0, 0
    
    # 2% 的价格范围
    limit_down = price * 0.98
    limit_up = price * 1.02
    
    bid_sum = 0
    # 统计买单 (只要价格大于 limit_down 的都算有效支撑)
    for p, amount in orderbook['bids']:
        if p >= limit_down:
            bid_sum += p * amount
        else:
            break
            
    ask_sum = 0
    # 统计卖单 (只要价格小于 limit_up 的都算有效压盘)
    for p, amount in orderbook['asks']:
        if p <= limit_up:
            ask_sum += p * amount
        else:
            break
            
    return bid_sum, ask_sum

def fetch_one_exchange(exchange):
    """ 去一个交易所查所有币种 """
    results = []
    ex_name = exchange.id.upper()
    
    try:
        exchange.load_markets() # 加载市场列表
    except:
        return results # 如果连不上交易所，直接返回空

    for symbol in TARGET_PAIRS:
        item = {'exchange': ex_name, 'symbol': symbol, 'status': 'Not Listed', 'price':0, 'bid_depth':0, 'ask_depth':0}
        
        if symbol in exchange.markets:
            try:
                ticker = exchange.fetch_ticker(symbol)
                price = ticker['last']
                # 获取深度数据
                orderbook = exchange.fetch_order_book(symbol, limit=200)
                
                bid_val, ask_val = calculate_depth(orderbook, price)
                
                item['price'] = price
                item['bid_depth'] = bid_val
                item['ask_depth'] = ask_val
                item['status'] = 'Active'
            except:
                item['status'] = 'Error' # 网络超时或API限制
        
        results.append(item)
    return results

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, threshold=ALERT_THRESHOLD)

@app.route('/api/data')
def get_data():
    final_data = []
    # 使用多线程同时查 5 个交易所，速度更快
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_one_exchange, ex) for ex in exchange_instances]
        for f in futures:
            final_data.extend(f.result())
    return jsonify(final_data)

if __name__ == '__main__':
    print("---------------------------------------------------")
    print("程序正在启动... 请在浏览器输入: http://127.0.0.1:5000")
    print("---------------------------------------------------")
    app.run(debug=True, port=5000)