# -*- coding: utf-8 -*-
import re
SRC = r"D:\PycharmProjects\LingYi\storage\classics_src\F-009-备急千金要方.txt"
raw = open(SRC, encoding="utf-8").read()
rawn = re.sub(r"\s+", "", raw)

def show(tag, key, back=80, fwd=420):
    p = rawn.find(key)
    print(f"### {tag}  pos={p}")
    if p < 0:
        # try fuzzy: drop each char? just report
        print("  NOT FOUND:", key)
        return
    print("  ", rawn[p - back:p + fwd].replace("\n", ""))
    print()

# 1. excerpt-not-found records
show("卫侯青膏", "卫侯青膏")
show("七气汤", "七气汤")
show("大平胃泽兰丸", "大平胃泽兰丸")

# 2. single-char herbs
show("杀鬼烧药方(人)", "杀鬼烧药方")
show("辟温杀鬼丸(皮/东门上鸡头)", "辟温杀鬼丸")
show("大薯蓣丸(归/胡)", "大薯蓣丸")
show("大茵陈汤(实)", "大茵陈汤")

# 3. 各 dosage drop
show("治中结阳丸", "结阳")
show("槟榔汤方(桔梗白术各四两)", "槟榔二十四枚")

# 4. 五痔第三 section-name record
show("五痔第三", "五痔第三", back=0, fwd=500)

# 5. 理中汤
show("理中汤(甘草三两干姜二两)", "理中汤")

# 6. 澡豆方。
show("澡豆方。", "澡豆方")

# 7. 治丸方
show("治丸方", "阴第八")
