import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from html import unescape

# GitHub repo root. The existing deals.json is kept here so no data folder is needed.
DATA = Path('deals.json')
UA = 'Mozilla/5.0 (compatible; TokkonBot/1.0; +https://github.com/mirumirumilutyyann/tokkon)'
SOURCES = {
    'seven_plaichi': 'https://www.sej.co.jp/cmp/plaichi.html',
    'seven_onigiri': 'https://www.sej.co.jp/cmp/ong2609.html',
    'family_index': 'https://www.family.co.jp/campaign.html',
    'lawson_sale': 'https://www.lawson.co.jp/recommend/sale/1buy1.html',
    'lawson_general': 'https://www.lawson.co.jp/recommend/sale/'
}


def fetch(url):
    req = Request(url, headers={'User-Agent': UA})
    with urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'ignore')


def text_lines(html):
    html = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', html, flags=re.I | re.S)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html = re.sub(r'</(p|div|li|h1|h2|h3|h4|section|article|tr)>', '\n', html, flags=re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = unescape(html)
    lines = []
    for x in html.splitlines():
        x = re.sub(r'\s+', ' ', x).strip()
        if x:
            lines.append(x)
    return lines


def ymd_from_jp(year, month, day):
    return f'{int(year):04d}-{int(month):02d}-{int(day):02d}'


def parse_range(s, default_year=None):
    # Supports 9/8〜9/14, 9月8日〜9月14日 and explicit years.
    m = re.search(
        r'(?:(20\d{2})[./年-])?(\d{1,2})[./月-](\d{1,2})日?\s*'
        r'(?:～|〜|-|–|~)\s*'
        r'(?:(20\d{2})[./年-])?(\d{1,2})[./月-](\d{1,2})日?', s
    )
    if not m:
        return None
    base_year = default_year or datetime.now(timezone.utc).year
    y1 = int(m.group(1) or base_year)
    y2 = int(m.group(4) or y1)
    return ymd_from_jp(y1, m.group(2), m.group(3)), ymd_from_jp(y2, m.group(5), m.group(6))


def parse_iso_range(s):
    m = re.search(
        r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s*'
        r'(?:～|〜|-|–|~)\s*'
        r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})', s
    )
    if not m:
        return None
    return ymd_from_jp(m.group(1), m.group(2), m.group(3)), ymd_from_jp(m.group(4), m.group(5), m.group(6))


def classify(title):
    if any(x in title for x in ['1個買うと', '1つ買うと', 'もらえる', '無料クーポン', '無料引換']):
        return '無料でもらえる'
    if any(x in title for x in ['値引', '円引', 'OFF', 'お買い得']):
        return '値引き'
    if 'クーポン' in title:
        return 'クーポン'
    return None


def clean_title(s):
    s = re.sub(r'^(NEW|一般|ファミペイ)\s*', '', s).strip()
    return s[:220]


def parse_lawson(html, url):
    lines = text_lines(html)
    out = []
    for i, line in enumerate(lines):
        if '開催期間' not in line:
            continue
        rng = parse_iso_range(line) or parse_range(line)
        if not rng:
            continue
        title = ''
        for j in range(i - 1, max(-1, i - 6), -1):
            cand = lines[j]
            if cand and cand not in ['お得なセール情報', 'Home', '商品・おトク情報'] and '開催期間' not in cand:
                title = cand
                break
        cat = classify(title)
        if not cat:
            continue
        start, end = rng
        out.append({
            'store': 'lawson', 'storeName': 'ローソン', 'buy': title,
            'get': '公式ページで内容を確認', 'date': f'{start}〜{end}',
            'category': cat, 'start': start, 'end': end,
            'source': url, 'auto': True
        })
    return out


def parse_family(html, url):
    lines = text_lines(html)
    out = []
    for i, line in enumerate(lines):
        rng = parse_range(line)
        if not rng:
            continue
        title = ''
        for j in range(i - 1, max(-1, i - 5), -1):
            cand = lines[j]
            if cand and not re.fullmatch(r'[\d/年月日（）（）曜日火水木金土月日〜～~:： ]+', cand):
                title = cand
                break
        title = clean_title(title)
        cat = classify(title)
        if not cat or len(title) < 5:
            continue
        start, end = rng
        if 'ファミペイ' in title or 'ファミペイ' in ' '.join(lines[max(0, i - 3):i + 1]):
            cat = 'アプリ限定'
        out.append({
            'store': 'family', 'storeName': 'ファミリーマート', 'buy': title,
            'get': '公式ページで内容を確認', 'date': f'{start}〜{end}',
            'category': cat, 'start': start, 'end': end,
            'source': url, 'auto': True
        })
    return out


def parse_seven_plaichi(html, url):
    lines = text_lines(html)
    out = []
    for i, line in enumerate(lines):
        if '発券期間' not in line:
            continue
        rng = parse_range(line)
        if not rng:
            continue
        title = ''
        for j in range(i - 1, max(-1, i - 11), -1):
            cand = lines[j]
            if any(x in cand for x in ['1個買うと', '1本買うと', '1つ買うと']):
                title = cand
                break
        if not title:
            continue
        m = re.search(r'「(.+?)」(?:を|の)?(?:1個|1本|1つ)買うと、(.+?)(?:無料|無料クーポン)', title)
        if m:
            buy, get = m.group(1), m.group(2)
        else:
            parts = re.split(r'(?:を|の)?(?:1個|1本|1つ)買うと、', title, maxsplit=1)
            buy = parts[0].replace('「', '').strip() if parts else title
            get = '無料クーポン'
        start, end = rng
        redeem = None
        for k in range(i + 1, min(len(lines), i + 9)):
            if '引換期間' in lines[k]:
                rr = parse_range(lines[k])
                if rr:
                    redeem = rr[1]
                    break
        date = f'購入：{start}〜{end}' + (f'　引換：{redeem}' if redeem else '')
        out.append({
            'store': 'seven', 'storeName': 'セブンイレブン', 'buy': buy[:180],
            'get': get[:180], 'date': date, 'category': '無料でもらえる',
            'start': start, 'end': end, 'redeemEnd': redeem,
            'source': url, 'auto': True
        })
    return out


def main():
    if not DATA.exists():
        raise SystemExit('deals.json not found in repository root')

    obj = json.loads(DATA.read_text(encoding='utf-8'))
    if isinstance(obj, list):
        obj = {'deals': obj}
    if not isinstance(obj, dict) or not isinstance(obj.get('deals'), list):
        raise SystemExit('deals.json format is not supported')

    # Preserve manually maintained entries; replace only auto-generated entries.
    base = [d for d in obj['deals'] if not d.get('auto')]
    auto = []
    parsers = [
        ('seven_plaichi', parse_seven_plaichi),
        ('family_index', parse_family),
        ('lawson_sale', parse_lawson),
    ]
    for key, fn in parsers:
        try:
            auto.extend(fn(fetch(SOURCES[key]), SOURCES[key]))
            print(f'[ok] {key}')
        except Exception as e:
            print(f'[warn] {key}: {e}')

    today = datetime.now(timezone.utc).date().isoformat()
    merged = {}
    for d in base + auto:
        if d.get('end') and d['end'] < today:
            continue
        key = (d.get('store'), d.get('buy'), d.get('start'), d.get('end'))
        merged[key] = d

    deals = list(merged.values())
    deals.sort(key=lambda d: (d.get('start', '9999-99-99'), d.get('store', ''), d.get('buy', '')))
    obj['deals'] = deals
    obj['updatedAt'] = datetime.now(timezone.utc).isoformat()
    obj['updateMode'] = 'scheduled-official-source-scan-root-deals-json'
    obj['sources'] = SOURCES
    DATA.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'official auto scan: {len(auto)} candidates; saved {len(deals)} active deals')


if __name__ == '__main__':
    main()
