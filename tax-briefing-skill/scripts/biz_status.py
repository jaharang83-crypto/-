#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
biz_status.py — 국세청 사업자등록 상태조회 (공공데이터포털 무료 API)
기능: 거래처.csv의 사업자번호를 일괄 조회 →
  ① 과세유형(일반/간이/면세) 태그 자동 갱신  ② 휴·폐업 감지 → [폐업] 태그 + 리포트
사용: NTS_API_KEY 환경변수 또는 config.json의 nts_api_key 설정 후
  python3 biz_status.py            # 조회 + CSV 태그 갱신 + 변경 리포트
  python3 biz_status.py --dry      # 조회만 (CSV 수정 안 함)
API 신청: 공공데이터포털(data.go.kr) → "국세청_사업자등록정보 진위확인 및 상태조회 서비스" (무료)
"""
import json, csv, io, os, re, sys, urllib.request
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE/'data/config.json').read_text(encoding='utf-8'))
KEY = os.environ.get('NTS_API_KEY') or CONFIG.get('nts_api_key', '')
API = 'https://api.odcloud.kr/api/nts-businessman/v1/status?serviceKey='
TAX_TAGS = {'일반과세':'일반과세', '간이과세':'간이과세', '면세':'면세'}

def norm_tax(tax_type: str) -> str:
    """API tax_type 문자열 → 태그"""
    if '간이' in tax_type: return '간이과세'
    if '면세' in tax_type: return '면세'
    if '일반' in tax_type: return '일반과세'
    return ''  # 비영리/고유번호 등은 태그 미부여

def query(biz_list):
    """100건 단위 일괄 조회"""
    results = {}
    for i in range(0, len(biz_list), 100):
        batch = biz_list[i:i+100]
        req = urllib.request.Request(
            API + KEY, method='POST',
            data=json.dumps({'b_no': batch}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        for item in data.get('data', []):
            results[item['b_no']] = item
    return results

def main():
    dry = '--dry' in sys.argv
    if not KEY:
        print('⚠ API 키가 없습니다. data.go.kr에서 발급 후 config.json의 nts_api_key에 넣어주세요.')
        sys.exit(1)

    rows = []
    with io.open(BASE/'data/거래처.csv', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    targets = {re.sub(r'\D','',r['사업자번호']): r for r in rows
               if len(re.sub(r'\D','',r.get('사업자번호',''))) == 10}
    print(f'조회 대상: {len(targets)}곳')
    res = query(list(targets.keys()))

    changes, closed = [], []
    for bno, row in targets.items():
        item = res.get(bno)
        if not item: continue
        tags = [t for t in row['태그'].split(';') if t]
        stt = item.get('b_stt', '')          # 계속사업자/휴업자/폐업자
        tax = norm_tax(item.get('tax_type',''))
        # ① 휴·폐업 감지
        if stt and stt != '계속사업자' and '폐업' not in tags and '휴업' not in tags:
            mark = '폐업' if '폐업' in stt else '휴업'
            tags.append(mark)
            closed.append(f"- **{row['거래처명']}** → {stt} (폐업일 {item.get('end_dt','-')}) — 수임 종료·부가세 폐업신고 확인")
        # ② 과세유형 변경 감지 (수동 태그 존중: 기존과 다를 때만 교체)
        cur = next((t for t in tags if t in TAX_TAGS), '')
        if tax and cur != tax:
            if cur: tags.remove(cur)
            tags.append(tax)
            changes.append(f"- **{row['거래처명']}**: 과세유형 {cur or '미지정'} → **{tax}** (홈택스 기준)")
        row['태그'] = ';'.join(dict.fromkeys(tags))

    # 리포트 저장 (briefing.py가 다음 브리핑에 자동 첨부)
    report = ''
    if closed:  report += '### 휴·폐업 감지\n' + '\n'.join(closed) + '\n'
    if changes: report += '### 과세유형 변경\n' + '\n'.join(changes) + '\n'
    (BASE/'data/상태변경리포트.md').write_text(
        (f'*조회일 {date.today().isoformat()}*\n' + report) if report else '', encoding='utf-8')
    print(report or '변경 사항 없음')

    if not dry and report:
        with io.open(BASE/'data/거래처.csv', 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)
        print('거래처.csv 태그 갱신 완료')

if __name__ == '__main__':
    main()
