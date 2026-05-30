#!/usr/bin/env python3
"""
Twitter/X 推文监控 + 股票分析系统
功能：
- 监控指定博主的推文
- 提取股票代码、分析情绪
- 获取实时股价
- 汇总统计博主近期股票提及
- 通过微信 PushPlus 推送（HTML格式，原文+中文翻译+图片+股票分析）
"""
import os
import json
import re
import time
from datetime import datetime, timezone
import requests
import yfinance as yf
from googletrans import Translator

# ============================================================
# 配置（通过环境变量或本地变量设置）
# ============================================================
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
SCREEN_NAME = os.environ.get("SCREEN_NAME", "aleabitoreddit")  # 监控的博主
PUSHPLUS_API = "https://www.pushplus.plus/send"
TWEET_COUNT = 20            # 每次获取推文数
MAX_NEW_TWEETS = 2          # 每次最多推送条数
GUEST_TOKEN_URL = "https://api.twitter.com/1.1/guest/activate.json"

# 情绪分析关键词词典
BULLISH_KEYWORDS = [
    'buy', 'long', 'bullish', 'strong', 'growth', 'moon', 'rocket',
    'upside', 'rally', 'surge', 'breakout', 'undervalued', 'cheap',
    'potential', 'opportunity', 'accumulate', 'hodl', 'hold', 'buying',
    'adding', 'loaded', 'position', 'conviction', 'confident', 'bull',
    'rally', 'run', 'explode', 'pump', 'gain', 'profit', 'winner',
    'outperform', 'beat', 'crush', 'fly', 'soar', 'climb', 'recover',
    'bounce', 'support', 'accumulate', 'dca', 'buythedip', 'btfd',
    'entry', 'entered', 'entered long', 'calls', 'call options',
    'overweight', 'outperform', 'strong buy', 'buy rating'
]

BEARISH_KEYWORDS = [
    'sell', 'short', 'bearish', 'weak', 'decline', 'crash', 'dump',
    'downside', 'correction', 'overvalued', 'expensive', 'bubble',
    'avoid', 'stay away', 'reduce', 'cut', 'exit', 'liquidate',
    'unload', 'dumping', 'selling', 'shorting', 'put', 'puts',
    'bear', 'fall', 'drop', 'plunge', 'tank', 'collapse', 'crash',
    'recession', 'bear market', 'downtrend', 'lower', 'support broken',
    'resistance', 'rejection', 'overbought', 'rsi high', 'top',
    'peak', 'distribution', 'distribution phase', 'underperform',
    'underweight', 'sell rating', 'strong sell'
]

translator = Translator(service_urls=['translate.google.com'])

# ============================================================
# 核心 API 函数
# ============================================================

def get_guest_token():
    """获取 X/Twitter Guest Token（无需登录）"""
    try:
        headers = {
            "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        }
        resp = requests.post(GUEST_TOKEN_URL, headers=headers, timeout=15)
        data = resp.json()
        return data.get("guest_token")
    except Exception as e:
        print(f"获取 guest token 失败: {e}")
        return None


def get_user_id(screen_name, guest_token):
    """通过 screen_name 获取用户 numeric ID"""
    query_id = "sLVLhk0bGj3MVFEKTdax1w"
    url = f"https://api.twitter.com/graphql/{query_id}/UserByScreenName"
    variables = json.dumps({"screen_name": screen_name, "withSafetyModeUserFields": True})
    features = json.dumps({"hidden_profile_subscriptions_enabled": True, "rweb_tipjar_consumption_enabled": True,
                           "responsive_web_graphql_exclude_directive_enabled": True, "verified_phone_label_enabled": False,
                           "subscriptions_verification_info_is_identity_verified_enabled": True,
                           "subscriptions_verification_info_verified_since_enabled": True,
                           "highlights_tweets_tab_ui_enabled": True, "responsive_web_twitter_article_notes_tab_enabled": True,
                           "creator_subscriptions_tweet_preview_api_enabled": True,
                           "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                           "responsive_web_graphql_timeline_navigation_enabled": True})
    headers = {"Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
               "x-guest-token": guest_token, "content-type": "application/json"}
    params = {"variables": variables, "features": features}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        user = data.get("data", {}).get("user", {}).get("result", {})
        legacy = user.get("legacy", {})
        return user.get("rest_id"), legacy.get("name")
    except Exception as e:
        print(f"获取用户ID失败: {e}")
        return None, None


def get_user_tweets(screen_name, user_id, guest_token, count=20):
    """获取用户推文（排除纯转推）"""
    query_id = "HuTx74BxAnezK1gWvYY7zg"
    url = f"https://api.twitter.com/graphql/{query_id}/UserTweets"
    variables = json.dumps({"userId": user_id, "count": count, "includePromotedContent": False,
                            "withQuickPromoteEligibilityTweetFields": True, "withVoice": True, "withV2Timeline": True})
    features = json.dumps({"rweb_tipjar_consumption_enabled": True, "responsive_web_graphql_exclude_directive_enabled": True,
                           "verified_phone_label_enabled": False, "creator_subscriptions_tweet_preview_api_enabled": True,
                           "responsive_web_graphql_timeline_navigation_enabled": True,
                           "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                           "communities_web_enable_membership_action_button_tweet_creation_enabled": False,
                           "c9s_tweet_anatomy_moderator_badge_enabled": True, "articles_preview_enabled": True,
                           "responsive_web_edit_tweet_api_enabled": True, "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                           "view_counts_everywhere_api_enabled": True, "longform_notetweets_consumption_enabled": True,
                           "responsive_web_twitter_article_tweet_consumption_enabled": True,
                           "tweet_awards_web_tipping_enabled": False, "creator_subscriptions_quote_tweet_preview_enabled": False,
                           "freedom_of_speech_not_reach_fetch_enabled": True, "standardized_nudges_misinfo": True,
                           "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                           "rweb_video_timestamps_enabled": True, "longform_notetweets_rich_text_read_enabled": True,
                           "longform_notetweets_inline_media_enabled": True, "responsive_web_enhance_cards_enabled": False})
    headers = {"Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
               "x-guest-token": guest_token, "content-type": "application/json"}
    params = {"variables": variables, "features": features}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        data = resp.json()
        timeline = data.get("data", {}).get("user", {}).get("result", {}).get("timeline_v2", {}).get("timeline", {}).get("instructions", [])
        tweets = []
        for instruction in timeline:
            if instruction.get("type") != "TimelineAddEntries":
                continue
            for entry in instruction.get("entries", []):
                tweet_result = entry.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
                if not tweet_result:
                    continue
                legacy = tweet_result.get("legacy", {})
                core = tweet_result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                entities = legacy.get("entities", {})
                media_list = entities.get("media", []) if entities else []
                # 排除纯转推
                retweeted = legacy.get("retweeted_status_result")
                if retweeted and not legacy.get("full_text"):
                    continue
                # 提取图片
                images = []
                for m in media_list:
                    if m.get("type") in ("photo", "animated_gif"):
                        img_url = m.get("media_url_https", "")
                        if img_url:
                            images.append(img_url + "?name=large")
                    elif m.get("type") == "video":
                        variants = m.get("video_info", {}).get("variants", [])
                        best = None
                        for v in variants:
                            if v.get("content_type") == "video/mp4":
                                if not best or v.get("bitrate", 0) > best.get("bitrate", 0):
                                    best = v
                        if best:
                            images.append(best.get("url", ""))
                text = legacy.get("full_text", "")
                tweet_id = legacy.get("id_str", "")
                if not tweet_id:
                    continue
                created_at = legacy.get("created_at", "")
                tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
                tweet = {"id": tweet_id, "text": text, "created_at": created_at,
                         "url": tweet_url, "images": images, "author_name": core.get("name", screen_name)}
                tweets.append(tweet)
        return tweets
    except Exception as e:
        print(f"获取推文失败: {e}")
        return []


# ============================================================
# 股票分析功能
# ============================================================

def extract_stock_symbols(text):
    """从推文中提取股票代码（$TSLA, #AAPL 等）"""
    # 匹配 $TSLA 或 #AAPL 格式
    patterns = [
        r'\$([A-Z]{1,5}(?:\.[A-Z]+)?)',  # $TSLA, $BRK.B
        r'#([A-Z]{1,5}(?:\.[A-Z]+)?)',   # #AAPL
        r'\b([A-Z]{2,5})\s*(?:stock|shares|equity|ticker)',  # "TSLA stock"
    ]
    symbols = set()
    for pattern in patterns:
        matches = re.findall(pattern, text.upper())
        for m in matches:
            if isinstance(m, tuple):
                m = m[0]
            # 过滤常见非股票单词
            if m not in {'I', 'A', 'IT', 'IS', 'AM', 'BE', 'DO', 'GO', 'NO', 'OF', 'ON', 'OR', 'SO', 'TO', 'UP', 'US', 'WE'}:
                symbols.add(m)
    return list(symbols)


def analyze_sentiment(text):
    """分析推文对股票的情绪"""
    text_lower = text.lower()
    bullish_score = sum(1 for word in BULLISH_KEYWORDS if word in text_lower)
    bearish_score = sum(1 for word in BEARISH_KEYWORDS if word in text_lower)
    
    if bullish_score > bearish_score:
        return "bullish", bullish_score - bearish_score
    elif bearish_score > bullish_score:
        return "bearish", bearish_score - bullish_score
    else:
        return "neutral", 0


def get_stock_info(symbol):
    """获取股票实时信息"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="2d")
        
        if len(hist) >= 2:
            current = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = current - prev
            change_pct = (change / prev) * 100
        else:
            current = info.get('currentPrice', info.get('regularMarketPrice', 0))
            prev = info.get('previousClose', 0)
            change = current - prev if current and prev else 0
            change_pct = (change / prev) * 100 if prev else 0
        
        return {
            "symbol": symbol,
            "name": info.get("longName", info.get("shortName", symbol)),
            "price": round(current, 2) if current else None,
            "change": round(change, 2) if change else None,
            "change_pct": round(change_pct, 2) if change_pct else None,
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap", 0)
        }
    except Exception as e:
        print(f"获取股票 {symbol} 信息失败: {e}")
        return {"symbol": symbol, "name": symbol, "price": None, "change": None, "change_pct": None, "currency": "USD"}


def analyze_tweet_stocks(tweet_text):
    """分析单条推文中的股票"""
    symbols = extract_stock_symbols(tweet_text)
    if not symbols:
        return []
    
    sentiment, strength = analyze_sentiment(tweet_text)
    stock_analyses = []
    for symbol in symbols:
        info = get_stock_info(symbol)
        info["sentiment"] = sentiment
        info["sentiment_strength"] = strength
        stock_analyses.append(info)
    return stock_analyses


def update_stock_stats(state, stock_analyses):
    """更新股票统计信息"""
    if "stock_stats" not in state:
        state["stock_stats"] = {}
    
    for stock in stock_analyses:
        symbol = stock["symbol"]
        if symbol not in state["stock_stats"]:
            state["stock_stats"][symbol] = {
                "mentions": 0,
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "first_seen": datetime.now(timezone.utc).isoformat()
            }
        state["stock_stats"][symbol]["mentions"] += 1
        state["stock_stats"][symbol]["last_seen"] = datetime.now(timezone.utc).isoformat()
        sentiment = stock.get("sentiment", "neutral")
        if sentiment == "bullish":
            state["stock_stats"][symbol]["bullish"] += 1
        elif sentiment == "bearish":
            state["stock_stats"][symbol]["bearish"] += 1
        else:
            state["stock_stats"][symbol]["neutral"] += 1


def get_top_stocks(state, top_n=5):
    """获取提及最多的股票统计"""
    stats = state.get("stock_stats", {})
    if not stats:
        return []
    
    sorted_stocks = sorted(stats.items(), key=lambda x: x[1]["mentions"], reverse=True)
    result = []
    for symbol, data in sorted_stocks[:top_n]:
        total = data["mentions"]
        bullish = data["bullish"]
        bearish = data["bearish"]
        if bullish > bearish:
            tendency = "📈 看涨"
        elif bearish > bullish:
            tendency = "📉 看跌"
        else:
            tendency = "➖ 中性"
        result.append({
            "symbol": symbol,
            "mentions": total,
            "bullish": bullish,
            "bearish": bearish,
            "neutral": data["neutral"],
            "tendency": tendency
        })
    return result


# ============================================================
# 翻译
# ============================================================

def translate_text(text):
    """英文翻译为简体中文"""
    if not text:
        return ""
    try:
        result = translator.translate(text, src='en', dest='zh-cn')
        return result.text if result else ""
    except Exception as e:
        print(f"翻译失败: {e}")
        return ""


# ============================================================
# HTML 推送构建
# ============================================================

def build_html_push(author_name, new_tweets, state):
    """构建 HTML 推送内容（含股票分析）"""
    top_stocks = get_top_stocks(state, top_n=5)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#f5f5f5;margin:0;padding:16px}}
.container{{max-width:600px;margin:0 auto}}
.card{{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);margin-bottom:16px;overflow:hidden}}
.card-header{{background:linear-gradient(135deg,#1da1f2,#0d8bd9);color:#fff;padding:16px 20px}}
.card-header h2{{margin:0;font-size:18px}}
.card-header .subtitle{{margin:4px 0 0;font-size:13px;opacity:0.9}}
.card-body{{padding:16px 20px}}
.tweet{{border-bottom:1px solid #eee;padding:16px 0}}
.tweet:last-child{{border-bottom:none}}
.tweet-header{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.tweet-author{{font-weight:600;color:#1da1f2;font-size:15px}}
.tweet-time{{font-size:12px;color:#8899a6}}
.original{{font-size:15px;color:#14171a;line-height:1.6;margin-bottom:10px;word-break:break-word}}
.translated{{font-size:14px;color:#657786;line-height:1.6;padding:10px;background:#f7f9fa;border-radius:8px;border-left:3px solid #1da1f2;margin-bottom:10px}}
.images{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}}
.images img{{max-width:100%;border-radius:8px;max-height:280px;object-fit:cover}}
.view-btn{{display:inline-block;margin-top:10px;padding:8px 16px;background:#1da1f2;color:#fff;text-decoration:none;border-radius:20px;font-size:13px}}
.stock-section{{margin-top:12px;padding:12px;background:#f0f8ff;border-radius:8px}}
.stock-title{{font-weight:600;color:#1a5276;font-size:14px;margin-bottom:8px}}
.stock-item{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px dashed #ddd}}
.stock-item:last-child{{border-bottom:none}}
.stock-name{{font-weight:600;color:#2c3e50}}
.stock-price{{font-family:monospace;font-size:15px}}
.stock-change-up{{color:#e74c3c;font-weight:600}}  /* 中国红=涨 */
.stock-change-down{{color:#2ecc71;font-weight:600}} /* 中国绿=跌 */
.sentiment-bullish{{color:#e74c3c;font-weight:600}}
.sentiment-bearish{{color:#2ecc71;font-weight:600}}
.sentiment-neutral{{color:#7f8c8d}}
.stats-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
.stats-table th{{text-align:left;padding:8px;background:#e8f4f8;color:#1a5276;font-weight:600}}
.stats-table td{{padding:8px;border-bottom:1px solid #eee}}
.stats-table tr:hover{{background:#f7f9fa}}
.footer{{text-align:center;padding:20px;color:#8899a6;font-size:12px}}
</style>
</head>
<body>
<div class="container">
<div class="card">
<div class="card-header">
<h2>@{SCREEN_NAME} 推文监控</h2>
<div class="subtitle">{author_name} · 检测到 {len(new_tweets)} 条新推文</div>
</div>
</div>
"""
    
    # 股票统计面板
    if top_stocks:
        html += """<div class="card"><div class="card-body">
<div class="stock-title">📊 近期股票提及统计 (Top {})</div>
<table class="stats-table">
<tr><th>代码</th><th>提及</th><th>看涨</th><th>看跌</th><th>倾向</th></tr>
""".format(len(top_stocks))
        for s in top_stocks:
            html += f"<tr><td><b>{s['symbol']}</b></td><td>{s['mentions']}次</td><td style='color:#e74c3c'>{s['bullish']}</td><td style='color:#2ecc71'>{s['bearish']}</td><td>{s['tendency']}</td></tr>"
        html += "</table></div></div>"
    
    # 推文列表
    for tweet in new_tweets:
        stock_analyses = tweet.get("stock_analyses", [])
        translated = tweet.get("translated", "")
        html += f"""<div class="card"><div class="card-body">
<div class="tweet">
<div class="tweet-header">
<span class="tweet-author">@{SCREEN_NAME}</span>
<span class="tweet-time">{tweet.get('created_at','')}</span>
</div>
<div class="original">{tweet.get('text','')}</div>
<div class="translated">{translated}</div>
"""
        # 股票分析
        for stock in stock_analyses:
            sentiment_emoji = "📈" if stock["sentiment"] == "bullish" else "📉" if stock["sentiment"] == "bearish" else "➖"
            sentiment_class = f"sentiment-{stock['sentiment']}"
            price_str = f"${stock['price']}" if stock['price'] else "价格未知"
            change_str = ""
            if stock['change'] is not None:
                sign = "+" if stock['change'] >= 0 else ""
                color_class = "stock-change-up" if stock['change'] >= 0 else "stock-change-down"
                change_str = f'<span class="{color_class}"> {sign}{stock["change"]} ({sign}{stock["change_pct"]}%)</span>'
            html += f"""<div class="stock-section">
<div class="stock-title">{sentiment_emoji} 股票分析</div>
<div class="stock-item">
<span class="stock-name">{stock['symbol']} {stock.get('name','')}</span>
<span>{price_str}{change_str}</span>
</div>
<div style="font-size:12px;color:#7f8c8d;margin-top:4px">
情绪: <span class="{sentiment_class}">{stock['sentiment'].upper()}</span> · 
强度: {stock.get('sentiment_strength',0)} · 货币: {stock.get('currency','USD')}
</div>
</div>
"""
        
        # 图片
        images = tweet.get("images", [])
        if images:
            html += '<div class="images">'
            for img in images:
                html += f'<img src="{img}" alt="推文图片">'
            html += '</div>'
        
        html += f'<a href="{tweet.get("url","")}" class="view-btn" target="_blank">🔗 查看原文</a>'
        html += "</div></div></div>"
    
    html += """<div class="footer">
<p>自动推送 · GitHub Actions 监控</p>
<p style="font-size:11px;color:#aab8c2">数据来源: X.com · 股价数据: Yahoo Finance</p>
</div></div></body></html>"""
    return html


# ============================================================
# PushPlus 推送
# ============================================================

def pushplus_notify(title, html_content):
    """发送 PushPlus 推送"""
    if not PUSHPLUS_TOKEN:
        print("未配置 PUSHPLUS_TOKEN，跳过推送")
        return False
    payload = {"token": PUSHPLUS_TOKEN, "title": title, "content": html_content, "template": "html"}
    try:
        resp = requests.post(PUSHPLUS_API, data=payload, timeout=20)
        data = resp.json()
        if data.get("code") == 200:
            print("✅ PushPlus 推送成功")
            return True
        else:
            print(f"❌ PushPlus 推送失败: {data.get('msg', data)}")
            return False
    except Exception as e:
        print(f"❌ PushPlus 请求异常: {e}")
        return False


# ============================================================
# 状态持久化（GitHub Actions 中使用文件，本地也可用）
# ============================================================

STATE_FILE = "state.json"

def load_state():
    """加载状态文件"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"known_tweet_ids": [], "last_check": None, "stock_stats": {}}


def save_state(state):
    """保存状态文件"""
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# 主流程
# ============================================================

def main():
    print(f"{'='*60}")
    print(f"Twitter/X 推文 + 股票分析监控启动")
    print(f"目标博主: @{SCREEN_NAME}")
    print(f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}")
    
    # 1. 获取 guest token
    print("获取 guest token...")
    guest_token = get_guest_token()
    if not guest_token:
        print("❌ 无法获取 guest token，退出")
        return
    print(f"✅ guest token: {guest_token[:20]}...")
    
    # 2. 获取用户 ID
    print(f"查询用户 @{SCREEN_NAME}...")
    user_id, user_name = get_user_id(SCREEN_NAME, guest_token)
    if not user_id:
        print("❌ 无法获取用户ID，退出")
        return
    print(f"✅ 用户: {user_name} (ID: {user_id})")
    
    # 3. 获取推文
    print(f"获取最近 {TWEET_COUNT} 条推文...")
    tweets = get_user_tweets(SCREEN_NAME, user_id, guest_token, TWEET_COUNT)
    print(f"✅ 获取到 {len(tweets)} 条推文")
    
    # 4. 加载状态
    state = load_state()
    known_ids = set(state.get("known_tweet_ids", []))
    print(f"状态文件已记录 {len(known_ids)} 条推文")
    
    # 5. 筛选新推文
    new_tweets = []
    for t in tweets:
        if t["id"] not in known_ids:
            # 翻译
            t["translated"] = translate_text(t["text"])
            # 股票分析
            t["stock_analyses"] = analyze_tweet_stocks(t["text"])
            # 更新统计
            update_stock_stats(state, t["stock_analyses"])
            new_tweets.append(t)
            known_ids.add(t["id"])
    
    print(f"发现 {len(new_tweets)} 条新推文")
    
    # 6. 推送新推文
    if new_tweets and PUSHPLUS_TOKEN:
        push_tweets = new_tweets[:MAX_NEW_TWEETS]
        title = f"@{SCREEN_NAME} 新推文 ({len(new_tweets)}条) - 含股票分析"
        html = build_html_push(user_name, push_tweets, state)
        pushplus_notify(title, html)
    
    # 7. 保存状态
    state["known_tweet_ids"] = list(known_ids)
    save_state(state)
    print(f"{'='*60}")
    if new_tweets:
        print(f"✅ 已推送 {len(push_tweets)} 条新推文 (共{len(new_tweets)}条)")
    else:
        print("暂无新推文，等待下次检查")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
