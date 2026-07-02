#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
briefing.py — 세무 기한 자동 브리핑 생성 엔진 (구민이 시스템용)
사용: python3 briefing.py [--date YYYY-MM-DD]
출력: config.json의 vault_briefing_dir 에 '세무브리핑_YYYY-MM-DD.md' 생성 + 표준출력
"""
import json, csv, sys, io, os
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE/'data/config.json').read_text(encoding='utf-8'))
DOW = ['월','화','수','목','금','토','일']

# ── 데이터 로드 ──────────────────────────────────
def load_clients():
    out = []
    with io.open(BASE/'data/거래처.csv', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            row['태그목록'] = [t.strip() for t in (row.get('태그','')).split(';') if t.strip()]
            out.append(row)
    return out

def load_master():
    return json.loads((BASE/'data/세무일정마스터.json').read_text(encoding='utf-8'))['events']

def load_holidays():
    p = BASE/'data/공휴일.json'
    if p.exists():
        return set(json.loads(p.read_text(encoding='utf-8')).keys())
    return set()

def load_done():
    p = BASE/'data/완료기록.csv'
    done = set()
    if p.exists():
        with io.open(p, encoding='utf-8-sig') as f:
            for row in csv.reader(f):
                if row and row[0] != 'key': done.add(row[0])
    return done

# ── 날짜 계산 ──────────────────────────────────
def last_day(y, m):
    return (date(y+(m//12), (m%12)+1, 1) - timedelta(days=1)).day

def shift_bizday(d, holidays):
    """주말·공휴일이면 다음 영업일로 순연"""
    moved = False
    while d.weekday() >= 5 or d.isoformat() in holidays:
        d += timedelta(days=1); moved = True
    return d, moved

def occurrences(today, events, holidays, horizon=70):
    out = []
    for e in events:
        dates = []
        if e['freq'] == 'monthly':
            for i in range(4):
                m0 = today.month - 1 + i
                y, m = today.year + m0//12, m0%12 + 1
                dd = last_day(y, m) if e['day'] == 'last' else e['day']
                dates.append(date(y, m, dd))
        else:
            for y in (today.year, today.year+1):
                dates.append(date(y, e['m'], e['d']))
        for dt in dates:
            adj, moved = shift_bizday(dt, holidays)
            dday = (adj - today).days
            if dday < 0 or dday > horizon: continue
            win_open = False
            if e.get('winStart'):
                ws = date(dt.year, e['winStart']['m'], e['winStart']['d'])
                win_open = ws <= today <= adj
            out.append({**e, 'date': adj, 'orig': dt, 'moved': moved,
                        'dday': dday, 'win_open': win_open,
                        'key': f"{e['id']}@{dt.isoformat()}"})
    out.sort(key=lambda o: o['date'])
    return out

# ── 거래처 매칭 (OR + AND + 제외) ──────────────
def match(e, clients):
    tags, alls, excl = e.get('tags',[]), e.get('all',[]), e.get('excl',[])
    L = clients
    if alls:   L = [c for c in L if all(t in c['태그목록'] for t in alls)]
    elif tags: L = [c for c in L if any(t in c['태그목록'] for t in tags)]
    if excl:   L = [c for c in L if not any(t in c['태그목록'] for t in excl)]
    return L

# ── 브리핑 생성 ─────────────────────────────────
def build(today):
    clients = load_clients()
    occ = occurrences(today, load_master(), load_holidays())
    done = load_done()
    closed = [o for o in occ if o['key'] in done]
    live   = [o for o in occ if o['key'] not in done]
    urgent = [o for o in live if o['dday'] <= 7]
    apply_ = [o for o in live if o['win_open'] and o not in urgent]
    soon   = [o for o in live if 7 < o['dday'] <= 30 and o not in apply_]
    later  = [o for o in live if o['dday'] > 30 and o not in apply_]

    L = []
    L.append('---')
    L.append(f'date: {today.isoformat()}')
    L.append(f'tags: [세무브리핑, 구민이]')
    L.append(f'긴급: {len(urgent)}')
    L.append('---')
    L.append(f'# 📋 세무일정 브리핑 — {today.year}.{today.month}.{today.day} ({DOW[today.weekday()]})')
    L.append(f'> 거래처 {len(clients)}곳 기준 자동 생성 · 완료 처리: `완료기록.csv`에 key 추가 또는 구민이에게 "OO 완료 처리" 요청')
    L.append('')

    def section(title, items, show_clients=True):
        L.append(f'## {title} ({len(items)}건)')
        if not items:
            L.append('- 해당 없음'); L.append(''); return
        for o in items:
            dd = 'D-DAY' if o['dday']==0 else f"D-{o['dday']}"
            mv = f" *(원기한 {o['orig'].month}/{o['orig'].day} → 영업일 순연)*" if o['moved'] else ''
            L.append(f"- [ ] **{dd}** `{o['date'].month}/{o['date'].day}({DOW[o['date'].weekday()]})` "
                     f"[{o['type']}] {o['title']}{mv}  `key:{o['key']}`")
            if o.get('desc'): L.append(f"    - {o['desc']}")
            if show_clients:
                cl = match(o, clients)
                if cl:
                    names = ', '.join(c['거래처명'] for c in cl[:25])
                    more = f" 외 {len(cl)-25}곳" if len(cl) > 25 else ''
                    L.append(f"    - 🎯 대상 {len(cl)}곳: {names}{more}")
                elif o.get('tags') or o.get('all'):
                    L.append(f"    - ⚠ 매칭 거래처 0곳 — 태그 확인 필요")
        L.append('')

    section('🔴 긴급 — 7일 이내', urgent)
    section('📮 신청기간 진행 중 ★', apply_)
    section('🟠 주의 — 30일 이내', soon)
    section('🔵 예정 — 70일 이내', later)
    if closed:
        L.append(f'## ✅ 완료 ({len(closed)}건)')
        for o in closed:
            L.append(f"- [x] {o['date'].month}/{o['date'].day} {o['title']}")
        L.append('')

    # 상태변경 리포트가 있으면 첨부
    diff = BASE/'data/상태변경리포트.md'
    if diff.exists() and diff.stat().st_size > 0:
        L.append('## 🚨 국세청 상태 변경 감지 (biz_status.py)')
        L.append(diff.read_text(encoding='utf-8').strip())
        L.append('')
    return '\n'.join(L)

def main():
    today = date.today()
    if '--date' in sys.argv:
        today = date.fromisoformat(sys.argv[sys.argv.index('--date')+1])
    md = build(today)
    out_dir = Path(os.path.expanduser(CONFIG.get('vault_briefing_dir', '.')))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'세무브리핑_{today.isoformat()}.md'
    out.write_text(md, encoding='utf-8')
    print(md)
    print(f'\n[저장됨] {out}', file=sys.stderr)

if __name__ == '__main__':
    main()
