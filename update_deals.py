import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from html import unescape

DATA=Path('data/deals.json')
UA='Mozilla/5.0 (compatible; TokkonBot/1.0; +https://github.com/mirumirumilutyyann/tokkon)'
SOURCES={
 'seven_plaichi':'https://www.sej.co.jp/cmp/plaichi.html',
 'seven_onigiri':'https://www.sej.co.jp/cmp/ong2609.html',
 'family_index':'https://www.family.co.jp/campaign.html',
 'lawson_sale':'https://www.lawson.co.jp/recommend/sale/1buy1.html',
 'lawson_general':'https://www.lawson.co.jp/recommend/sale/'
}

def fetch(url):
    req=Request(url,headers={'User-Agent':UA})
    with urlopen(req,timeout=30) as r:
        return r.read().decode('utf-8','ignore')

def text_lines(html):
    html=re.sub(r'<(script|style|noscript)[^>]*>.*?</\\1>',' ',html,flags=re.I|re.S)
    html=re.sub(r'<br\\s*/?>','\\n',html,flags=re.I)
    html=re.sub(r'</(p|div|li|h1|h2|h3|h4|section|article|tr)>','\\n',html,flags=re.I)
    html=re.sub(r'<[^>]+>',' ',html)
    html=unescape(html)
    lines=[]
    for x in html.splitlines():
        x=re.sub(r'\\s+',' ',x).strip()
        if x: lines.append(x)
    return lines

def ymd_from_jp(month,day):
    now=datetime.now(timezone.utc)
    return f'{now.year}-{int(month):02d}-{int(day):02d}'

def parse_range(s):
    m=re.search(r'(?:2026[./年-])?(\d{1,2})[./月-](\d{1,2})日?\s*(?:～|〜|-|–)\s*(?:2026[./年-])?(\d{1,2})[./月-](\d{1,2})日?',s)
    if not m:return None
    return ymd_from_jp(m.group(1),m.group(2)), ymd_from_jp(m.group(3),m.group(4))

def parse_iso_range(s):
    m=re.search(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s*(?:～|〜|-|–)\s*(20\d{2})[./-](\d{1,2})[./-](\d{1,2})',s)
    if not m:return None
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}',f'{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}'

def classify(title):
    if any(x in title for x in ['1個買うと','1つ買うと','もらえる','無料クーポン','無料引換']): return '無料でもらえる'
    if any(x in title for x in ['値引','円引','OFF','お買い得']): return '値引き'
    if 'クーポン' in title: return 'クーポン'
    return None

def clean_title(s):
    s=re.sub(r'^(NEW|一般|ファミペイ)\\s*','',s).strip()
    return s[:220]

def parse_lawson(html,url):
    lines=text_lines(html); out=[]
    for i,line in enumerate(lines):
        if '開催期間' not in line: continue
        rng=parse_iso_range(line)
        if not rng: continue
        # nearest previous meaningful line; skip labels
        title=''
        for j in range(i-1,max(-1,i-5),-1):
            cand=lines[j]
            if cand and cand not in ['お得なセール情報','Home','商品・おトク情報'] and '開催期間' not in cand:
                title=cand; break
        cat=classify(title)
        if not cat: continue
        start,end=rng
        out.append({'store':'lawson','storeName':'ローソン','buy':title,'get':'公式ページで内容を確認','date':f'{start}〜{end}','category':cat,'start':start,'end':end,'source':url,'auto':True})
    return out

def parse_family(html,url):
    lines=text_lines(html); out=[]
    for i,line in enumerate(lines):
        rng=parse_range(line)
        if not rng: continue
        # previous line is normally campaign title
        title=''
        for j in range(i-1,max(-1,i-4),-1):
            cand=lines[j]
            if cand and not re.fullmatch(r'[\d/年月日（）（）曜日火水木金土月日〜～:： ]+',cand):
                title=cand; break
        title=clean_title(title)
        cat=classify(title)
        if not cat or len(title)<5: continue
        start,end=rng
        # app-labelled campaigns get app category
        if 'ファミペイ' in lines[max(0,i-3):i+1] or 'ファミペイ' in title: cat='アプリ限定'
        out.append({'store':'family','storeName':'ファミリーマート','buy':title,'get':'公式ページで内容を確認','date':f'{start}〜{end}','category':cat,'start':start,'end':end,'source':url,'auto':True})
    return out

def parse_seven_plaichi(html,url):
    lines=text_lines(html); out=[]
    for i,line in enumerate(lines):
        if '発券期間' not in line: continue
        rng=parse_range(line)
        if not rng: continue
        title=''
        for j in range(i-1,max(-1,i-10),-1):
            cand=lines[j]
            if '1個買うと' in cand or '1本買うと' in cand or '1つ買うと' in cand:
                title=cand; break
        if not title: continue
        m=re.search(r'「(.+?)」(?:を|の)?(?:1個|1本|1つ)買うと、(.+?)(?:無料|無料クーポン)',title)
        if m:
            buy=m.group(1); get=m.group(2)
        else:
            parts=re.split(r'(?:を|の)?(?:1個|1本|1つ)買うと、',title,1)
            buy=parts[0].replace('「','').strip() if parts else title
            get='無料クーポン'
        start,end=rng
        redeem=None
        for k in range(i+1,min(len(lines),i+8)):
            rr=re.search(r'引換期間\\s*',lines[k])
            r2=parse_range(lines[k])
            if '引換期間' in lines[k] and r2: redeem=r2[1]; break
        date=f'購入：{start}〜{end}' + (f'　引換：{redeem}' if redeem else '')
        out.append({'store':'seven','storeName':'セブンイレブン','buy':buy[:180],'get':get[:180],'date':date,'category':'無料でもらえる','start':start,'end':end,'redeemEnd':redeem,'source':url,'auto':True})
    return out

def main():
    obj=json.loads(DATA.read_text(encoding='utf-8'))
    base=[d for d in obj.get('deals',[]) if not d.get('auto')]
    auto=[]
    for key,fn in [('seven_plaichi',parse_seven_plaichi),('family_index',parse_family),('lawson_sale',parse_lawson)]:
        try: auto.extend(fn(fetch(SOURCES[key]),SOURCES[key]))
        except Exception as e: print(f'[warn] {key}: {e}')
    # Keep only future/current and deduplicate by store+buy+start.
    today=datetime.now(timezone.utc).date().isoformat()
    merged={}
    for d in base+auto:
        if d.get('end') and d['end']<today: continue
        key=(d.get('store'),d.get('buy'),d.get('start'),d.get('end'))
        merged[key]=d
    deals=list(merged.values())
    deals.sort(key=lambda d:(d.get('start','9999-99-99'),d.get('store',''),d.get('buy','')))
    obj['deals']=deals
    obj['updatedAt']=datetime.now(timezone.utc).isoformat()
    obj['updateMode']='scheduled-official-source-scan'
    obj['sources']=SOURCES
    DATA.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'official auto scan: {len(auto)} candidates; saved {len(deals)} active deals')

if __name__=='__main__': main()
