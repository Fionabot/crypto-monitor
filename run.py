import ccxt
import time
from flask import Flask, render_template_string, jsonify
from concurrent.futures import ThreadPoolExecutor

# ================= 配置区域 =================
TARGET_PAIRS = ['XTER/USDT', 'PALIO/USDT']
ALERT_THRESHOLD = 2000 
# ===========================================

app = Flask(__name__)

# 配置交易所：设置5秒超时，防止一直卡着
common_config = {
    'timeout': 5000,  # 5000毫秒 = 5秒
    'enableRateLimit': True
}

exchange_instances = [
    ccxt.bybit(common_config),
    ccxt.bitget(common_config),
    ccxt.bithumb(common_config),
    ccxt.gateio(common_config),
    ccxt.mexc(common_config),
    ccxt.kraken(common_config),
    ccxt.lbank(common_config),
    ccxt.htx(common_config)
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
        .card { border: none; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px; overflow: hidden; }
        
        /* 标题栏更简洁 */
        .card-header { background: #2c3e50; color: #fff; padding: 15px 20px; font-weight: 600; font-size: 1.1rem; }
        
        /* 底部汇总栏样式 */
        .card-footer { background-color: #f8f9fa; border-top: 1px solid #eee; padding: 15px; }
        .total-stat-box { font-size: 1rem; font-weight: bold; padding: 5px 15px; border-radius: 6px; }
        .total-bid { color: #2e7d32; background: #e8f5e9; border: 1px solid #c8e6c9; }
        .total-ask { color: #c62828; background: #ffebee; border: 1px solid #ffcdd2; }

        .depth-danger { background-color: #ffebee !important; color: #c62828; font-weight: bold; }
        .depth-good { color: #2e7d32; }
        .spread-high { color: #d32f2f; font-weight: bold; }
        .spread-low { color: #388e3c; }
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
            <div class="loading-text">
                <div class="spinner-border text-primary" role="status"></div>
                <div class="mt-2">正在努力连接交易所 (超时限制 120秒)...</div>
            </div>
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
                
                // 计算总和
                let totalBid = 0;
                let totalAsk = 0;
                pairRows.forEach(r => {
                    if (r.status === 'Active') {
                        totalBid += r.bid_depth;
                        totalAsk += r.ask_depth;
                    }
                });
                
                const formatNum = (num) => num > 1000000 ? (num/1000000).toFixed(2)+'M' : (num/1000).toFixed(1)+'K';

                // 构建 HTML
                let html = `
                <div class="col-md-12">
                    <div class="card">
                        <!-- 标题栏：只放币种名称 -->
                        <div class="card-header">
                            <span>🪙 ${pair}</span>
                        </div>
                        
                        <!-- 表格区域 -->
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
                    let bidClass = (row.bid_depth < {{ threshold }}) ? 'depth-danger' : 'depth-good';
                    let askClass = (row.ask_depth < {{ threshold }}) ? 'depth-danger' : 'depth-good';
                    let spreadVal = parseFloat(row.spread);
                    let spreadClass = (spreadVal > 0.5) ? 'spread-high' : 'spread-low';
                    let spreadDisplay = row.spread === '-' ? '-' : row.spread + '%';

                    if(row.status === 'Error') {
                         html += `<tr><td>${row.exchange}</td><td colspan="4" class="text-muted">连接超时 (5s)</td></tr>`;
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

                // --- 变化在这里：添加页脚汇总区域 ---
                html += `
                                </tbody>
                            </table>
                        </div>
                        <div class="card-footer">
                            <div class="d-flex justify-content-around text-center">
                                <span class="total-stat-box total-bid">📉 全网总买盘: $${f