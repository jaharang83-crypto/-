#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
holidays.py — Google 공휴일 캘린더(ICS)로 공휴일 캐시 생성 (API 키 불필요)
briefing.py의 기한 순연(설·추석·대체공휴일 포함) 정확도를 위해 연 1~2회 실행.
사용: python3 holidays.py            # 작년+올해+내년 공휴일 → data/공휴일.json
공휴일 정보가 없어도 briefing.py는 동작합니다 (주말 순연만 적용).
"""
import json, re, sys, urllib.request
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
ICS_URL = ('https://calendar.google.com/calendar/ical/'
           'ko.south_korea%23holiday%40group.v.calendar.google.com/public/basic.ics')

def fetch_ics():
    req = urllib.request.Request(ICS_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8')

def unfold(text):
    """ICS 줄바꿈 접힘(line folding) 해제: 공백/탭으로 시작하는 줄은 이전 줄에 이어붙임"""
    lines = text.replace('\r\n', '\n').split('\n')
    out = []
    for ln in lines:
        if ln.startswith((' ', '\t')) and out:
            out[-1] += ln[1:]
        else:
            out.append(ln)
    return out

# 국세기본법 제5조 기한 특례 대상: 관공서 공휴일 + 근로자의 날.
# Google 캘린더에는 제헌절·식목일·어버이날 같은 '쉬지 않는 기념일'도 섞여 있어
# 이름 기준으로 법정 공휴일만 걸러낸다 (걸러내지 않으면 기한이 실제보다 늦게 계산됨).
OFFICIAL = re.compile(
    r'신정|새해|설날|삼일절|3\.?1절|부처님|석가탄신일|어린이날|현충일|광복절'
    r'|추석|개천절|한글날|성탄절|기독탄신일|크리스마스|대체\s*공휴일|대체휴일'
    r'|임시\s*공휴일|선거|투표|근로자의\s*날')
NOT_HOLIDAY = re.compile(r'이브|전야|섣달')

def parse_events(text):
    """VEVENT의 DTSTART(날짜)·SUMMARY(공휴일명)만 추출 — 법정 공휴일만"""
    events = {}
    cur = {}
    for ln in unfold(text):
        if ln == 'BEGIN:VEVENT':
            cur = {}
        elif ln == 'END:VEVENT':
            if 'date' in cur and 'name' in cur:
                name = cur['name']
                if OFFICIAL.search(name) and not NOT_HOLIDAY.search(name):
                    events[cur['date']] = name
        elif ln.startswith('DTSTART'):
            m = re.search(r'(\d{8})$', ln)
            if m:
                d = m.group(1)
                cur['date'] = f'{d[:4]}-{d[4:6]}-{d[6:]}'
        elif ln.startswith('SUMMARY:'):
            cur['name'] = ln[len('SUMMARY:'):].strip()
    return events

def main():
    try:
        text = fetch_ics()
    except Exception as e:
        print(f'⚠ 공휴일 캘린더를 가져오지 못했습니다: {e}')
        print('  주말 순연만 적용됩니다. (네트워크 확인 후 재실행)')
        sys.exit(0)

    events = parse_events(text)
    y = date.today().year
    keep_years = {str(y - 1), str(y), str(y + 1)}
    holidays = {d: n for d, n in events.items() if d[:4] in keep_years}

    (BASE / 'data/공휴일.json').write_text(
        json.dumps(dict(sorted(holidays.items())), ensure_ascii=False, indent=1),
        encoding='utf-8')
    print(f'저장 완료: data/공휴일.json ({len(holidays)}일, {y-1}~{y+1}년)')

if __name__ == '__main__':
    main()
