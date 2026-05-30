#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X 推文监控 + PushPlus 微信推送 (HTML增强版)
监控用户: aleabitoreddit
功能: 原文+中文翻译+图片展示+HTML推送
频率: 每15分钟
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from googletrans import Translator

# ============ 配置 ============
SCREEN_NAME = "aleabitoreddit"
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_monitor_state.json")
AUTH_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# GraphQL Query IDs (from twitter-api-client)
QUERY_USER_BY_SCREEN_NAME = "sLVLhk0bGj3MVFEKTdax1w"
QUERY_USER_TWEETS = "HuTx74BxAnezK1gWvYY7zg"

# 翻译器
_translator = None

def get_translator():
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")
    sys.stdout.flush()


def translate_text(text, max_retries=2):
    """将英文翻译成中文，带重试机制"""
    if not text or len(text.strip()) == 0:
        return ""
    # 限制翻译长度，避免API限制
    if len(text) > 4000:
        text = text[:4000] + "..."
    
    for attempt in range(max_retries):
        try:
            tr = get_translator()
            result = tr.translate(text, dest='zh-cn', src='en')
            return result.text
        except Exception as e:
            log(f"[翻译重试 {attempt+1}/{max_retries}] {e}")
            time.sleep(1)
    return "[翻译失败，请查看原文]"


def get_guest_token():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Authorization': f'Bearer {AUTH_BEARER}',
    }
    resp = requests.post('https://api.x.com/1.1/guest/activate.json', headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()['guest_token']


def get_api_headers(guest_token):
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Authorization': f'Bearer {AUTH_BEARER}',
        'Content-Type': 'application/json',
        'x-guest-token': guest_token,
        'x-twitter-active-user': 'yes',
        'x-twitter-client-language': 'en',
        'Origin': 'https://x.com',
        'Referer': 'https://x.com/',
    }


def get_user_id(screen_name, headers):
    url = f"https://api.x.com/graphql/{QUERY_USER_BY_SCREEN_NAME}/UserByScreenName"
    params = {
        "variables": json.dumps({
            "screen_name": screen_name,
            "withSafetyModeUserFields": True
        }),
        "features": json.dumps({
            "hidden_profile_likes_enabled": True,
            "hidden_profile_subscriptions_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "responsive_web_twitter_article_notes_tab_enabled": True,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True
        }),
        "fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data['data']['user']['result']['rest_id']


def get_user_tweets(user_id, headers, count=20):
    url = f"https://api.x.com/graphql/{QUERY_USER_TWEETS}/UserTweets"
    params = {
        "variables": json.dumps({
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True
        }),
        "features": json.dumps({
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": False,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_media_download_video_enabled": False,
            "responsive_web_enhance_cards_enabled": False
        }),
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 解析推文
    timeline = data.get('data', {}).get('user', {}).get('result', {}).get('timeline_v2', {}).get('timeline', {})
    instructions = timeline.get('instructions', [])
    tweets = []
    for instr in instructions:
        if instr.get('type') == 'TimelineAddEntries':
            for entry in instr.get('entries', []):
                content = entry.get('content', {})
                if content.get('entryType') == 'TimelineTimelineItem':
                    item_content = content.get('itemContent', {})
                    if item_content.get('itemType') == 'TimelineTweet':
                        tweet_result = item_content.get('tweet_results', {}).get('result', {})
                        legacy = tweet_result.get('legacy', {})
                        if legacy and legacy.get('id_str'):
                            # 过滤掉转推
                            if legacy.get('retweeted_status_result') is None:
                                # 提取图片
                                photos = []
                                ext_entities = legacy.get('extended_entities', {})
                                media_list = ext_entities.get('media', [])
                                if not media_list:
                                    media_list = legacy.get('entities', {}).get('media', [])
                                for m in media_list:
                                    if m.get('type') == 'photo':
                                        url = m.get('media_url_https', '')
                                        if url:
                                            # 使用大图
                                            url = url + '?name=large'
                                            photos.append(url)
                                
                                # 提取互动数据
                                reply_count = legacy.get('reply_count', 0)
                                retweet_count = legacy.get('retweet_count', 0)
                                favorite_count = legacy.get('favorite_count', 0)
                                
                                tweets.append({
                                    'id': legacy['id_str'],
                                    'text': legacy.get('full_text', ''),
                                    'created_at': legacy.get('created_at', ''),
                                    'photos': photos,
                                    'reply_count': reply_count,
                                    'retweet_count': retweet_count,
                                    'favorite_count': favorite_count,
                                })
    return tweets


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"known_tweet_ids": [], "last_check": None}


def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_html_push(tweets, screen_name):
    """构建 HTML 推送内容"""
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f7f9fa;
    margin: 0;
    padding: 16px;
    color: #0f1419;
}}
.container {{
    max-width: 600px;
    margin: 0 auto;
}}
.header {{
    background: linear-gradient(135deg, #1d9bf0 0%, #1a8cd8 100%);
    color: white;
    padding: 16px 20px;
    border-radius: 16px 16px 0 0;
    font-size: 15px;
    font-weight: 600;
}}
.header a {{
    color: white;
    text-decoration: none;
}}
.tweet-card {{
    background: white;
    border-radius: 0 0 16px 16px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
.tweet-header {{
    display: flex;
    align-items: center;
    margin-bottom: 14px;
}}
.tweet-author {{
    font-weight: 700;
    font-size: 15px;
    color: #0f1419;
}}
.tweet-time {{
    font-size: 13px;
    color: #536471;
    margin-left: auto;
}}
.section-label {{
    font-size: 12px;
    font-weight: 600;
    color: #536471;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 16px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #eff3f4;
}}
.original-text {{
    font-size: 15px;
    line-height: 1.6;
    color: #0f1419;
    white-space: pre-wrap;
    word-break: break-word;
}}
.translated-text {{
    font-size: 15px;
    line-height: 1.7;
    color: #1d9bf0;
    background: #f0f8ff;
    padding: 12px 14px;
    border-radius: 12px;
    border-left: 3px solid #1d9bf0;
    white-space: pre-wrap;
    word-break: break-word;
}}
.photo-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 8px;
    margin-top: 12px;
}}
.photo-grid img {{
    width: 100%;
    border-radius: 12px;
    object-fit: cover;
    max-height: 300px;
}}
.stats {{
    display: flex;
    gap: 20px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid #eff3f4;
    font-size: 13px;
    color: #536471;
}}
.stats span {{
    display: flex;
    align-items: center;
    gap: 4px;
}}
.view-btn {{
    display: inline-block;
    margin-top: 14px;
    padding: 10px 20px;
    background: #1d9bf0;
    color: white;
    text-decoration: none;
    border-radius: 24px;
    font-size: 14px;
    font-weight: 600;
    text-align: center;
}}
.view-btn:hover {{
    background: #1a8cd8;
}}
.footer {{
    text-align: center;
    font-size: 12px;
    color: #8899a6;
    margin-top: 20px;
    padding-bottom: 10px;
}}
</style>
</head>
<body>
<div class="container">
<div class="header">
    🐦 @{screen_name} 发布新推文
</div>
"""
    
    for t in tweets:
        tweet_url = f"https://x.com/{screen_name}/status/{t['id']}"
        created = t['created_at']
        photos_html = ""
        if t['photos']:
            imgs = "\n".join([f'<img src="{url}" alt="推文图片">' for url in t['photos']])
            photos_html = f'<div class="photo-grid">\n{imgs}\n</div>'
        
        html += f"""
<div class="tweet-card">
    <div class="tweet-header">
        <span class="tweet-author">@{screen_name}</span>
        <span class="tweet-time">{created}</span>
    </div>
    
    <div class="section-label">📝 原文</div>
    <div class="original-text">{escape_html(t['text'])}</div>
    
    {photos_html}
    
    <div class="section-label">🌐 中文翻译</div>
    <div class="translated-text">{escape_html(t['translated'])}</div>
    
    <div class="stats">
        <span>💬 {t['reply_count']} 回复</span>
        <span>🔄 {t['retweet_count']} 转发</span>
        <span>❤️ {t['favorite_count']} 点赞</span>
    </div>
    
    <a href="{tweet_url}" class="view-btn" target="_blank">查看原文及评论讨论 →</a>
</div>
"""
    
    html += """
<div class="footer">
    由 Twitter/X 监控系统自动推送 · PushPlus
</div>
</div>
</body>
</html>"""
    
    return html


def escape_html(text):
    """HTML转义"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def pushplus_notify_html(title, html_content):
    """通过 PushPlus 推送 HTML 消息到微信"""
    if not PUSHPLUS_TOKEN:
        log("[WARN] PUSHPLUS_TOKEN 未设置，跳过推送")
        return False

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": html_content,
        "template": "html"
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get('code') == 200:
            log("[PushPlus] HTML推送成功")
            return True
        else:
            log(f"[PushPlus] 推送失败: {result}")
            return False
    except Exception as e:
        log(f"[PushPlus] 请求异常: {e}")
        return False


def main():
    log("=" * 50)
    log("开始监控 Twitter/X 用户: @" + SCREEN_NAME)
    log("=" * 50)

    if not PUSHPLUS_TOKEN:
        log("[ERROR] 环境变量 PUSHPLUS_TOKEN 未设置！")
        sys.exit(1)

    state = load_state()
    known_ids = set(state.get("known_tweet_ids", []))

    try:
        # 1. 获取 guest token
        guest_token = get_guest_token()
        headers = get_api_headers(guest_token)

        # 2. 获取用户ID
        user_id = get_user_id(SCREEN_NAME, headers)
        log(f"用户ID: {user_id}")

        # 3. 获取最新推文
        tweets = get_user_tweets(user_id, headers, count=20)
        log(f"获取到 {len(tweets)} 条推文")

        # 4. 找出新推文
        new_tweets = [t for t in tweets if t['id'] not in known_ids]

        if not known_ids:
            # 首次运行，只记录不推送
            log("首次运行，记录当前推文，下次将推送新内容。")
            all_ids = [t['id'] for t in tweets]
            state["known_tweet_ids"] = all_ids[:50]
            state["last_check"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            log(f"已记录 {len(all_ids)} 条推文ID")
        elif new_tweets:
            log(f"发现 {len(new_tweets)} 条新推文！")
            
            # 限制每次最多推送2条（翻译耗时，内容量大）
            to_push = new_tweets[:2]
            
            # 翻译每条推文
            for t in to_push:
                log(f"正在翻译推文 {t['id'][:10]}...")
                t['translated'] = translate_text(t['text'])
                time.sleep(0.5)  # 避免翻译API限流
            
            # 生成HTML并推送
            html_content = build_html_push(to_push, SCREEN_NAME)
            pushplus_notify_html(f"@{SCREEN_NAME} 新推文", html_content)

            # 更新状态
            all_ids = [t['id'] for t in tweets]
            state["known_tweet_ids"] = all_ids[:50]
            state["last_check"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
        else:
            log("没有新推文。")
            state["last_check"] = datetime.now(timezone.utc).isoformat()
            save_state(state)

    except Exception as e:
        log(f"[ERROR] 监控异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    log("监控完成。")


if __name__ == "__main__":
    main()
