#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
春华秋实 · ETF四季分批战法（国内版）—— 每日自动更新生成器

数据源：新浪财经日K线（250日），纯标准库，无需第三方包
标的池：pool.csv（43支纯国内ETF，已剔除纳指/标普/德/法/日）
输出  ：index.html（引流展示站）、data.csv（当日快照）

三因子口径（写死在本脚本，公开可复核）：
  M 动量  = 近20个交易日收益率(%)
  V 估值  = 250日价格区间位置分位 (close-min)/(max-min)*100，越低越便宜
  F 风控  = 收盘价>MA60 且 MA20>MA60 → 通过（趋势向上才允许播种/摘果）
  综合分  = 0.4*M分 + 0.3*V分 + 0.3*F分
            M分 = clamp(50 + M*2.5, 0, 100)
            V分 = 100 - V（越低越便宜，分越高）
            F分 = 100/0
四季归类：
  风控❌           → 冬（休耕）
  风控✅ + V<50%   → 春（播种·估值低）
  风控✅ + 50%≤V<90% → 秋（摘果·高估值）
  风控✅ + V≥90%   → 秋（摘果·极高）
"""
import os
import re
import ssl
import csv
import sys
import json
import time
import datetime
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
POOL_CSV = os.path.join(HERE, "pool.csv")
DATA_CSV = os.path.join(HERE, "data.csv")
OUT_HTML = os.path.join(HERE, "index.html")

HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}


def fetch_kline(symbol, datalen=250, retry=2):
    """新浪日K线，返回升序 close 列表"""
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "CN_MarketData.getKLineData?symbol=%s&scale=240&ma=no&datalen=%d"
           % (symbol, datalen))
    for attempt in range(retry + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                raw = resp.read().decode("gbk", errors="ignore")
            data = json.loads(raw)
            if not data:
                return [], []
            rows = [(d["day"], float(d["close"])) for d in data]
            rows.sort(key=lambda x: x[0])
            return [r[0] for r in rows], [r[1] for r in rows]
        except Exception as e:
            last = e
            time.sleep(1.0 + attempt)
    print("    [K线] %s 失败: %s" % (symbol, repr(last)[:100]))
    return [], []


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def analyze(code, name):
    days, closes = fetch_kline(code)
    if len(closes) < 65:
        return {"代码": code, "名称": name, "季节": "冬", "综合分": "", "动量M": "",
                "估值分位": "", "风控": "❌数据不足", "操作": "休耕", "日期": "",
                "_ok": False}
    close = closes[-1]
    lo, hi = min(closes), max(closes)
    v = (close - lo) / (hi - lo) * 100 if hi > lo else 50.0
    m = (close - closes[-21]) / closes[-21] * 100 if len(closes) > 21 else 0.0
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    passed = (close > ma60) and (ma20 > ma60)

    m_score = clamp(50 + m * 2.5, 0, 100)
    v_score = 100 - v
    f_score = 100.0 if passed else 0.0
    total = 0.4 * m_score + 0.3 * v_score + 0.3 * f_score

    if not passed:
        season, act = "冬", "休耕"
    elif v < 50:
        season, act = "春", "★播种·估值低"
    elif v >= 90:
        season, act = "秋", "★摘果·极高"
    else:
        season, act = "秋", "★摘果·高估值"

    return {"代码": code, "名称": name, "季节": season, "综合分": "%.2f" % total,
            "动量M": "%.2f" % m, "估值分位": "%.1f%%" % v,
            "风控": "✅通过" if passed else "❌未过", "操作": act,
            "日期": days[-1], "_ok": True}


def load_pool():
    rows = list(csv.DictReader(open(POOL_CSV, encoding="utf-8-sig")))
    return [(r["代码"].strip(), r["名称"].strip()) for r in rows if r["代码"].strip()]


def load_prev_season():
    """读上次快照的 季节 映射，用于算"今日变化" """
    prev = {}
    if not os.path.exists(DATA_CSV):
        return prev
    try:
        for r in csv.DictReader(open(DATA_CSV, encoding="utf-8-sig")):
            prev[r["代码"]] = r["季节"]
    except Exception:
        pass
    return prev


TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🌸 春华秋实 · ETF四季分批战法（国内版）｜ 老王ETF实战工具箱</title>
<meta name="description" content="只做国内43支ETF的四季分批战法：春播种·夏浇灌·秋摘果·冬休耕，三因子信号每日自动更新。">
<style>
:root{
  --bg:#0d1117; --card:#161b22; --line:#30363d; --txt:#e6edf3; --sub:#9da7b3;
  --red:#e5484d; --green:#3fb950; --gold:#d4a017; --blue:#388bfd;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--txt);line-height:1.7;padding:0 16px}
.wrap{max-width:960px;margin:0 auto;padding:40px 0}
header.hero{text-align:center;padding:32px 0 24px;border-bottom:1px solid var(--line)}
.hero h1{font-size:30px;letter-spacing:1px}
.hero .tag{color:var(--gold);font-size:15px;margin-top:8px}
.hero .sub{color:var(--sub);font-size:14px;margin-top:10px;max-width:680px;margin-left:auto;margin-right:auto}
.badges{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:16px}
.badge{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 14px;font-size:12px;color:var(--sub)}
.badge b{color:var(--txt)}
.live{display:inline-flex;align-items:center;gap:6px;background:rgba(63,185,80,.12);color:var(--green);border:1px solid rgba(63,185,80,.35);border-radius:999px;padding:4px 14px;font-size:12px;margin-top:14px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 0 rgba(63,185,80,.7);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(63,185,80,.6)}70%{box-shadow:0 0 0 8px rgba(63,185,80,0)}100%{box-shadow:0 0 0 0 rgba(63,185,80,0)}}
h2{font-size:20px;margin:36px 0 16px;border-left:4px solid var(--gold);padding-left:10px}
p{color:var(--sub);font-size:14px;margin-bottom:10px}
p b{color:var(--txt)}
.seasons{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:680px){.seasons{grid-template-columns:repeat(2,1fr)}}
.season{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.season h3{font-size:16px;margin-bottom:6px}
.season.chun h3{color:var(--green)} .season.xia h3{color:var(--blue)} .season.qiu h3{color:var(--gold)} .season.dong h3{color:var(--sub)}
.season .act{font-size:12px;color:var(--sub)}
.season .day{font-size:11px;color:var(--sub);margin-top:6px}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}
@media(max-width:680px){.cards{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h3{font-size:16px;margin-bottom:6px}
.card.chun h3{color:var(--green)} .card.qiu h3{color:var(--gold)} .card.dong h3{color:var(--sub)}
.card p{font-size:13px;margin:0}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--gold);font-weight:600;background:#11161d;position:sticky;top:0}
tr:hover td{background:#11161d}
.tag{padding:2px 8px;border-radius:6px;font-size:12px}
.t-dong{background:#21262d;color:var(--sub)}
.t-chun{background:rgba(63,185,80,.15);color:var(--green)}
.t-qiu{background:rgba(212,160,23,.15);color:var(--gold)}
.pass{color:var(--green)} .fail{color:var(--red)}
.up{color:var(--red)} .down{color:var(--green)}
.chg{font-size:11px;padding:1px 6px;border-radius:5px;margin-left:6px;white-space:nowrap}
.chg-in{background:rgba(63,185,80,.18);color:var(--green)}
.chg-out{background:rgba(229,72,77,.15);color:var(--red)}
.buy{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}
@media(max-width:680px){.buy{grid-template-columns:1fr}}
.buy .box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;text-align:center}
.buy .box h3{font-size:16px;margin-bottom:6px}
.buy .box .price{font-size:22px;font-weight:700;color:var(--gold)}
.buy .box p{font-size:12px}
.btn{display:block;text-align:center;background:var(--gold);color:#1a1a1a;text-decoration:none;font-weight:700;border-radius:8px;padding:10px;margin-top:14px;font-size:14px}
footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--sub);text-align:center}
footer .warn{color:var(--red);margin-top:8px}
.note{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;font-size:13px;color:var(--sub)}
.note b{color:var(--txt)}
.chgbar{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--green);border-radius:10px;padding:12px 14px;font-size:13px;color:var(--sub);margin-top:14px}
.chgbar b{color:var(--txt)}
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <h1>🌸 春华秋实 · ETF四季分批战法</h1>
    <div class="tag">国内版 · 只做 A股 + 港股通 · 不碰美股欧股日股</div>
    <div class="sub">把"种花→浇灌→摘果→休耕"套进国内ETF —— 教人分批买、分批卖，别一把梭。真做ETF的人写的战法。</div>
    <div class="badges">
      <span class="badge">标的 <b>仅国内 {TOTAL} 支</b></span>
      <span class="badge">已剔除 <b>纳指/标普/德/法/日</b></span>
      <span class="badge">信号 <b>每日自动更新</b></span>
      <span class="badge">本地 <b>买断·不联网</b></span>
    </div>
    <div class="live"><span class="dot"></span>数据日期 {DATE} · 更新于 {UPDATED}</div>
  </header>

  <h2>一、什么是"春华秋实"</h2>
  <p>网上流行说法：<b>试探买入=种花、加仓=追肥、卖出=摘果</b>，本质就是<b>分批建仓、分批止盈</b>。我把这套生命周期补全成"四季"，更好记、更好用：</p>
  <div class="seasons">
    <div class="season chun"><h3>🌱 春·播种</h3><div class="act">试探买入<br>小仓位种下第一颗种子</div><div class="day">第 1 天</div></div>
    <div class="season xia"><h3>💧 夏·浇灌</h3><div class="act">分批加仓<br>确认对了再追肥</div><div class="day">第 2–3 天</div></div>
    <div class="season qiu"><h3>🍎 秋·摘果</h3><div class="act">分批卖出<br>果实熟了分几天收</div><div class="day">第 N+1~N+3 天</div></div>
    <div class="season dong"><h3>❄️ 冬·休耕</h3><div class="act">空仓观望<br>地歇着等下一轮</div><div class="day">平时</div></div>
  </div>
  <p class="note">一句话记住：<b>春种一粒粟，秋收万颗子</b> —— 春天别贪多（试探），夏天别慌（分批），秋天别贪（止盈），冬天别手痒（空仓）。</p>

  <h2>二、为什么只做国内（不要国外的）</h2>
  <p>美股/欧股/日股（纳指、标普500、德国、法国、日经）的ETF，国内散户定投不方便，汇率和时差都是坑。本战法<b>只覆盖 A股宽基/行业 + 港股通</b>，聚焦你真正能方便买、能定投的方向。已剔除上面 5 只境外ETF，剩下 <b>{TOTAL} 支纯国内可投标的</b>。</p>

  <h2>三、今日国内档位速览（{TOTAL}支 · 截至 {DATE}）</h2>
  <div class="cards">
    <div class="card chun"><h3>🌱 春·可播（{SPRINGN}）</h3><p>风控过+估值低：<br><b>{SPRING}</b><br>小仓试探，别重仓</p></div>
    <div class="card qiu"><h3>🍎 秋·摘果（{AUTUMNN}）</h3><p>估值偏高，持有者分批卖、未持有别追：<br><b>{AUTUMN}</b></p></div>
    <div class="card dong"><h3>❄️ 冬·休耕（{WINTERN}）</h3><p>风控未过/趋势向下，暂不参与。<br>弱市纪律：少动、只摘不种</p></div>
  </div>
  {CHGBAR}

  <h2>四、{TOTAL}支国内ETF · 四季档位总表</h2>
  <table>
    <thead><tr><th>季节</th><th>代码</th><th>名称</th><th>综合分</th><th>动量M</th><th>估值分位</th><th>风控</th><th>操作</th></tr></thead>
    <tbody>
{TBODY}
    </tbody>
  </table>
  <p class="note">档位逻辑：<b>风控✅</b>（收盘价站上MA60且MA20在MA60上方）且估值分位&lt;50% → 春（播种）；风控✅且分位≥90% → 秋（摘果·极高）；风控✅且50%–90% → 秋（摘果·高估值）；其余 → 冬（休耕）。<br>因子口径：动量M=近20交易日涨跌幅；估值分位=250日价格区间位置；综合分=0.4×动量分+0.3×估值分+0.3×风控分。<b>数据每个交易日收盘后自动更新。</b></p>

  <h2>五、单只ETF的分批节奏（照天数走）</h2>
  <table>
    <thead><tr><th>天数</th><th>季节</th><th>动作</th><th>仓位</th><th>心法</th></tr></thead>
    <tbody>
      <tr><td>第 1 天</td><td><span class="tag t-chun">春·播种</span></td><td>试探买入</td><td>计划仓位30%</td><td>先种一颗种子，验证方向</td></tr>
      <tr><td>第 2 天</td><td><span class="tag t-chun">夏·浇灌①</span></td><td>分批加仓</td><td>再加20%</td><td>没破位就追肥</td></tr>
      <tr><td>第 3 天</td><td><span class="tag t-chun">夏·浇灌②</span></td><td>分批加仓</td><td>再加20%（累计70%）</td><td>回调加、上涨不加</td></tr>
      <tr><td>第 4–20 天</td><td><span class="tag t-chun">花期·持有</span></td><td>持有观察</td><td>不动</td><td>每周看一次信号</td></tr>
      <tr><td>第 21 天起</td><td><span class="tag t-qiu">秋·摘果①</span></td><td>分批卖出</td><td>卖1/3</td><td>达标+8%或信号转弱先摘</td></tr>
      <tr><td>第 22 天</td><td><span class="tag t-qiu">秋·摘果②</span></td><td>分批卖出</td><td>再卖1/3</td><td>落袋为安</td></tr>
      <tr><td>第 23 天</td><td><span class="tag t-qiu">秋·摘果③</span></td><td>清仓</td><td>剩余全卖</td><td>转入冬·休耕</td></tr>
    </tbody>
  </table>

  <h2>六、怎么买（本地买断 · 不联网）</h2>
  <div class="buy">
    <div class="box"><h3>9.9 引流款</h3><div class="price">¥9.9</div><p>战法速览 + 当月信号</p></div>
    <div class="box"><h3>39 利润款</h3><div class="price">¥39</div><p>完整{TOTAL}支档位表 + 分批节奏详解</p></div>
    <div class="box"><h3>99 旗舰款</h3><div class="price">¥99</div><p>战法 + 网格工具 + 每日信号更新</p></div>
  </div>
  <a class="btn" href="https://www.goofish.com/" target="_blank" rel="noopener">闲鱼搜「老王ETF」拍下 →</a>

  <footer>
    <div>春华秋实 · ETF四季分批战法（国内版）｜ 老王 × WorkBuddy ｜ 数据每日自动更新</div>
    <div class="warn">⚠️ 本页仅为三因子信号与分批方法的演示，所有信号由公开数据计算生成，不构成任何投资建议。ETF有本金亏损风险，请根据自身风险承受能力独立决策。</div>
  </footer>

</div>
</body>
</html>
'''


def main():
    pool = load_pool()
    print("标的池 %d 支，开始抓取..." % len(pool))
    prev = load_prev_season()

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(analyze, c, n): (c, n) for c, n in pool}
        for f in futures:
            pass
        for f in futures:
            try:
                results.append(f.result())
            except Exception as e:
                c, n = futures[f]
                print("  [异常] %s %s: %s" % (c, n, repr(e)[:80]))
                results.append({"代码": c, "名称": n, "季节": "冬", "综合分": "", "动量M": "",
                                "估值分位": "", "风控": "❌异常", "操作": "休耕", "日期": "", "_ok": False})

    ok = [r for r in results if r["_ok"]]
    if not ok:
        print("❌ 全部抓取失败，保留原 index.html 不动")
        return 1
    if len(ok) < len(pool) * 0.7:
        print("⚠️ 仅 %d/%d 支取数成功，成功率偏低但继续生成" % (len(ok), len(pool)))

    # 排序：综合分降序，没数据的垫底
    def sort_key(r):
        try:
            return float(r["综合分"]) if r["综合分"] else -999
        except Exception:
            return -999
    results.sort(key=sort_key, reverse=True)
    for i, r in enumerate(results, 1):
        r["排名"] = i

    spring = [r for r in results if r["季节"] == "春"]
    autumn = [r for r in results if r["季节"] == "秋"]
    winter = [r for r in results if r["季节"] == "冬"]

    # 今日变化
    changes = []
    for r in results:
        old = prev.get(r["代码"])
        if old and old != r["季节"]:
            changes.append((r, old))
    if changes:
        parts = []
        for r, old in changes:
            parts.append('<b>%s</b> %s→%s' % (r["名称"], old, r["季节"]))
        chgbar = ('<div class="chgbar">📢 <b>今日档位变化</b>：' + "；".join(parts) +
                  '<br>季节切换只是信号变化，仍需按分批节奏执行，别一次梭哈。</div>')
    else:
        chgbar = ('<div class="chgbar">✅ <b>今日无档位变化</b>，各ETF季节与上一交易日一致。</div>'
                  if prev else '')

    SEASON_CLS = {"冬": "t-dong", "春": "t-chun", "秋": "t-qiu"}

    def rrow(d):
        cls = SEASON_CLS.get(d["季节"], "t-dong")
        passed = "通过" in d["风控"]
        pcls = "pass" if passed else "fail"
        pmark = "✅" if passed else "❌"
        mark = ""
        old = prev.get(d["代码"])
        if old and old != d["季节"]:
            if d["季节"] in ("春", "秋"):
                mark = '<span class="chg chg-in">新进%s</span>' % d["季节"]
            else:
                mark = '<span class="chg chg-out">转冬</span>'
        mv = d["动量M"]
        mcls = ""
        try:
            mcls = "up" if float(mv) > 0 else "down"
        except Exception:
            pass
        return ('<tr><td><span class="tag %s">%s</span></td>'
                '<td>%s</td><td>%s%s</td><td>%s</td>'
                '<td class="%s">%s</td><td>%s</td>'
                '<td class="%s">%s</td><td>%s</td></tr>'
                % (cls, d["季节"], d["代码"], d["名称"], mark, d["综合分"],
                   mcls, mv, d["估值分位"], pcls, pmark, d["操作"]))

    tbody = "\n".join(rrow(r) for r in results)

    dates = [r["日期"] for r in results if r["日期"]]
    data_date = max(dates) if dates else datetime.date.today().isoformat()
    now = datetime.datetime.now()

    html = (TEMPLATE
            .replace("{TOTAL}", str(len(results)))
            .replace("{SPRINGN}", str(len(spring)))
            .replace("{AUTUMNN}", str(len(autumn)))
            .replace("{WINTERN}", str(len(winter)))
            .replace("{SPRING}", "、".join(r["名称"] for r in spring) or "无（今日无播种标的）")
            .replace("{AUTUMN}", "、".join(r["名称"] for r in autumn) or "无")
            .replace("{DATE}", data_date)
            .replace("{UPDATED}", now.strftime("%Y-%m-%d %H:%M"))
            .replace("{CHGBAR}", chgbar)
            .replace("{TBODY}", tbody))

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    fields = ["季节", "排名", "代码", "名称", "综合分", "动量M", "估值分位", "风控", "操作", "日期"]
    with open(DATA_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})

    print("✅ 生成完成 %s｜春%d 秋%d 冬%d｜取数 %d/%d"
          % (data_date, len(spring), len(autumn), len(winter), len(ok), len(pool)))
    if spring:
        print("   春·可播：", "、".join(r["名称"] for r in spring))
    if autumn:
        print("   秋·摘果：", "、".join(r["名称"] for r in autumn))
    if changes:
        print("   今日变化：", "；".join("%s %s→%s" % (r["名称"], o, r["季节"]) for r, o in changes))
    else:
        print("   今日无档位变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
