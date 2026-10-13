#!/usr/bin/env python3
"""Categorize locally extracted NFS16 text into one exclusive, revisable work queue.

Game-owned text remains only under the ignored work/ directory. Existing
translations/menu/*.csv are read-only inputs. Classification is heuristic,
never evidence of confirmed UI usage. Overrides are optional in
translations/category-overrides.csv with string_id,category_id,subcategory.
"""
import argparse,csv,re,json,hashlib,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/"work/locale-extract/en-strings.csv"
MENU=ROOT/"translations/menu"
OVERRIDES=ROOT/"translations/category-overrides.csv"
OUTPUT=ROOT/"work/localization-plan"
CATEGORY={
"00_menu":("기존 메뉴 번역","기존 6개 CSV 번역, 재검수 없이 유지"),
"01_ui":("기타 UI·HUD","남은 버튼, 수치, HUD, 조작"),
"02_notices":("시스템·온라인 안내","오류, 확인창, 게임 접속/세이브 안내"),
"03_tutorial":("튜토리얼·도움말","시스템 안내, 로딩 팁, 조작법"),
"04_missions":("미션·도전과제","목표 조건, 도전과제, 보상 및 해금"),
"05_events":("이벤트·코스명","레이스, 드리프트 등 종목과 코스명"),
"06_cars":("차량·차종명","차량 제조사, 모델 및 고유명"),
"07_parts":("부품·아이템·랩핑","자동차 부품, 휠, 커스터마이징 아이템"),
"08_tuning":("튜닝·부품 설명","성능과 조작감, 부품 기능 설명"),
"09_police":("경찰·추격 대사","정차 지시, 추격 중 경찰 음성"),
"10_story":("스토리·영상·전화 대사","타임코드 대사, 전화 통화 및 일반 화자 대사"),
"11_social":("SNS·메시지","게시물, 팔로우, 문자 메시지, SNS"),
"12_music":("음악·권리 표기","트랙·음원 크레딧 및 라이선스"),
"13_credits":("제작진·크레딧","제작진 역할, 명단, 조직·스튜디오"),
"14_dev":("개발·테스트 문자열","미사용 후보, 내부 ID, 임시 문자열"),
"15_legal":("상표권·법률·라이선스","차량 상표, 오픈소스 법적 고지, 보통 원문 유지"),
"16_locations":("지역·장소명","레이스 장소, 주유소, 지형·지명"),
"17_names":("인명·고유명·제목 후보","인물, 계정명, 이벤트 타이틀, 상호명 등 원문 유지 여부 검토"),
"18_review":("미분류·문맥 확인","자동 분류하기 어려운 문장과 상태 안내"),
}
SCOPE={"main":"메인","settings":"설정","garage":"차고","events":"이벤트","social":"소셜","system":"공통 버튼"}
HEADERS=("string_id","category_id","category_name","subcategory","source_text","ko_text",
         "status","confidence","reason","flags","reuse_key","duplicate_count","needs_context","notes")
SUMMARY=("priority","category_id","category_name","ids","unique_source_texts","translated",
         "reviewed","not_started","high_confidence","needs_context","description")
def r(pattern):return re.compile(pattern,re.I)
TIMED=r(r"\{\d+(?:\.\d+)?-\d+(?:\.\d+)?\}")
VARIABLE=r(r"\{\d+(?::[^{}\n]*)?\}")
MARKUP=r(r"<[\w/][^<>]*>")
DEV=r(r"^(?:ID_ITEMS_|ID_ONLINE_|ID_[A-Z0-9_]{5,}|Traffic(?:Car)?[_-]|(?:X|Y|Z)ROTATION(?:NEG|POS)|POV\d+(?:NORTH|SOUTH|EAST|WEST)|[LR](?:UP|DOWN|LEFT|RIGHT|TRIGGER|THUMB)|AXIS\d+[XY]|XBUTTON\d+|TestText|TestVoice|TestRace|PLACEHOLDER|\*Cut\*)")
MUSIC=r(r"Published by|Recording courtesy of|Performed by|Written by|under license from|Music Publishing|Music Licensing|Copyright Control|Music courtesy|Appears courtesy of|arrangement with|Soundtrack|Performed and composed")
CREDIT=r(r"^(?:(?:Senior |Junior |Executive |Assistant |Lead |Global |Head of |Vice President |Associate )?(?:Audio|Art|Design|Level|Environment|Technical|UI|VFX|QA|Game|Gameplay|Rendering|Localization|Internationalization|Online|Network|Marketing|Project|Production|Software|Systems?|Operations|Support|Quality|3D|Cinematic|Legal|Business|Development) (?:Engineers?|Engineering|Artists?|Leads?|Directors?|Managers?|Designers?|Producers?|Team|Specialists?|Programmers?)|(?:Creative |Technical |Audio |Art )?(?:Director|Producer|Supervisor)s?$|SPECIAL THANKS|DEVELOPMENT TEAM|THE TEAM|PRODUCTION BABIES|MAIN CAST|SUPPORTING CAST|QUALITY ASSURANCE|CREDITS)$")
POLICE=r(r"\b(?:pull over|pull (?:your|that|the) (?:car|vehicle) over|stop (?:your|that|this|the) (?:car|vehicle|race)|stop (?:right|now|immediately)|slow (?:your|that) (?:car|vehicle)|slow down|give it up|under arrest|suspect|police pursuit|pursuit(?:s)?|spike strip|you're busted|I repeat|roadblock|cop chase|impound)\b|^(?:You in the|Driver in the|Driver of the|Porsche driver|Corvette driver)")
SOCIAL=r(r"^(?:@[A-Za-z0-9_]+|#\w+)|\b(?:new follower|friend request|liked your|commented on|retweeted|posted (?:this|a)|shared (?:your|a) (?:post|photo)|social feed|hashtag|follow me)\b")
PART=r(r"\b(?:air filter|air intake|body kit|bumper|caliper|camshaft|clutch|coilover|cooling|cylinder head|differential|diffuser|drivetrain|ECU|exhaust|fender|fuel injector|fuel pump|gearbox|grille|hood|intercooler|intake manifold|license plate|mirror|nitrous|oil cooler|rim|splitter|side skirt|spoiler|suspension|sway bar|tail(?:light|lamp)|tire|turbo|supercharger|wheel|wing|wrap|paint|decal|tint|canard|brake|manifold|catalytic)\b")
PART_PREF=r(r"^(?:Stock |Race Style |Street Style |Sport |Elite |Aftermarket |Forged |Seibon |Varis |RWB |Rocket Bunny |Liberty Walk |Toyo Tires |SSR |Work Wheels |HRE |Brembo |Custom Wrap |Kustom )")
TUNING=r(r"\b(?:suspension|camshaft|turbocharger|supercharger|damping|spring stiffness|brake bias|aerodynamic|nitrous|exhaust|horsepower|torque|RPM|ride height|grip|drift|engine|fuel|tire pressure|transmission|ECU|injectors|intercooler|steering sensitivity|anti.roll)\b")
CARS=r(r"^(?:BMW|Mercedes(?:-AMG|-Benz)?|Nissan|Porsche|Toyota|Honda|Ford|Volkswagen|Subaru|Ferrari|Lamborghini|Mazda|Dodge|Volvo|Mitsubishi|McLaren|Chevrolet|Lotus|Acura|Pagani|Scion|Buick|Infiniti|Chrysler|Audi|Jaguar|Koenigsegg|GMC|Lexus|Shelby|Cadillac|Mini)\b|^(?:GT-?R|RX-?7|MX-?5|M\d|911 Carrera|Aventador|Huracan|BRZ|GT86|Impreza|Golf GTI|F40|S2000|NSX|Supra|240SX|180SX|Sil80|RSR)(?:\s|$)")
MISSION=r(r"^(?:Win|Complete|Finish|Beat|Earn|Get|Reach|Drive|Drift|Score|Perform|Play|Collect|Jump|Meet|Unlock|Take|Find|Equip|Upgrade|Place|Escape|Outrun|Dodge|Keep|Stay|Avoid|Hit|Destroy|Obtain|Use|Share|Like|Follow|Own|Start|Lose|Achieve|Survive|Defeat|Overtake|Enter|Purchase|Join|Return|Answer)\s+")
MISSION_LABEL=r(r"\b(?:Objectives?|Daily Challenges|Challenge Complete|Win .*Event|Target Score|Score More Than|Rank Reward)\b")
EVENT=r(r"^(?:\*Cut\*)?(?:Drift |Sprint Race|Circuit Race|Drag Race|Time Trial|Time Attack|Speed Run|Speedlist|Gymkhana|Touge|Outrun Race|Freestyle Drift|Special Stage Race|Race |Eddie's Challenge)\b")
NOTICE=r(r"\b(?:Are you sure|Would you like|Do you want|Cannot |Can't |Could not |Failed to |Unable to |Please (?:try|select|wait)|not available|unavailable|already exists|not enough|insufficient|no free slots|session full|connection lost|disconnected|service unavailable|server|reconnect|reset your)\b")
UI=r(r"^(?:Press |Skip |Rotate |Show |Hide |Enable |Disable |Save |Load |Reset |Apply |Cancel |Back|Continue|Exit|Retry|Confirm|OK|No|Yes|Menu|New |Switch |View |Toggle |Camera|Move |Look |Mute|Unmute|Close |Open |Delete |Edit |Redo|Undo|Copy |Paste |Select |Start |Next |Previous |Photo|Garage|Options|Graphics|Audio|Display|Handling|Map |Stats|Scores|Top |RANK|REP|BANK|COP|Speedometer|GPS|Keyboard|Button|LAP|POINTS|TOTAL|BEST|MINS|HRS|MPH|KM/H)$")
TUTORIAL=r(r"\b(?:to (?:access|enable|unlock|earn|open|continue|reveal|equip|move)|you (?:can|will|must|need|may|have to)|use (?:the|your)|when (?:you|in)|allows? you|these (?:are|can|will)|here(?:'s| is) how|tip:|press (?:a|the|your)|the (?:game|map|menu|phone|garage)|higher REP)\b")
STORY=r(r"^(?:Yo[,! ]|Hey[,! ]|A'?ight|Alright|Bro[,! ]|Man[,! ]|Dude[,! ]|Yeah[,! ]|Look[,! ]|Listen[,! ]|Well[,! ]|I'm |I am |I got |I've |I'll |We're |We got |Remember |Check this|What's up|OK,|Okay,|Oh man|Congratulations|Nice |Whoa|Wow[! ,.])")
LEGAL=r(r"(?:trademarks? of|trademarks? and|trademarks? used|associated marks|used under approval|used by permission|emblems and designs|under license|patent|intellectual property|provided by the copyright|copyright holders|redistributions? in|conditions and the following disclaimer|THE SOFTWARE IS PROVIDED|software included in this product|licensed under|all rights reserved|the License is distributed|GNU (?:GENERAL|LESSER)|LGPL|MIT License|BSD License|Disclaimer|Commercial Use License|copyrighted software|privacy policy|EA collects certain information)")
LOCATION=r(r"(?:Hill|Heights|Bay|Police Station|Gas Station|Bridge|River|Valley|County|Park|Plaza|Mall|Beach|Boulevard|Freeway|Road|Stadium|Airport|Harbor|Docks|District|Intersection|Highway|Mountain Pass)$")
AFTERMARKET=r(r"^(?:Kumho Tires|Rotiform|Vossen|ADV\.?1|BBS |Work Meister|Chargespeed|Fifteen52|HRE |SSR |Rays |RAYS |Volk |Toyo Tires|Nitto |Brembo |APR |Varis |Seibon |Rocket Bunny|Liberty Walk|Nismo |D2 |KW )")
CREDIT_TAIL=r(r"\b(?:Senior (?:Manager|Director|Engineer|Designer)|Project Managers?|Compliance (?:Manager|Lead|Project)|Artist|Director|Producer|Engineering|Software Engineer|Specialist|QA Engineer|Designers?|Managers?|Supervisors?|Leads?|Programmer|Coordinator|Developers?)s?$")
SOCIAL_TAG=r(r"(?:^|[\s.,!])#[A-Za-z][A-Za-z0-9_]{2,}")
SOUND_TITLE=r(r"(?:(?:feat(?:uring)?\.)\s*[A-Za-z]|^[\uFFFD]{1,2}[^,;]+[\uFFFD]{1,2}(?:\s+feat\b)?)")
FORMATS_ONLY=r(r"^(?:\$?\{\d+(?::[^}]+)?\}(?:\s*[+\-/:]?\s*\$?\{\d+(?::[^}]+)?\})*|[\w]+(?: XPOS| XNEG| YPOS| YNEG))$")
def category(text):
 s=text.strip();n=len(s)
 if not s:return "14_dev","빈 문자열","높음","empty"
 if DEV.search(s) or s in ("UNDEFINED","HEADER TEXT","PLACEHOLDER"):return "14_dev","내부 ID·더미","높음","internal ID/placeholder"
 if s in ("DEVELOPMENT QA","QUALITY ASSURANCE","SOFTWARE ENGINEERING","Database Services"):return "13_credits","제작진 부서명","높음","staff/development department"
 if MUSIC.search(s):return "12_music","라이선스/음악 크레딧","높음","music credit language"
 if LEGAL.search(s):return "15_legal","상표·저작권·법률 문서","높음","legal/trademark licensing"
 if FORMATS_ONLY.fullmatch(s):return "14_dev","변수·형식 코드만 존재","높음","format tokens without translatable words"
 if SOUND_TITLE.search(s) and len(s)<140:return "12_music","곡명·피처링 후보","중간","track/performer title"
 if (s.startswith(("“","‘","\"")) and s.endswith(("”","’","\"")) and n<120):return "12_music","음악 제목 후보","중간","quoted title"
 if CREDIT.search(s):return "13_credits","제작진 직책","높음","staff role phrase"
 if len(s)<85 and not re.search(r"[!?{}]",s) and CREDIT_TAIL.search(s):
  return "13_credits","제작진 직책 후보","중간","staff role suffix"
 if TIMED.search(s):return "10_story","타임코드 대사","높음","timed subtitle"
 if (POLICE.search(s) or re.match(r"^(?:Driver\. Pull|(?:Miata|Porsche|Challenger|Corvette|BMW|Supra|Camaro), stop)",s,re.I)) and not MISSION.match(s) and n<=220 and not TUTORIAL.search(s) and not s.lower().startswith(("2 kinds of","learn the difference","the cops will","police stations are")):
  return "09_police","경찰 경고·추격","높음","police dialogue pattern"
 if SOCIAL.search(s) or SOCIAL_TAG.search(s):return "11_social","SNS 메시지","중간","social marker/hashtag"
 if n>70 and TUNING.search(s) and ("," in s or "." in s) and not MISSION.match(s):return "08_tuning","기술·성능 설명","중간","tuning explanation"
 if n<=95 and (PART.search(s) or PART_PREF.search(s) or AFTERMARKET.search(s)) and not MISSION.match(s) and not s.endswith((".","!","?")) and not s.lower().startswith(("you ","this ","your ","there ")):
  return "07_parts","장착품·랩핑·부품명","높음" if PART.search(s) else "중간","part/item label"
 if CARS.search(s) and n<=75 and not MISSION.match(s) and not s.endswith((".","!","?")) and "," not in s:return "06_cars","제조사·차종","중간","vehicle/model pattern"
 if (MISSION.match(s) or MISSION_LABEL.search(s)) and n<=240:
  if n<=25 and re.match(r"^(?:Start|Get|Save|Play|Apply|Enter|Join|Select) [A-Za-z]{1,12}$",s):
   return "01_ui","행동 버튼 후보","중간","short verb label"
  return "04_missions","미션·목표","중간","objective/achievement verb"
 if EVENT.search(s) and n<=85 and not s.endswith((".","!","?")):
  return "05_events","종목/코스명","중간","event title pattern"
 if (NOTICE.search(s) or re.search(r"not allowed to access the online features",s,re.I)) and n<=300:return "02_notices","서버·알림·확인","중간","notification phrase"
 if n<=165 and re.match(r"^(?:Retrieving |Downloading |Uploading |Connecting |Loading |Waiting |Searching |Finding |Share/Unshare|No more |Your game |This player |You downloaded |New Personal Best!|Event Starts In|Event ends in)",s,re.I):
  return "02_notices","진행 상태·온라인 알림","중간","progress/status notification"
 if UI.search(s):return "01_ui","버튼·HUD","중간","known short UI term"
 if n<=55 and (re.search(r"(?:km/h|mph|km|lap|pts|RPM|0-100|0-60|target.*pts|distance behind)",s,re.I) or re.match(r"^\$?\{\d+:[^}]+\}",s)):
  return "01_ui","속도·거리·경기 HUD 후보","중간","short formatted HUD value"
 if TUTORIAL.search(s) and n>=75:return "03_tutorial","플레이 시스템 설명","중간","tutorial structure"
 if STORY.search(s) or (n>110 and re.search(r"\b(?:I'm|I've|we're|my|dude|man|ya|you'll|we'll|ain't)\b",s,re.I)):return "10_story","화자 미확인 대사","낮음","informal speech"
 if n<=70 and LOCATION.search(s) and not MISSION.match(s) and not s.lower().startswith(("run ","meet ","visit ","race ","go ","get ","find ","drive ")) and not s.endswith((".","!","?")):
  return "16_locations","도시·장소명 후보","중간","location suffix"
 if n<=46 and s==s.upper() and re.search(r"[A-Z]",s) and s.count(" ")<=4:return "01_ui","짧은 UI/랭크명 후보","낮음","uppercase short label"
 if n<=80 and not re.search(r"[!?;:{}\n\r]",s) and len(s.split())<=6 and (s[:1].isupper() or s[:1].isdigit()):
  if re.search(r"\b(?:Station|Road|Bridge|Mall|Park|Harbor|Hotel|Heights|Valley|County)\b",s,re.I) and not s.lower().startswith(("run ","meet ","visit ","race ","go ","get ","find ","drive ")):
   return "16_locations","장소명 후보","중간","location word"
  if len(s.split())==1:
   return "17_names","인명·캐릭터·단일 고유명사 후보","낮음","single name/title"
  if len(s.split())<=3:
   return "17_names","이벤트·인명·회사명 후보","낮음","short proper title"
  return "17_names","긴 고유명사·타이틀 후보","낮음","multi-word title"
 if n<=65 and VARIABLE.search(s):
  return "01_ui","HUD 숫자/플레이스홀더 후보","낮음","formatted short HUD string"
 if n>=160 and TUNING.search(s):
  return "08_tuning","브랜드·차량 설명 후보","낮음","long automotive explanation"
 return "18_review","기타 문맥 확인","낮음","no reliable rule"
def flags(s):
 terms=[]
 if TIMED.search(s):terms.append("타임코드")
 if VARIABLE.search(s):terms.append("변수")
 if MARKUP.search(s):terms.append("마크업")
 if "\n" in s or "\r" in s:terms.append("줄바꿈")
 if re.search(r"[\uE000-\uF8FF]",s):terms.append("게임기호")
 if "��" in s or "\ufffd" in s:terms.append("인코딩 확인")
 if len(s)>200:terms.append("장문")
 return ";".join(terms)
def writecsv(path,headers,rows):
 with path.open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=headers,lineterminator="\r\n")
  w.writeheader();w.writerows(rows)
def load_menu():
 out={}
 for scope in SCOPE:
  path=MENU/(scope+".csv")
  with path.open(encoding="utf-8-sig",newline="") as f:
   r=csv.DictReader(f)
   for item in r:
    sid=item["string_id"].upper().replace("0X","")
    if sid in out:raise ValueError("Duplicate existing menu ID "+sid)
    out[sid]=item
 return out
def load_category_drafts():
 out={}
 directory=ROOT/"translations/categories"
 if not directory.exists():return out
 fields=("string_id","scope","source_text","ko_text","status","notes")
 for path in sorted(directory.glob("*.csv")):
  with path.open(encoding="utf-8-sig",newline="") as file:
   reader=csv.DictReader(file)
   if tuple(reader.fieldnames or [])!=fields:
    raise ValueError(f"Unexpected category translation columns: {path}")
   for item in reader:
    sid=item["string_id"].strip().upper().replace("0X","")
    if sid in out:raise ValueError("Duplicate category translation ID "+sid)
    if item["scope"] not in CATEGORY or item["scope"]=="00_menu":
     raise ValueError("Unknown category translation scope "+item["scope"])
    out[sid]=item
 return out

def overrides(path):
 if not path.is_file():return {}
 d={}
 with path.open(encoding="utf-8-sig",newline="") as f:
  reader=csv.DictReader(f)
  if reader.fieldnames!=["string_id","category_id","subcategory"]:raise ValueError("Override header mismatch")
  for x in reader:
   sid=x["string_id"].upper().replace("0X","")
   if sid in d or x["category_id"] not in CATEGORY:raise ValueError("Invalid override "+sid)
   d[sid]=(x["category_id"],x["subcategory"])
 return d
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--source",type=Path,default=SOURCE)
 ap.add_argument("--out",type=Path,default=OUTPUT)
 ap.add_argument("--overrides",type=Path,default=OVERRIDES)
 args=ap.parse_args()
 with args.source.open(encoding="utf-8-sig",newline="") as f:
  rows=list(csv.DictReader(f))
 if len(rows)<1000 or len({r["string_id"] for r in rows})!=len(rows):raise ValueError("Unexpected source inventory")
 menu=load_menu(); category_drafts=load_category_drafts(); by_override=overrides(args.overrides)
 known={r["string_id"].upper() for r in rows}
 if set(menu)-known or set(by_override)-known or set(category_drafts)-known:
  raise ValueError("Unknown menu, category translation or override ID")
 if set(menu)&set(category_drafts):
  raise ValueError("A string ID occurs in both the menu and category translation CSVs")
 freq=collections.Counter(r["source_text"] for r in rows)
 out={k:[] for k in CATEGORY}
 for orig in rows:
  sid=orig["string_id"].upper()
  english=orig["source_text"]
  if sid in menu:
   m=menu[sid]
   if m["source_text"]!=english:raise ValueError("Menu English mismatch for "+sid)
   cat,sub,conf,why="00_menu",SCOPE[m["scope"]],"확정","existing menu CSV"
   translated,status,note=m["ko_text"],m["status"],m["notes"]
  else:
   cat,sub,conf,why=category(english)
   translated,status,note="","미착수",""
  if sid in by_override:
   if sid in menu and by_override[sid][0]!="00_menu":raise ValueError("Cannot override existing menu category")
   cat,sub=by_override[sid];conf,why="확정","manual override"
  if sid in category_drafts:
   reviewed=category_drafts[sid]
   if reviewed["source_text"]!=english or reviewed["scope"]!=cat:
    raise ValueError("Category translation/source mismatch for "+sid)
   translated,status,note=reviewed["ko_text"],reviewed["status"],reviewed["notes"]
   why="editable category translation CSV, review status preserved"
  note=note or ("번역/원문 유지 검토" if cat in ("12_music","13_credits","14_dev","15_legal","17_names") else "")
  row={
   "string_id":"0x"+sid,"category_id":cat,"category_name":CATEGORY[cat][0],"subcategory":sub,
   "source_text":english,"ko_text":translated,"status":status,
   "confidence":conf,"reason":why,"flags":flags(english),
   "reuse_key":hashlib.sha1(english.encode("utf-8")).hexdigest()[:12],
   "duplicate_count":freq[english],
   "needs_context":"예" if conf in ("낮음","중간") or cat in ("10_story","11_social","17_names","18_review") else "아니요",
   "notes":note
  }
  out[cat].append(row)
 dest=args.out;dest.mkdir(parents=True,exist_ok=True)
 byfolder=dest/"by-category";byfolder.mkdir(exist_ok=True)
 # Old versions may use different IDs. Purge only stale generated CSVs.
 for old_file in byfolder.glob("*.csv"):
  if old_file.stem not in CATEGORY:old_file.unlink()
 all_rows=[];summary=[]
 for priority,(cat,(label,description)) in enumerate(CATEGORY.items()):
  data=out[cat]
  data.sort(key=lambda item:(item["subcategory"],item["source_text"].casefold(),item["string_id"]))
  writecsv(byfolder/(cat+".csv"),HEADERS,data)
  all_rows.extend(data)
  summary.append({
    "priority":priority,"category_id":cat,"category_name":label,"ids":len(data),
    "unique_source_texts":len({r["source_text"] for r in data}),
    "translated":sum(bool(r["ko_text"]) for r in data),
    "reviewed":sum(r["status"]=="검수완료" for r in data),
    "not_started":sum(r["status"]=="미착수" for r in data),
    "high_confidence":sum(r["confidence"] in ("확정","높음") for r in data),
    "needs_context":sum(r["needs_context"]=="예" for r in data),
    "description":description
  })
 if len(all_rows)!=len(rows):raise AssertionError("Categorized string counts differ from source")
 writecsv(dest/"all-strings.csv",HEADERS,all_rows)
 writecsv(dest/"summary.csv",SUMMARY,summary)
 subgroups=collections.defaultdict(list)
 for row in all_rows:
  subgroups[(row["category_id"],row["subcategory"])].append(row)
 writecsv(dest/"subcategories.csv",
  ["category_id","category_name","subcategory","ids","unique_source_texts","needs_context"],
  [{"category_id":cat,"category_name":CATEGORY[cat][0],"subcategory":sub,
    "ids":len(items),"unique_source_texts":len({i["source_text"] for i in items}),
    "needs_context":sum(i["needs_context"]=="예" for i in items)}
   for (cat,sub),items in sorted(subgroups.items())])
 (dest/"summary.json").write_text(json.dumps({
    "total":len(rows),"existing_menu":len(menu),"backlog":len(rows)-len(menu),
    "unique_source_texts":len(freq),"categories":summary
 },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 md=["# NFS 2015 전체 번역 분류", "",
     f"- 원본 문자열 ID: {len(rows):,}개",
     f"- 기존 메뉴 등록: {len(menu):,}개",
     f"- 추가 대상: {len(rows)-len(menu):,}개",
     "- 주의: 메뉴 외 분류는 문자열 패턴에 기반한 추정. 실제 화면 사용처로 검증해야 함.",
     "", "| 우선 | 카테고리 | ID 수 | 중복 제거 문구 | 번역 있는 ID | 확신 높음 | 문맥 확인 |",
     "|---:|---|---:|---:|---:|---:|---:|"]
 for s in summary:
  md.append(f"| {s['priority']} | {s['category_name']} | {s['ids']:,} | {s['unique_source_texts']:,} | {s['translated']:,} | {s['high_confidence']:,} | {s['needs_context']:,} |")
 md+=["", "## 사용하는 방법", "",
     "- all-strings.csv: 전체 ID/원문/기존 번역/카테고리/분류 확신도 통합 목록.",
     "- by-category 폴더: 16개 카테고리별 원문 CSV. 문자열 ID는 0x 8자리로 유지.",
     "- 기존 메뉴 번역은 translations/menu/*.csv만 수정. 기획용 CSV를 번역 원본으로 쓰지 않는다.",
     "- 분류를 바꾸려면 translations/category-overrides.csv에 string_id,category_id,subcategory를 작성하고 스크립트를 다시 실행.",
     "- 동일 reuse_key 문구는 번역 재사용 후보지만 화면별 문맥 차이를 확인한 뒤 재사용.",
     "- 원문 타임코드, 마크업, 텍스트 변수와 게임 전용 문자는 번역해도 변경하면 안 된다.",
     "- 음악/제작진/개발용은 기본적으로 번역 여부를 검토한 뒤 결정.",
     "- 영어 전체 추출물은 저작권 자료이므로 work/ 내에만 보관하고 GitLab에 업로드하지 않는다.",
     "", "## 권장 작업 순서", "",
     "기존 메뉴 QA → 기타 UI/HUD → 시스템/온라인 → 튜토리얼 → 미션 → 이벤트명 → 차종·부품/튜닝 설명 → 경찰 → 스토리 대사 → SNS → 크레딧 및 미분류 정리",
     ""]
 (dest/"SUMMARY.md").write_text("\n".join(md),encoding="utf-8")
 print("INVENTORY_OK total="+str(len(rows))+" menu="+str(len(menu))+" remaining="+str(len(rows)-len(menu))+" unique_english="+str(len(freq)))
 for s in summary:
  print(f"{s['category_id']:20} ids={s['ids']:5} unique={s['unique_source_texts']:5} confident={s['high_confidence']:5} contextual={s['needs_context']:5}")
 print("EXAMPLES")
 for cat,data in out.items():
  if cat=="00_menu":continue
  sample=[(x["string_id"],x["source_text"][:125]) for x in data[::max(1,len(data)//4)][:4]]
  print(cat,ascii(sample))
 print("OUTPUT",dest)
if __name__=="__main__":
 main()
