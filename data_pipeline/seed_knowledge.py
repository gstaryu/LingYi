"""
TCM 结构化知识库种子数据脚本 - 填充本草、方剂、禁忌表。

数据来源：公开领域中医经典文献（《伤寒论》《金匮要略》《神农本草经》）
及标准《中药学》教材内容，手工整理确保可靠性。

用法:
    # 使用默认 db_path（settings.db_path）
    python -m data_pipeline.seed_knowledge

    # 指定数据库路径（测试用）
    python -m data_pipeline.seed_knowledge --db-path /tmp/test.db

幂等性：使用 upsert（INSERT ON CONFLICT DO UPDATE），可重复运行。
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from lingyi.knowledge.models import Contraindication, Formula, FormulaComponent, Herb
from lingyi.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


# ==================== 本草数据（~33味常用药）====================

HERBS: list[Herb] = [
    Herb(
        name="人参",
        aliases=["棒槌", "园参", "野山参"],
        nature_flavor="甘、微苦，微温",
        meridians=["脾", "肺", "心"],
        efficacy="大补元气，复脉固脱，补脾益肺，生津养血，安神益智",
        indications=["气虚欲脱", "脾气不足", "肺气亏虚", "心神不安", "失眠多梦"],
        dosage="3-9g，挽救虚脱可用15-30g",
        processing="生用或晒干（生晒参）；蒸制后干燥（红参）",
        contraindications="实证、热证而正气不虚者忌用。不宜与藜芦同用（十八反）",
    ),
    Herb(
        name="黄芪",
        aliases=["绵黄芪", "黄耆"],
        nature_flavor="甘，微温",
        meridians=["脾", "肺"],
        efficacy="补气升阳，固表止汗，利水消肿，生津养血，行滞通痹，托毒排脓，敛疮生肌",
        indications=["气虚乏力", "食少便溏", "中气下陷", "表虚自汗", "气虚水肿"],
        dosage="9-30g",
        processing="生用或蜜炙（炙黄芪偏于补中益气）",
        contraindications="表实邪盛、气滞湿阻、食积内停、阴虚阳亢者忌用",
    ),
    Herb(
        name="甘草",
        aliases=["生甘草", "炙甘草", "甜根子"],
        nature_flavor="甘，平",
        meridians=["心", "肺", "脾", "胃"],
        efficacy="补脾益气，清热解毒，祛痰止咳，缓急止痛，调和诸药",
        indications=["脾气虚弱", "咳嗽气喘", "脘腹四肢挛急疼痛", "药食中毒"],
        dosage="2-10g",
        processing="生用或蜜炙（炙甘草偏于补脾和胃）",
        contraindications="不宜与海藻、京大戟、红大戟、甘遂、芫花同用（十八反）。实证、水肿者慎用",
    ),
    Herb(
        name="当归",
        aliases=["秦归", "云归", "全当归"],
        nature_flavor="甘、辛，温",
        meridians=["肝", "心", "脾"],
        efficacy="补血活血，调经止痛，润肠通便",
        indications=["血虚萎黄", "月经不调", "经闭痛经", "虚寒腹痛", "肠燥便秘"],
        dosage="6-12g",
        processing="生用或酒炙（酒当归增强活血通经之力）",
        contraindications="湿盛中满、大便溏泄者慎用",
    ),
    Herb(
        name="白术",
        aliases=["于术", "冬术"],
        nature_flavor="苦、甘，温",
        meridians=["脾", "胃"],
        efficacy="健脾益气，燥湿利水，止汗，安胎",
        indications=["脾气虚弱", "痰饮水肿", "自汗", "胎动不安"],
        dosage="6-12g",
        processing="生用或麸炒（炒白术增强健脾作用）、土炒",
        contraindications="阴虚内热、津液亏耗者慎用",
    ),
    Herb(
        name="茯苓",
        aliases=["云苓", "白茯苓"],
        nature_flavor="甘、淡，平",
        meridians=["心", "脾", "肾"],
        efficacy="利水渗湿，健脾，宁心",
        indications=["水肿尿少", "痰饮眩悸", "脾虚食少", "便溏泄泻", "心神不安"],
        dosage="10-15g",
        processing="生用",
        contraindications="阴虚而无湿热、虚寒精滑者慎用",
    ),
    Herb(
        name="桂枝",
        aliases=["嫩桂枝", "桂枝尖"],
        nature_flavor="辛、甘，温",
        meridians=["心", "肺", "膀胱"],
        efficacy="发汗解肌，温通经脉，助阳化气，平冲降逆",
        indications=["风寒感冒", "脘腹冷痛", "血寒经闭", "关节痹痛", "痰饮蓄水"],
        dosage="3-10g",
        processing="生用",
        contraindications="热证、阴虚阳盛者忌用。孕妇慎用",
    ),
    Herb(
        name="麻黄",
        aliases=["麻黄草"],
        nature_flavor="辛、微苦，温",
        meridians=["肺", "膀胱"],
        efficacy="发汗解表，宣肺平喘，利水消肿",
        indications=["风寒感冒", "咳嗽气喘", "风水水肿"],
        dosage="2-10g",
        processing="生用或蜜炙（炙麻黄偏于平喘）",
        contraindications="表虚自汗、阴虚盗汗者忌用。孕妇慎用",
    ),
    Herb(
        name="附子",
        aliases=["黑附子", "淡附片", "炮附子"],
        nature_flavor="辛、甘，大热；有毒",
        meridians=["心", "肾", "脾"],
        efficacy="回阳救逆，补火助阳，散寒止痛",
        indications=["亡阳虚脱", "阳虚内寒", "寒湿痹痛"],
        dosage="3-15g，先煎30-60分钟以减毒",
        processing="盐附子、黑顺片、白附片（炮制减毒后入药）",
        contraindications="孕妇禁用。不宜与半夏、瓜蒌、贝母、白蔹、白及同用（十八反）",
    ),
    Herb(
        name="干姜",
        aliases=["白姜", "均姜"],
        nature_flavor="辛，热",
        meridians=["脾", "胃", "肾", "心", "肺"],
        efficacy="温中散寒，回阳通脉，温肺化饮",
        indications=["脘腹冷痛", "呕吐泄泻", "肢冷脉微", "寒饮喘咳"],
        dosage="3-10g",
        processing="生用或炮制成炮姜（炒炭止血）",
        contraindications="阴虚内热、血热妄行者忌用。孕妇慎用",
    ),
    Herb(
        name="黄连",
        aliases=["川连", "味连", "雅连"],
        nature_flavor="苦，寒",
        meridians=["心", "脾", "胃", "肝", "胆", "大肠"],
        efficacy="清热燥湿，泻火解毒",
        indications=["湿热痞满", "呕吐吞酸", "心烦不寐", "高热神昏", "目赤牙痛"],
        dosage="2-5g",
        processing="生用或酒炙、姜汁炙（酒连偏清上焦热，姜连偏清胃止呕）",
        contraindications="脾胃虚寒者忌用。阴虚津伤者慎用",
    ),
    Herb(
        name="黄芩",
        aliases=["条芩", "子芩", "枯芩"],
        nature_flavor="苦，寒",
        meridians=["肺", "胆", "脾", "大肠", "小肠"],
        efficacy="清热燥湿，泻火解毒，止血，安胎",
        indications=["湿温暑湿", "肺热咳嗽", "少阳证", "血热出血", "胎动不安"],
        dosage="3-10g",
        processing="生用或酒炙、炒炭",
        contraindications="脾胃虚寒、食少便溏者不宜使用",
    ),
    Herb(
        name="半夏",
        aliases=["法半夏", "姜半夏", "清半夏"],
        nature_flavor="辛，温；有毒",
        meridians=["脾", "胃", "肺"],
        efficacy="燥湿化痰，降逆止呕，消痞散结",
        indications=["湿痰寒痰", "呕吐反胃", "胸脘痞闷", "梅核气"],
        dosage="3-9g",
        processing="内服须炮制：清半夏、姜半夏、法半夏",
        contraindications="孕妇慎用。不宜与乌头类同用（十八反）。生半夏外用",
    ),
    Herb(
        name="柴胡",
        aliases=["北柴胡", "南柴胡", "软柴胡"],
        nature_flavor="苦、辛，微寒",
        meridians=["肝", "胆"],
        efficacy="疏散退热，疏肝解郁，升举阳气",
        indications=["感冒发热", "少阳证", "肝郁气滞", "气虚下陷"],
        dosage="3-10g",
        processing="生用或醋炙（醋柴胡偏于疏肝止痛）",
        contraindications="肝阳上亢、肝风内动、阴虚火旺者忌用",
    ),
    Herb(
        name="白芍",
        aliases=["白芍药", "杭白芍", "杭芍"],
        nature_flavor="苦、酸，微寒",
        meridians=["肝", "脾"],
        efficacy="养血调经，敛阴止汗，柔肝止痛，平抑肝阳",
        indications=["血虚萎黄", "月经不调", "自汗盗汗", "胁痛腹痛", "头痛眩晕"],
        dosage="6-15g",
        processing="生用或炒用、酒炙",
        contraindications="阳衰虚寒之证不宜使用。不宜与藜芦同用（十八反）",
    ),
    Herb(
        name="熟地黄",
        aliases=["熟地"],
        nature_flavor="甘，微温",
        meridians=["肝", "肾"],
        efficacy="补血滋阴，益精填髓",
        indications=["血虚萎黄", "心悸怔忡", "月经不调", "盗汗遗精", "腰膝酸软"],
        dosage="9-15g",
        processing="酒炖或酒蒸至内外色黑油润",
        contraindications="脾胃虚弱、气滞痰多、腹满便溏者忌用",
    ),
    Herb(
        name="川芎",
        aliases=["芎藭", "抚芎"],
        nature_flavor="辛，温",
        meridians=["肝", "胆", "心包"],
        efficacy="活血行气，祛风止痛",
        indications=["血瘀气滞", "月经不调", "头痛", "风湿痹痛"],
        dosage="3-10g",
        processing="生用或酒炙",
        contraindications="阴虚火旺、舌红口干者不宜使用。孕妇慎用",
    ),
    Herb(
        name="陈皮",
        aliases=["橘皮", "新会皮"],
        nature_flavor="辛、苦，温",
        meridians=["脾", "肺"],
        efficacy="理气健脾，燥湿化痰",
        indications=["脘腹胀满", "食少吐泻", "咳嗽痰多"],
        dosage="3-10g",
        processing="生用",
        contraindications="气虚证、阴虚燥咳者慎用",
    ),
    Herb(
        name="枳实",
        aliases=["江枳实", "川枳实"],
        nature_flavor="苦、辛、酸，微寒",
        meridians=["脾", "胃", "大肠"],
        efficacy="破气消积，化痰散痞",
        indications=["积滞内停", "痞满胀痛", "泻痢后重", "胸痹"],
        dosage="3-10g",
        processing="生用或麸炒",
        contraindications="孕妇慎用。脾胃虚弱而无积滞者忌用",
    ),
    Herb(
        name="厚朴",
        aliases=["川朴", "紫油厚朴"],
        nature_flavor="苦、辛，温",
        meridians=["脾", "胃", "肺", "大肠"],
        efficacy="燥湿消痰，下气除满",
        indications=["湿滞伤中", "脘痞吐泻", "食积气滞", "痰饮喘咳"],
        dosage="3-10g",
        processing="生用或姜汁炙（姜厚朴和中止呕）",
        contraindications="孕妇慎用。气虚津亏者不宜使用",
    ),
    Herb(
        name="大黄",
        aliases=["将军", "锦纹", "川军"],
        nature_flavor="苦，寒",
        meridians=["脾", "胃", "大肠", "肝", "心包"],
        efficacy="泻下攻积，清热泻火，凉血解毒，逐瘀通经",
        indications=["积滞便秘", "血热吐衄", "目赤咽肿", "热毒疮疡", "瘀血经闭"],
        dosage="3-15g；外用适量",
        processing="生用或酒炙、炒炭",
        contraindications="孕妇禁用。哺乳期、月经期慎用。脾胃虚寒者忌用",
    ),
    Herb(
        name="芒硝",
        aliases=["朴硝", "皮硝"],
        nature_flavor="咸、苦，寒",
        meridians=["胃", "大肠"],
        efficacy="泻下通便，润燥软坚，清火消肿",
        indications=["实热积滞", "大便燥结", "咽痛口疮", "目赤肿痛"],
        dosage="6-12g，冲服",
        processing="提炼结晶",
        contraindications="孕妇禁用。脾胃虚寒者忌用。不宜与三棱同用（十九畏）",
    ),
    Herb(
        name="石膏",
        aliases=["生石膏", "白虎"],
        nature_flavor="甘、辛，大寒",
        meridians=["肺", "胃"],
        efficacy="清热泻火，除烦止渴；煅用收湿敛疮",
        indications=["温热病气分热证", "肺热喘咳", "胃火牙痛", "溃疡不敛"],
        dosage="15-60g，先煎",
        processing="生用或煅用",
        contraindications="脾胃虚寒、阴虚内热者忌用",
    ),
    Herb(
        name="知母",
        aliases=["肥知母", "毛知母"],
        nature_flavor="苦、甘，寒",
        meridians=["肺", "胃", "肾"],
        efficacy="清热泻火，滋阴润燥",
        indications=["热病烦渴", "肺热咳嗽", "骨蒸潮热", "内热消渴"],
        dosage="6-12g",
        processing="生用或盐水炙（盐知母引药入肾）",
        contraindications="脾胃虚寒、大便溏泄者忌用",
    ),
    Herb(
        name="金银花",
        aliases=["双花", "银花", "忍冬花"],
        nature_flavor="甘，寒",
        meridians=["肺", "心", "胃"],
        efficacy="清热解毒，疏散风热",
        indications=["痈肿疔疮", "外感风热", "温病初起", "热毒血痢"],
        dosage="6-15g",
        processing="生用或炒炭",
        contraindications="脾胃虚寒及气虚疮疡脓清者忌用",
    ),
    Herb(
        name="连翘",
        aliases=["青翘", "老翘"],
        nature_flavor="苦，微寒",
        meridians=["心", "肺", "小肠"],
        efficacy="清热解毒，消肿散结，疏散风热",
        indications=["痈疽瘰疬", "风热外感", "温病初起"],
        dosage="6-15g",
        processing="生用",
        contraindications="脾胃虚寒者慎用",
    ),
    Herb(
        name="牡丹皮",
        aliases=["丹皮", "粉丹皮"],
        nature_flavor="苦、辛，微寒",
        meridians=["心", "肝", "肾"],
        efficacy="清热凉血，活血化瘀",
        indications=["热入营血", "温毒发斑", "夜热早凉", "经闭痛经", "痈肿疮毒"],
        dosage="6-12g",
        processing="生用或酒炙",
        contraindications="孕妇慎用。血虚有寒、月经过多者不宜使用",
    ),
    Herb(
        name="桃仁",
        aliases=["光桃仁"],
        nature_flavor="苦、甘，平",
        meridians=["心", "肝", "大肠"],
        efficacy="活血祛瘀，润肠通便，止咳平喘",
        indications=["经闭痛经", "癥瘕痞块", "肠燥便秘", "咳嗽气喘"],
        dosage="5-10g",
        processing="燀去皮生用或炒用",
        contraindications="孕妇慎用。便溏者不宜使用",
    ),
    Herb(
        name="红花",
        aliases=["红蓝花", "草红花"],
        nature_flavor="辛，温",
        meridians=["心", "肝"],
        efficacy="活血通经，散瘀止痛",
        indications=["经闭痛经", "胸痹心痛", "瘀滞腹痛", "跌打损伤"],
        dosage="3-10g",
        processing="生用",
        contraindications="孕妇禁用。月经过多者忌用",
    ),
    Herb(
        name="杏仁",
        aliases=["苦杏仁", "北杏"],
        nature_flavor="苦，微温；有小毒",
        meridians=["肺", "大肠"],
        efficacy="降气止咳平喘，润肠通便",
        indications=["咳嗽气喘", "胸满痰多", "肠燥便秘"],
        dosage="5-10g",
        processing="燀去皮生用或炒用",
        contraindications="孕妇慎用。用量不宜过大，婴儿慎用",
    ),
    Herb(
        name="五味子",
        aliases=["五梅子", "山花椒"],
        nature_flavor="酸、甘，温",
        meridians=["肺", "心", "肾"],
        efficacy="收敛固涩，益气生津，补肾宁心",
        indications=["久嗽虚喘", "自汗盗汗", "遗精滑精", "久泻不止", "心悸失眠"],
        dosage="2-6g",
        processing="生用或醋蒸、蜜炙",
        contraindications="外有表邪、内有实热者忌用",
    ),
    Herb(
        name="麦冬",
        aliases=["寸冬", "麦门冬"],
        nature_flavor="甘、微苦，微寒",
        meridians=["心", "肺", "胃"],
        efficacy="养阴生津，润肺清心",
        indications=["肺燥干咳", "阴虚痨嗽", "喉痹咽痛", "津伤口渴", "心烦失眠"],
        dosage="6-12g",
        processing="生用",
        contraindications="脾胃虚寒、感冒风寒痰饮者忌用",
    ),
    Herb(
        name="葛根",
        aliases=["粉葛", "干葛"],
        nature_flavor="甘、辛，凉",
        meridians=["脾", "胃", "肺"],
        efficacy="解肌退热，透疹，生津止渴，升阳止泻",
        indications=["外感发热", "项背强痛", "麻疹不透", "热病口渴", "脾虚泄泻"],
        dosage="10-15g",
        processing="生用或煨用（煨葛根偏于止泻）",
        contraindications="胃寒呕吐者慎用",
    ),
]


# ==================== 方剂数据（~22首经典方）====================

FORMULAS: list[Formula] = [
    Formula(
        name="桂枝汤",
        source="伤寒论",
        composition=[
            FormulaComponent("桂枝", "9g"),
            FormulaComponent("芍药", "9g"),
            FormulaComponent("甘草", "6g"),
            FormulaComponent("生姜", "9g"),
            FormulaComponent("大枣", "3枚"),
        ],
        indication="外感风寒表虚证。头痛发热，汗出恶风，鼻鸣干呕，苔白不渴，脉浮缓或浮弱",
        modifications="恶风寒甚者加防风、荆芥；咳嗽者加杏仁、厚朴",
        contraindications="表实无汗、外感风寒表实证不宜使用",
        category="经方",
    ),
    Formula(
        name="麻黄汤",
        source="伤寒论",
        composition=[
            FormulaComponent("麻黄", "6g"),
            FormulaComponent("桂枝", "4g"),
            FormulaComponent("杏仁", "9g"),
            FormulaComponent("甘草", "3g"),
        ],
        indication="外感风寒表实证。恶寒发热，无汗而喘，头痛身疼，苔薄白，脉浮紧",
        modifications="喘甚加苏子、桑白皮；湿邪重加白术、苍术",
        contraindications="表虚自汗、体虚外感者忌用。孕妇慎用",
        category="经方",
    ),
    Formula(
        name="白虎汤",
        source="伤寒论",
        composition=[
            FormulaComponent("石膏", "50g"),
            FormulaComponent("知母", "18g"),
            FormulaComponent("甘草", "6g"),
            FormulaComponent("粳米", "9g"),
        ],
        indication="阳明气分热盛证。壮热面赤，烦渴引饮，汗出恶热，脉洪大有力",
        modifications="热盛伤津加人参（白虎加人参汤）；关节肿痛加桂枝（白虎加桂枝汤）",
        contraindications="脾胃虚寒、阴虚发热者忌用",
        category="经方",
    ),
    Formula(
        name="四物汤",
        source="太平惠民和剂局方",
        composition=[
            FormulaComponent("当归", "12g"),
            FormulaComponent("川芎", "8g"),
            FormulaComponent("白芍", "12g"),
            FormulaComponent("熟地黄", "12g"),
        ],
        indication="营血虚滞证。头晕心悸，面色无华，月经不调，脐腹疼痛",
        modifications="血热加黄芩、牡丹皮；血瘀加桃仁、红花",
        contraindications="脾胃阳虚、食少便溏者慎用",
        category="时方",
    ),
    Formula(
        name="四君子汤",
        source="太平惠民和剂局方",
        composition=[
            FormulaComponent("人参", "9g"),
            FormulaComponent("白术", "9g"),
            FormulaComponent("茯苓", "9g"),
            FormulaComponent("甘草", "6g"),
        ],
        indication="脾胃气虚证。面色萎白，语声低微，气短乏力，食少便溏，舌淡苔白",
        modifications="气虚甚加黄芪；湿盛加陈皮、半夏（六君子汤）",
        contraindications="阴虚内热者慎用",
        category="时方",
    ),
    Formula(
        name="六味地黄丸",
        source="小儿药证直诀",
        composition=[
            FormulaComponent("熟地黄", "24g"),
            FormulaComponent("山茱萸", "12g"),
            FormulaComponent("山药", "12g"),
            FormulaComponent("泽泻", "9g"),
            FormulaComponent("牡丹皮", "9g"),
            FormulaComponent("茯苓", "9g"),
        ],
        indication="肾阴虚证。腰膝酸软，头晕耳鸣，盗汗遗精，骨蒸潮热，手足心热",
        modifications="阴虚火旺加知母、黄柏（知柏地黄丸）；视物不清加枸杞、菊花（杞菊地黄丸）",
        contraindications="脾虚泄泻者慎用",
        category="时方",
    ),
    Formula(
        name="逍遥散",
        source="太平惠民和剂局方",
        composition=[
            FormulaComponent("柴胡", "9g"),
            FormulaComponent("当归", "9g"),
            FormulaComponent("白芍", "9g"),
            FormulaComponent("白术", "9g"),
            FormulaComponent("茯苓", "9g"),
            FormulaComponent("甘草", "5g"),
            FormulaComponent("生姜", "3g"),
            FormulaComponent("薄荷", "3g"),
        ],
        indication="肝郁血虚脾弱证。两胁作痛，头痛目眩，口燥咽干，神疲食少，月经不调",
        modifications="热甚加牡丹皮、栀子（丹栀逍遥散/加味逍遥散）",
        contraindications="阴虚阳亢者慎用",
        category="时方",
    ),
    Formula(
        name="补中益气汤",
        source="脾胃论",
        composition=[
            FormulaComponent("黄芪", "18g"),
            FormulaComponent("人参", "6g"),
            FormulaComponent("白术", "9g"),
            FormulaComponent("甘草", "9g"),
            FormulaComponent("当归", "3g"),
            FormulaComponent("陈皮", "6g"),
            FormulaComponent("升麻", "6g"),
            FormulaComponent("柴胡", "6g"),
        ],
        indication="脾虚气陷证。饮食减少，体倦肢软，少气懒言，面色萎黄，大便稀溏，脱肛，子宫脱垂",
        modifications="气虚甚重用黄芪；脏器下垂重用人参、升麻",
        contraindications="阴虚内热、肝阳上亢者忌用",
        category="时方",
    ),
    Formula(
        name="黄连解毒汤",
        source="外台秘要",
        composition=[
            FormulaComponent("黄连", "9g"),
            FormulaComponent("黄芩", "6g"),
            FormulaComponent("黄柏", "6g"),
            FormulaComponent("栀子", "9g"),
        ],
        indication="三焦火毒热盛证。大热烦躁，口燥咽干，错语不眠，吐衄发斑，外科痈肿疔毒",
        modifications="便秘加大黄；瘀热发黄加茵陈、大黄",
        contraindications="脾胃虚寒者忌用。阴虚火旺者慎用",
        category="时方",
    ),
    Formula(
        name="半夏泻心汤",
        source="伤寒论",
        composition=[
            FormulaComponent("半夏", "12g"),
            FormulaComponent("黄芩", "9g"),
            FormulaComponent("干姜", "9g"),
            FormulaComponent("人参", "9g"),
            FormulaComponent("黄连", "3g"),
            FormulaComponent("大枣", "4枚"),
            FormulaComponent("甘草", "9g"),
        ],
        indication="寒热错杂之痞证。心下痞满而不痛，呕吐肠鸣下利，苔腻微黄",
        modifications="痞甚加枳实、厚朴；湿热甚去干姜加生姜（生姜泻心汤）",
        contraindications="纯寒或纯热证不宜使用",
        category="经方",
    ),
    Formula(
        name="小柴胡汤",
        source="伤寒论",
        composition=[
            FormulaComponent("柴胡", "24g"),
            FormulaComponent("黄芩", "9g"),
            FormulaComponent("人参", "9g"),
            FormulaComponent("甘草", "9g"),
            FormulaComponent("半夏", "9g"),
            FormulaComponent("生姜", "9g"),
            FormulaComponent("大枣", "4枚"),
        ],
        indication="少阳证。往来寒热，胸胁苦满，默默不欲饮食，心烦喜呕，口苦咽干目眩",
        modifications="胸中烦而不呕去半夏人参加瓜蒌；口渴去半夏加天花粉",
        contraindications="阴虚血少者慎用",
        category="经方",
    ),
    Formula(
        name="麻杏石甘汤",
        source="伤寒论",
        composition=[
            FormulaComponent("麻黄", "6g"),
            FormulaComponent("杏仁", "9g"),
            FormulaComponent("石膏", "24g"),
            FormulaComponent("甘草", "6g"),
        ],
        indication="表寒里热证（肺热喘咳）。身热不解，咳逆气急鼻扇，口渴，有汗或无汗",
        modifications="痰多加贝母、瓜蒌；热甚加黄芩、栀子",
        contraindications="风寒咳喘、虚证喘息者忌用",
        category="经方",
    ),
    Formula(
        name="大承气汤",
        source="伤寒论",
        composition=[
            FormulaComponent("大黄", "12g"),
            FormulaComponent("厚朴", "24g"),
            FormulaComponent("枳实", "12g"),
            FormulaComponent("芒硝", "9g"),
        ],
        indication="阳明腑实证。大便不通，脘腹痞满，腹痛拒按，潮热谵语，手足濈然汗出，脉沉实",
        modifications="热结阴伤加生地、玄参（增液承气汤）",
        contraindications="孕妇禁用。脾胃虚寒者忌用",
        category="经方",
    ),
    Formula(
        name="理中丸",
        source="伤寒论",
        composition=[
            FormulaComponent("人参", "9g"),
            FormulaComponent("干姜", "9g"),
            FormulaComponent("白术", "9g"),
            FormulaComponent("甘草", "9g"),
        ],
        indication="脾胃虚寒证。脘腹绵绵作痛，喜温喜按，呕吐便溏，畏寒肢冷，舌淡苔白",
        modifications="寒甚重用干姜；呕吐加半夏、生姜",
        contraindications="阴虚内热者忌用",
        category="经方",
    ),
    Formula(
        name="四逆汤",
        source="伤寒论",
        composition=[
            FormulaComponent("附子", "15g"),
            FormulaComponent("干姜", "9g"),
            FormulaComponent("甘草", "6g"),
        ],
        indication="少阴病之亡阳证。四肢厥逆，恶寒蜷卧，呕吐不渴，腹痛下利，脉微欲绝",
        modifications="阳虚甚加人参（四逆加人参汤）",
        contraindications="热厥证忌用。附子须先煎减毒",
        category="经方",
    ),
    Formula(
        name="肾气丸",
        source="金匮要略",
        composition=[
            FormulaComponent("干地黄", "24g"),
            FormulaComponent("山药", "12g"),
            FormulaComponent("山茱萸", "12g"),
            FormulaComponent("泽泻", "9g"),
            FormulaComponent("茯苓", "9g"),
            FormulaComponent("牡丹皮", "9g"),
            FormulaComponent("桂枝", "3g"),
            FormulaComponent("附子", "3g"),
        ],
        indication="肾阳不足证。腰痛脚软，下半身常有冷感，少腹拘急，小便不利或反多，脉虚弱",
        modifications="阳虚甚加鹿角胶、淫羊藿",
        contraindications="阴虚火旺者忌用。孕妇禁用（含附子）",
        category="经方",
    ),
    Formula(
        name="当归四逆汤",
        source="伤寒论",
        composition=[
            FormulaComponent("当归", "12g"),
            FormulaComponent("桂枝", "9g"),
            FormulaComponent("芍药", "9g"),
            FormulaComponent("细辛", "3g"),
            FormulaComponent("甘草", "6g"),
            FormulaComponent("通草", "6g"),
            FormulaComponent("大枣", "8枚"),
        ],
        indication="血虚寒厥证。手足厥寒，脉细欲绝，肢体关节疼痛",
        modifications="寒甚加吴茱萸、生姜（当归四逆加吴茱萸生姜汤）",
        contraindications="热厥证忌用",
        category="经方",
    ),
    Formula(
        name="真武汤",
        source="伤寒论",
        composition=[
            FormulaComponent("茯苓", "9g"),
            FormulaComponent("芍药", "9g"),
            FormulaComponent("白术", "6g"),
            FormulaComponent("生姜", "9g"),
            FormulaComponent("附子", "9g"),
        ],
        indication="阳虚水泛证。畏寒肢厥，小便不利，心下悸，头眩身瞤动，四肢沉重疼痛，浮肿",
        modifications="咳者加五味子、细辛；小便利去茯苓；下利去芍药加干姜",
        contraindications="阴虚火旺者忌用。附子须先煎减毒",
        category="经方",
    ),
    Formula(
        name="酸枣仁汤",
        source="金匮要略",
        composition=[
            FormulaComponent("酸枣仁", "15g"),
            FormulaComponent("甘草", "3g"),
            FormulaComponent("知母", "6g"),
            FormulaComponent("茯苓", "6g"),
            FormulaComponent("川芎", "6g"),
        ],
        indication="肝血不足，虚热内扰之虚烦不眠证。虚烦不得眠，心悸盗汗，头目眩晕，咽干口燥",
        modifications="热甚加栀子、牡丹皮；阴虚加生地、麦冬",
        contraindications="实热证、痰湿内扰者不宜使用",
        category="经方",
    ),
    Formula(
        name="归脾汤",
        source="济生方",
        composition=[
            FormulaComponent("白术", "9g"),
            FormulaComponent("当归", "9g"),
            FormulaComponent("茯苓", "9g"),
            FormulaComponent("黄芪", "12g"),
            FormulaComponent("龙眼肉", "12g"),
            FormulaComponent("远志", "3g"),
            FormulaComponent("酸枣仁", "12g"),
            FormulaComponent("木香", "3g"),
            FormulaComponent("人参", "6g"),
            FormulaComponent("甘草", "3g"),
        ],
        indication="心脾气血两虚证。心悸怔忡，健忘失眠，气短乏力，食少，面色萎黄，妇女月经超前或量多色淡",
        modifications="崩漏下血加阿胶、艾叶",
        contraindications="阴虚内热者慎用",
        category="时方",
    ),
    Formula(
        name="血府逐瘀汤",
        source="医林改错",
        composition=[
            FormulaComponent("桃仁", "12g"),
            FormulaComponent("红花", "9g"),
            FormulaComponent("当归", "9g"),
            FormulaComponent("川芎", "5g"),
            FormulaComponent("生地黄", "9g"),
            FormulaComponent("赤芍", "6g"),
            FormulaComponent("牛膝", "9g"),
            FormulaComponent("桔梗", "5g"),
            FormulaComponent("柴胡", "3g"),
            FormulaComponent("枳壳", "6g"),
            FormulaComponent("甘草", "3g"),
        ],
        indication="胸中血瘀证。胸痛头痛日久不愈，痛如针刺而有定处，心悸怔忡，夜不能睡",
        modifications="气滞甚加香附、青皮；痛甚加乳香、没药",
        contraindications="孕妇禁用。气虚血瘀者慎用",
        category="时方",
    ),
    Formula(
        name="旋覆代赭汤",
        source="伤寒论",
        composition=[
            FormulaComponent("旋覆花", "9g"),
            FormulaComponent("人参", "6g"),
            FormulaComponent("生姜", "15g"),
            FormulaComponent("代赭石", "3g"),
            FormulaComponent("甘草", "9g"),
            FormulaComponent("半夏", "9g"),
            FormulaComponent("大枣", "4枚"),
        ],
        indication="胃虚痰阻证。心下痞硬，噫气不除，反胃呕吐，舌苔白滑",
        modifications="痰多加陈皮、茯苓；胃热加黄连、竹茹",
        contraindications="肝阳上亢之呕吐不宜使用",
        category="经方",
    ),
]


# ==================== 禁忌数据 ====================

CONTRAINDICATIONS: list[Contraindication] = []

# 体质/证候禁忌条目
CONTRAINDICATIONS.extend([
    Contraindication(
        herb="人参",
        type="体质",
        detail="实证、热证而正气不虚者忌用，误补益疾",
        severity="禁用",
    ),
    Contraindication(
        herb="麻黄",
        type="体质",
        detail="表虚自汗、阴虚盗汗者忌用，恐发汗伤阴",
        severity="禁用",
    ),
    Contraindication(
        herb="大黄",
        type="体质",
        detail="脾胃虚寒、气血虚弱者忌用，恐苦寒伤中",
        severity="禁用",
    ),
    Contraindication(
        herb="石膏",
        type="体质",
        detail="脾胃虚寒、阴虚内热者忌用",
        severity="禁用",
    ),
    Contraindication(
        herb="黄连",
        type="体质",
        detail="脾胃虚寒者忌用，苦寒易伤脾胃阳气",
        severity="禁用",
    ),
    Contraindication(
        herb="熟地黄",
        type="体质",
        detail="脾胃虚弱、气滞痰多、腹满便溏者忌用，滋腻碍脾",
        severity="禁用",
    ),
])

# 配伍禁忌（十八反、十九畏关键药对，供查询参考）
CONTRAINDICATIONS.extend([
    Contraindication(
        herb="甘草",
        type="配伍",
        detail="十八反：甘草反海藻、大戟、甘遂、芫花，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="乌头",
        type="配伍",
        detail="十八反：乌头反半夏、瓜蒌、贝母、白蔹、白及，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="附子",
        type="配伍",
        detail="十八反：附子反半夏、瓜蒌、贝母、白蔹、白及，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="藜芦",
        type="配伍",
        detail="十八反：藜芦反人参、沙参、丹参、玄参、细辛、芍药，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="巴豆",
        type="配伍",
        detail="十九畏：巴豆畏牵牛子，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="丁香",
        type="配伍",
        detail="十九畏：丁香畏郁金，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="人参",
        type="配伍",
        detail="十九畏：人参畏五灵脂，不宜同用",
        severity="禁用",
    ),
    Contraindication(
        herb="芒硝",
        type="配伍",
        detail="十九畏：芒硝畏三棱，不宜同用",
        severity="禁用",
    ),
])


async def seed_knowledge(db_path: str) -> dict[str, int]:
    """
    将种子数据写入指定 SQLite 数据库。

    Returns:
        {"herbs": N, "formulas": N, "contraindications": N}
    """
    storage = SQLiteStorage(db_path)
    await storage.init_db()

    for herb in HERBS:
        await storage.upsert_herb(herb)
    logger.info("已写入 %d 味本草", len(HERBS))

    for formula in FORMULAS:
        await storage.upsert_formula(formula)
    logger.info("已写入 %d 首方剂", len(FORMULAS))

    for ci in CONTRAINDICATIONS:
        await storage.add_contraindication(ci)
    logger.info("已写入 %d 条禁忌", len(CONTRAINDICATIONS))

    await storage.close()

    return {
        "herbs": len(HERBS),
        "formulas": len(FORMULAS),
        "contraindications": len(CONTRAINDICATIONS),
    }


def main():
    """CLI 入口。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="TCM 结构化知识库种子数据脚本")
    parser.add_argument(
        "--db-path",
        default=None,
        help="数据库路径（默认使用 settings.db_path）",
    )
    args = parser.parse_args()

    if args.db_path:
        db_path = args.db_path
    else:
        from lingyi.config import get_settings
        db_path = get_settings().db_path

    print(f"数据库: {db_path}")
    counts = asyncio.run(seed_knowledge(db_path))
    print(
        f"\n种子数据写入完成:\n"
        f"  本草: {counts['herbs']} 味\n"
        f"  方剂: {counts['formulas']} 首\n"
        f"  禁忌: {counts['contraindications']} 条"
    )


if __name__ == "__main__":
    main()
