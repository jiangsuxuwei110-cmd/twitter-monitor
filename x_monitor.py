#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X 推文监控 + PushPlus 微信推送 (GitHub Actions 版)
监控用户: aleabitoreddit
功能: 原文+中文翻译+图片展示+HTML推送
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from googletrans import Translator

# ============ 配置（从环境变量读取）============
SCREEN_NAME = os.environ.get("SCREEN_NAME", "aleabitoreddit")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
STATE_FILE = "state.json"
AUTH_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

QUERY_USER_BY_SCREEN_NAME = "sLVLhk0bGj3MVFEKTdax1w"
QUERY_USER_TWEETS = "HuTx74BxAnezK1gWvYY7zg"

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
    if not text or len(text.strip()) == 0:
        return ""
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
    return "[翻译失败]"


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
    }


def get_user_id(screen_name, guest_token):
    url = 'https://x.com/i/api/graphql/sLVLhk0bGj3MVFEKTdax1w/UserByScreenName'
    headers = get_api_headers(guest_token)
    params = {
        'variables': json.dumps({"screen_name": screen_name, "withSafetyModeUserFields": True}),
        'features': json.dumps({"hidden_profile_likes_enabled": True, "hidden_profile_subscriptions_enabled": True,
            "rweb_tipjar_consumption_enabled": True, "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False, "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True, "responsive_web_twitter_article_notes_tab_enabled": True,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "creator_subscriptions_tweet_preview_api_enabled": True, "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True})
    }
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = data.get('data', {}).get('user', {}).get('result', {})
    return result.get('rest_id') or result.get('id')


def get_user_tweets(user_id, screen_name, guest_token, count=30):
    url = 'https://x.com/i/api/graphql/HuTx74BxAnezK1gWvYY7zg/UserTweets'
    headers = get_api_headers(guest_token)
    variables = {
        "userId": user_id,
        "count": count,
        "includePromotedContent": False,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        "withV2Timeline": True
    }
    features = {
        "rweb_tipjar_consumption_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
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
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_media_download_video_enabled": False,
        "responsive_web_enhance_cards_enabled": False
    }
    resp = requests.get(url, headers=headers, params={'variables': json.dumps(variables), 'features': json.dumps(features)}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    tweets = []
    timeline = data.get('data', {}).get('user', {}).get('result', {}).get('timeline_v2', {}).get('timeline', {})
    instructions = timeline.get('instructions', [])

    for instr in instructions:
        if instr.get('type') == 'TimelineAddEntries':
            for entry in instr.get('entries', []):
                content = entry.get('content', {})
                if content.get('entryType') == 'TimelineTimelineItem':
                    item_content = content.get('itemContent', {})
                    if item_content.get('itemType') == 'TimelineTweet':
                        tweet_result = item_content.get('tweet_results', {}).get('result', {})
                        core = tweet_result.get('core', {}).get('user_results', {}).get('result', {})
                        legacy = tweet_result.get('legacy', {})

                        tweet_id = legacy.get('id_str', '')
                        full_text = legacy.get('full_text', '')
                        created_at = legacy.get('created_at', '')
                        is_retweet = bool(legacy.get('retweeted_status_result'))
                        reply_count = legacy.get('reply_count', 0)
                        retweet_count = legacy.get('retweet_count', 0)
                        favorite_count = legacy.get('favorite_count', 0)

                        media_urls = []
                        ext_entities = legacy.get('extended_entities', {})
                        for m in ext_entities.get('media', []):
                            if m.get('type') == 'photo':
                                media_urls.append(m.get('media_url_https', ''))
                            elif m.get('type') == 'video':
                                media_urls.append(m.get('media_url_https', ''))

                        if not tweet_id:
                            continue

                        tweets.append({
                            'id': tweet_id,
                            'text': full_text,
                            'created_at': created_at,
                            'is_retweet': is_retweet,
                            'reply_count': reply_count,
                            'retweet_count': retweet_count,
                            'favorite_count': favorite_count,
                            'media_urls': media_urls,
                        })
    return tweets


def pushplus_notify(title, content):
    if not PUSHPLUS_TOKEN:
        log("[PushPlus] 未配置 TOKEN，跳过推送")
        return False
    url = "https://www.pushplus.plus/send"
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html"
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        result = resp.json()
        if result.get('code') == 200:
            log("[PushPlus] 推送成功")
            return True
        else:
            log(f"[PushPlus] 推送失败: {result}")
            return False
    except Exception as e:
        log(f"[PushPlus] 推送异常: {e}")
        return False


def build_html_push(tweets, screen_name):
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 12px; background: #f0f2f5; color: #333; font-size: 14px; line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, #1da1f2 0%, #0d8bd9 100%); color: white; padding: 16px; border-radius: 12px; margin-bottom: 12px; text-align: center; }}
.header h2 {{ margin: 0; font-size: 16px; }}
.header p {{ margin: 4px 0 0 0; opacity: 0.9; font-size: 12px; }}
.tweet {{ background: white; border-radius: 12px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.tweet-header {{ display: flex; align-items: center; margin-bottom: 10px; }}
.tweet-header img {{ width: 40px; height: 40px; border-radius: 50%; margin-right: 10px; background: #e1e8ed; }}
.tweet-header .name {{ font-weight: 600; color: #1da1f2; font-size: 15px; }}
.tweet-header .time {{ color: #8899a6; font-size: 12px; margin-top: 2px; }}
.label {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-bottom: 8px; }}
.label-original {{ background: #e8f5fe; color: #1da1f2; }}
.label-trans {{ background: #f0f9eb; color: #67c23a; }}
.text {{ margin: 8px 0; word-break: break-word; }}
.original {{ color: #14171a; }}
.translation {{ color: #555; background: #fafafa; padding: 10px; border-radius: 8px; margin-top: 6px; border-left: 3px solid #67c23a; }}
.media {{ margin-top: 10px; }}
.media img {{ max-width: 100%; border-radius: 8px; margin-bottom: 6px; display: block; }}
.stats {{ display: flex; gap: 16px; margin-top: 10px; font-size: 12px; color: #8899a6; }}
.stats span {{ display: flex; align-items: center; gap: 4px; }}
.footer {{ text-align: center; margin-top: 16px; padding: 12px; }}
.footer a {{ display: inline-block; background: #1da1f2; color: white; padding: 10px 24px; border-radius: 20px; text-decoration: none; font-size: 13px; font-weight: 600; }}
.more {{ text-align: center; color: #8899a6; font-size: 13px; padding: 8px; }}
</style>
</head>
<body>
<div class="header">
<h2>@{screen_name} 新推文提醒</h2>
<p>共 {len(tweets)} 条新推文</p>
</div>
"""

    for t in tweets:
        tweet_url = f"https://x.com/{screen_name}/status/{t['id']}"
        created_str = t['created_at']

        text_en = t['text']
        text_zh = t.get('translation', translate_text(text_en))

        media_html = ""
        if t.get('media_urls'):
            media_html = '<div class="media">'
            for img_url in t['media_urls']:
                media_html += f'<img src="{img_url}" alt="推文图片">'
            media_html += '</div>'

        html += f"""
<div class="tweet">
<div class="tweet-header">
<div>
<div class="name">@{screen_name}</div>
<div class="time">{created_str}</div>
</div>
</div>
<div class="label label-original">原文</div>
<div class="text original">{text_en.replace(chr(10), '<br>')}</div>
<div class="label label-trans">中文翻译</div>
<div class="text translation">{text_zh.replace(chr(10), '<br>')}</div>
{media_html}
<div class="stats">
<span>回复 {t.get('reply_count', 0)}</span>
<span>转发 {t.get('retweet_count', 0)}</span>
<span>点赞 {t.get('favorite_count', 0)}</span>
</div>
</div>
"""

    html += f"""
<div class="footer">
<a href="{tweet_url}">查看原文及评论讨论</a>
</div>
</body>
</html>"""
    return html


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'known_tweet_ids': [], 'last_check': None}


def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    log("=" * 50)
    log(f"开始监控 @{SCREEN_NAME}")
    log("=" * 50)

    if not PUSHPLUS_TOKEN:
        log("[错误] 未设置 PUSHPLUS_TOKEN 环境变量")
        sys.exit(1)

    state = load_state()
    known_ids = set(state.get('known_tweet_ids', []))
    log(f"已知推文: {len(known_ids)} 条")

    try:
        guest_token = get_guest_token()
        log(f"Guest Token: {guest_token[:10]}...")

        user_id = get_user_id(SCREEN_NAME, guest_token)
        log(f"用户ID: {user_id}")

        tweets = get_user_tweets(user_id, SCREEN_NAME, guest_token, count=20)
        log(f"获取推文: {len(tweets)} 条")

        # 过滤转推
        original_tweets = [t for t in tweets if not t.get('is_retweet')]
        log(f"原创推文: {len(original_tweets)} 条")

        if not original_tweets:
            log("没有获取到原创推文")
            save_state({
                'known_tweet_ids': list(known_ids),
                'last_check': datetime.now(timezone.utc).isoformat()
            })
            return

        # 检测新推文
        new_tweets = [t for t in original_tweets if t['id'] not in known_ids]
        log(f"新推文: {len(new_tweets)} 条")

        if not known_ids:
            log("首次运行，记录推文状态，不推送")
            all_ids = [t['id'] for t in original_tweets]
            save_state({
                'known_tweet_ids': all_ids,
                'last_check': datetime.now(timezone.utc).isoformat()
            })
            return

        if new_tweets:
            log(f"发现 {len(new_tweets)} 条新推文，开始处理...")
            to_push = new_tweets[:2]
            more = len(new_tweets) - len(to_push)

            # 预翻译
            for t in to_push:
                log(f"翻译推文 {t['id'][:8]}...")
                t['translation'] = translate_text(t['text'])

            log("生成HTML推送...")
            html_content = build_html_push(to_push, SCREEN_NAME)

            title = f"@{SCREEN_NAME} 新推文 ({len(new_tweets)}条)"
            if more > 0:
                title += f" 还有{more}条未显示"

            pushplus_notify(title, html_content)
        else:
            log("没有新推文")

        # 更新状态
        all_ids = [t['id'] for t in original_tweets]
        save_state({
            'known_tweet_ids': all_ids,
            'last_check': datetime.now(timezone.utc).isoformat()
        })
        log("状态已保存")

    except Exception as e:
        log(f"[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    log("监控完成")


if __name__ == '__main__':
    main()
