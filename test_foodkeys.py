import json, os, tempfile
import foodkeys_search as fk

fk.DB = tempfile.mkdtemp()
row = lambda i, n: f'''<div class="col-md-2 text-center" style="padding:10px"><a title="{n}" href="details?id={i}&CompanyName=x" target="_blank"><img src="a.jpg"></a></div>
<div class="col-md-10"><span class="rating rating_4" title="x"></span><h2><a href="details?id={i}&CompanyName=x"><span style="x">{n}</span> </a></h2>
<h6><span class="title" data-content="واردکننده ادویه جات و زردچوبه">واردکننده ...</span></h6><div class="title">۱۰۷۳۱ بازدید</div></div>'''
page = row(97, "سبز بهار پارس") + row(5, "آیسان کالا") + "<a href=\"javascript:__doPostBack('x','Page$2')\">2</a>"
r = fk.rows(page, "food_importers")
assert [x["id"] for x in r] == ["97", "5"] and r[0]["views"] == 10731 and r[0]["rating"] == 4 and "زردچوبه" in r[0]["summary"], r
det = '''<div id="nav-home">نام شرکت : سبز بهار پارس ( سهامی خاص )<br/>مدیر عامل : آقای علی رضایی<br/>عنوان محصولات : زردچوبه، فلفل</div>
<div id="nav-history">تاریخچه</div>
<div id="nav-address">آدرس : استان فارس ، شهر شیراز<hr/>تلفن همراه مدیر عامل : <span>محفوظ</span><hr/>تلفن : <span>۰۷۱-۳۶۶۱۲۳۴۵</span><hr/>ایمیل : a@sabzbahar.ir</div>
<div id="nav-employee">x</div>'''
d = fk.detail(det)
assert d["withheld"] == 1 and "07136612345" in d["phones"] and d["fields"]["مدیر عامل"].endswith("رضایی") and "زردچوبه" in d["products"], d
assert fk.name_sim("شرکت بازرگانی سبز بهار پارس سهامی خاص", "سبز بهار پارس") > 0.9 and fk.name_sim("نشاسته گل گندم", "سبز بهار پارس") < 0.3
c, why = fk.score_pair({"name": "بازرگانی سبز بهار پارس", "ceo": "علی رضایی", "profile": {"address": "فارس، شیراز"}}, {"name": "سبز بهار پارس", "detail": d})
assert 80 <= c <= 99 and "نام مدیرعامل در فوودکیز" in why, (c, why)
assert fk.score_pair({"name": "نشاسته گل گندم"}, {"name": "سبز بهار پارس"})[0] == 0
print("ok foodkeys")
