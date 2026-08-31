"""The assistant's glossary: audit concepts explained for a first-time auditor.

Ask Tarazu is also used by people doing their first audit. "What is
reconciliation?", "what does materiality mean?", "why do I have to approve
everything myself?" — questions a professional asks about a case, a beginner
asks about the profession. They are answered from this file: short,
plain-language explanations written and reviewed in code, in English and Urdu.

This is deliberate, and it is the same standing `help` already has. The rule
the module keeps is *never answer about the case from outside the case* — an
answer about this case's numbers must come from this case's data. A concept
explanation claims nothing about the case; it is fixed text the module ships,
so a model never generates it and no number in it is computed. It is shown as
written, phrased by the deterministic composer, and a model may only reword it
under the same number check as every other answer.
"""

from __future__ import annotations

__all__ = ["CONCEPTS", "DEDICATED_TOPICS", "TOPIC_WORDS"]

#: One concept per topic key: the explanation in each language. Keep each to a
#: few sentences a beginner can hold in mind, ending with what it means for
#: *their* work in Tarazu where that helps.
CONCEPTS: dict[str, dict[str, str]] = {
    "reconciliation": {
        "en": (
            "Reconciliation is checking that two independent records of the same money agree. "
            "In Tarazu it is a three-way match: every payment in the client's ledger must be "
            "backed by a line in the bank statement (the money really left) and, where there "
            "should be one, an invoice (the payment was really owed). A row that agrees on "
            "amount and date is matched; a row with nothing behind it is the classic sign of "
            "a payment that never happened. Ask \"which items are unmatched?\" to see yours."
        ),
        "ur": (
            "مطابقت (ریکنسلئیشن) کا مطلب ہے ایک ہی رقم کے دو آزاد ریکارڈوں کا آپس میں ملانا۔ "
            "ترازو میں یہ تین طرفہ میچ ہے: کلائنٹ کی لیجر کی ہر ادائیگی کے پیچھے بینک اسٹیٹمنٹ کی ایک قطار ہونی چاہیے "
            "(رقم واقعی گئی) اور جہاں انوائس ہونی چاہیے وہ بھی (ادائیگی واقعی واجب الادا تھی)۔ "
            "جو قطار رقم اور تاریخ دونوں پر مل جائے وہ مماثل ہے؛ جس کے پیچھے کچھ نہ ہو وہ فرضی ادائیگی کی کلاسک علامت ہے۔ "
            "اپنے کیس میں دیکھنے کے لیے پوچھیں: \"کون سے آئٹم غیر مماثل ہیں؟\""
        ),
    },
    "benford": {
        "en": (
            "Benford's law is an observation about real-life numbers: in naturally occurring "
            "amounts, about 30% start with the digit 1 and only about 5% start with 9. Made-up "
            "numbers tend not to follow that shape, so when the first digits of a ledger's "
            "amounts stray far from it, that is worth a look. It is a screening test, never "
            "proof — small samples wobble, and honest books can deviate. Ask \"Benford "
            "summary\" to see this case's own result."
        ),
        "ur": (
            "بینفورڈ کا قانون قدرتی اعداد کے بارے میں ایک مشاہدہ ہے: حقیقی رقوم میں تقریباً 30% کا آغاز ہندسہ 1 سے ہوتا ہے "
            "اور صرف 5% کا آغاز 9 سے۔ گھڑے ہوئے اعداد عموماً یہ ساخت نہیں رکھتے، اس لیے جب لیجر کی رقوم کے پہلے ہندسے اس سے بہت ہٹ جائیں "
            "تو دیکھنے کے قابل ہے۔ یہ ایک جانچ ہے، ثبوت کبھی نہیں — چھوٹا نمونہ ہل سکتا ہے اور ایماندار کتابیں بھی ہٹ سکتی ہیں۔ "
            "اپنے کیس کا نتیجہ دیکھنے کے لیے پوچھیں: \"بینفورڈ خلاصہ\"۔"
        ),
    },
    "red-flag": {
        "en": (
            "A red flag is a pattern that experience says deserves a closer look — not proof "
            "of wrongdoing. A round amount, a payment on a Sunday, two payments just under "
            "an approval limit: each can have an innocent explanation, and each is where an "
            "auditor looks first. In Tarazu every flag is raised by a fixed, published rule "
            "and is only a suggestion; the verdict is always the auditor's. Ask \"what flags "
            "were raised?\" for this case's list."
        ),
        "ur": (
            "سرخ نشانی (ریڈ فلیگ) وہ نمونہ ہے جسے تجربہ کہتا ہے زیادہ غور سے دیکھو — غلط کام کا ثبوت نہیں۔ "
            "گول رقم، اتوار کی ادائیگی، منظوری کی حد سے تھوڑا نیچے دو ادائیگیاں: ہر ایک کی معقول وضاحت ہو سکتی ہے، "
            "اور ہر ایک وہ جگہ ہے جہاں آڈیٹر پہلے دیکھتا ہے۔ ترازو میں ہر نشانی ایک متعین، طے شدہ اصول سے اٹھتی ہے اور صرف تجویز ہے؛ "
            "فیصلہ ہمیشہ آڈیٹر کا ہے۔ اپنے کیس کی فہرست کے لیے پوچھیں: \"کون سی نشانیاں اٹھیں؟\""
        ),
    },
    "approval-limit": {
        "en": (
            "An approval limit is the amount above which a payment needs a second signature "
            "— a control firms set so no one person can move large sums alone. The audit "
            "interest is in payments sized to sit just under it: one payment at 98% of the "
            "limit may be chance, a pattern of them suggests someone knows the limit and is "
            "steering under it. Tarazu's near-limit rule flags amounts within 2% below a limit."
        ),
        "ur": (
            "منظوری کی حد وہ رقم ہے جس سے اوپر ادائیگی کو دوسرا دستخط درکار ہوتا ہے — یہ کنٹرول فرم اس لیے رکھتی ہے "
            "کہ کوئی اکیلا بڑی رقم نہ ہلا سکے۔ آڈٹ کی دلچسپی ان ادائیگیوں میں ہے جو عین اس حد سے نیچے رکھی گئی ہوں: "
            "حد کے 98% پر ایک ادائیگی اتفاق ہو سکتی ہے، مگر ان کا سلسلہ بتاتا ہے کہ کوئی حد جانتا ہے اور اس سے بچ رہا ہے۔ "
            "ترازو کا \"حد کے قریب\" اصول حد سے 2% نیچے کی رقوم نشان زد کرتا ہے۔"
        ),
    },
    "duplicate-payment": {
        "en": (
            "A duplicate payment is the same bill paid twice — usually by accident: an "
            "invoice entered twice, a re-send mistaken for a new bill. It costs the client "
            "real money and is easy to miss by eye, which is why it is checked mechanically. "
            "Tarazu flags the same amount to the same party within a few days, and one "
            "invoice settled by two ledger rows. Ask \"any duplicate payments?\" to see yours."
        ),
        "ur": (
            "دوہری ادائیگی ایک ہی بل کی دو بار ادائیگی ہے — عموماً غلطی سے: انوائس دو بار درج ہو گئی، "
            "یا دوبارہ بھیجی گئی انوائس کو نیا بل سمجھ لیا گیا۔ اس سے کلائنٹ کی اصل رقم جاتی ہے اور نظر سے چھپنا آسان ہے، "
            "اسی لیے یہ مشینی طریقے سے جانچی جاتی ہے۔ ترازو ایک ہی فریق کو چند دنوں کے اندر ایک ہی رقم، "
            "اور ایک انوائس جو دو لیجر قطاروں سے کلی ہو، نشان زد کرتا ہے۔ اپنے کیس کے لیے پوچھیں: \"کوئی دوہری ادائیگی؟\""
        ),
    },
    "matching": {
        "en": (
            "Matching is the comparison at the heart of reconciliation. Tarazu matches each "
            "ledger row against the bank statement and the invoices: matched means amount "
            "and date both agree; partial means the right counterpart exists but something "
            "differs (a date off by days, a small amount gap) — look, but it may be timing; "
            "unmatched means nothing behind the row at all, which is where fictitious "
            "payments hide. Ask \"which items are unmatched?\" to start with the sharpest "
            "question first."
        ),
        "ur": (
            "میلان (میچنگ) وہ موازنہ ہے جو مطابقت کے مرکز میں ہے۔ ترازو لیجر کی ہر قطار کو بینک اسٹیٹمنٹ اور انوائسز سے ملاتا ہے: "
            "مماثل کا مطلب رقم اور تاریخ دونوں متفق ہیں؛ جزوی کا مطلب صحیح ہم منصب موجود ہے مگر کچھ فرق ہے "
            "(کچھ دن کی تاریخ، تھوڑا رقم کا فرق) — دیکھیں، مگر یہ ٹائمنگ بھی ہو سکتی ہے؛ "
            "غیر مماثل کا مطلب قطار کے پیچھے کچھ بھی نہیں، اور فرضی ادائیگیاں وہیں چھپتی ہیں۔ "
            "سب سے تیز سوال پہلے پوچھنے کے لیے کہیں: \"کون سے آئٹم غیر مماثل ہیں؟\""
        ),
    },
    "audit-trail": {
        "en": (
            "An audit trail is the unbroken record of who did what, and when — the thing "
            "that lets a third party re-verify the work months later. Tarazu's trail is "
            "append-only: every upload, every flag, every decision, every question you ask "
            "here is written to it, and nothing — not you, not the system — can edit or "
            "delete an entry. That is enforced in the database itself, not by good "
            "behaviour. Ask \"what happened in this case?\" to read this engagement's own "
            "history."
        ),
        "ur": (
            "آڈٹ ٹریل اس کام کا مسلسل ریکارڈ ہے کہ کس نے کیا کیا اور کب — یہی چیز تیسرے شخص کو مہینوں بعد کام دوبارہ جانچنے دیتی ہے۔ "
            "ترازو کا ٹریل صرف جمع ہونے والا ہے: ہر اپ لوڈ، ہر نشانی، ہر فیصلہ، آپ کا یہاں پوچھا گیا ہر سوال اس میں لکھا جاتا ہے، "
            "اور کچھ بھی — نہ آپ، نہ سسٹم — کوئی اندراج بدل یا مٹ نہیں سکتا۔ یہ بات ڈیٹابیس خود پر لاگو کرتی ہے، دیانت پر نہیں۔ "
            "اس کیس کی اپنی تاریخ پڑھنے کے لیے پوچھیں: \"اس کیس میں کیا ہوا؟\""
        ),
    },
    "evidence": {
        "en": (
            "Evidence, in an audit, is the independent document behind a claim — the bank "
            "line proves the money moved; the invoice proves it was owed; the ledger alone "
            "proves nothing, because the client writes it. That is why Tarazu never takes a "
            "ledger row on trust: each one is matched against those independent sources, and "
            "rows short of evidence are surfaced rather than smoothed over. Ask \"which rows "
            "are missing evidence?\" for this case's gaps."
        ),
        "ur": (
            "آڈٹ میں ثبوت کسی دعوے کے پیچھے کی آزاد دستاویز ہے — بینک کی قطار ثابت کرتی ہے کہ رقم گئی؛ "
            "انوائس ثابت کرتی ہے کہ ادائیگی واجب الادا تھی؛ لیجر اکیلے کچھ ثابت نہیں کرتا، کیونکہ وہ کلائنٹ خود لکھتا ہے۔ "
            "اسی لیے ترازو لیجر کی قطار پر بھروسہ نہیں کرتا: ہر قطار ان آزاد مآخذ سے ملائی جاتی ہے، "
            "اور جو قطاریں ثبوت سے خالی ہیں وہ چھپائی نہیں جاتیں۔ اپنے کیس کے خلا دیکھنے کے لیے پوچھیں: \"کون سی قطاریں ثبوت سے خالی ہیں؟\""
        ),
    },
    "ledger": {
        "en": (
            "A ledger is the client's own book of payments — usually a spreadsheet — and it "
            "is the starting point of this audit, not the truth. The client writes it, so a "
            "dishonest client can write anything into it; the bank statement and the "
            "invoices are the independent voices it is checked against. In Tarazu the "
            "ledger is read by plain spreadsheet code, no AI involved, and every row keeps "
            "the sheet row it came from."
        ),
        "ur": (
            "لیجر کلائنٹ کی اپنی ادائیگیوں کی کتاب ہے — عموماً ایک اسپریڈ شیٹ — اور یہ اس آڈٹ کا نقطہ آغاز ہے، سچ نہیں۔ "
            "یہ کلائنٹ خود لکھتا ہے، اس لیے بے ایمان کلائنٹ اس میں کچھ بھی لکھ سکتا ہے؛ "
            "بینک اسٹیٹمنٹ اور انوائسز وہ آزاد آوازیں ہیں جن سے اس کی جانچ ہوتی ہے۔ "
            "ترازو میں لیجر سادہ اسپریڈ شیٹ کوڈ سے پڑھا جاتا ہے، کوئی AI شامل نہیں، اور ہر قطار اپنی شیٹ قطار نمبر ساتھ رکھتی ہے۔"
        ),
    },
    "bank-statement": {
        "en": (
            "A bank statement is the bank's own record of the account — the closest thing "
            "to an independent witness an audit has. Money that left the account is on it, "
            "money that only exists on paper is not, which is why the statement is the "
            "anchor every ledger row is matched against. Tarazu reads it with a vision "
            "model, and every value it reads keeps the page and the snippet it came from, "
            "so you can check the machine against the paper."
        ),
        "ur": (
            "بینک اسٹیٹمنٹ بینک کا اکاؤنٹ کا اپنا ریکارڈ ہے — آڈٹ کے پاس آزاد گواہ کا سب سے قریب روپ۔ "
            "جو رقم اکاؤنٹ سے گئی وہ اس پر ہے، جو رقم صرف کاغذ پر ہے وہ نہیں، اسی لیے یہ وہ لنگر ہے "
            "جس سے لیجر کی ہر قطار ملائی جاتی ہے۔ ترازو اسے وژن ماڈل سے پڑھتا ہے، اور جو قدر پڑھی جاتی ہے "
            "وہ اپنا صفحہ اور اقتباس ساتھ رکھتی ہے، تاکہ آپ مشین کا کاغذ سے مقابلہ کر سکیں۔"
        ),
    },
    "materiality": {
        "en": (
            "Materiality is the professional word for \"big enough to matter\". An audit "
            "does not check every paisa to the same depth; it focuses where an error would "
            "change a reader's opinion of the books. A missing receipt for a small tea "
            "bill and the same gap on a large payment are not the same finding. Tarazu "
            "helps you see the sizes — largest payments, totals by vendor — so you can "
            "point your attention where it matters."
        ),
        "ur": (
            "اہمیت (میٹیریلٹی) کا پیشہ ورانہ مطلب ہے \"اتنا بڑا کہ فرق ڈالے\"۔ آڈٹ ہر پیسے کو ایک گہرائی سے نہیں جانچتا؛ "
            "وہ وہاں توجہ دیتا ہے جہاں غلطی کتابوں پر قاری کی رائے بدل دے۔ چھوٹے چائے کے بل کی گم رسید "
            "اور بڑی ادائیگی پر وہی خلا برابر نہیں۔ ترازو سائز دکھانے میں مدد دیتا ہے — سب سے بڑی ادائیگیاں، وینڈر کے حساب سے مجموعی — "
            "تاکہ آپ اپنی توجہ وہاں رکھیں جہاں وہ معنی رکھتی ہے۔"
        ),
    },
    "sampling": {
        "en": (
            "Sampling is checking some of the many and reasoning about the rest — what "
            "auditors do when a ledger has thousands of rows. The choice of which rows to "
            "look at is where an audit earns its keep: random samples, high-value rows, "
            "and rule-based picks each answer a different question. Tarazu's flags are "
            "rule-based picks — every row is screened by the same published rules, and "
            "you decide which flagged rows become findings."
        ),
        "ur": (
            "نمونہ لینا (سیمپلنگ) بہت سے میں سے کچھ جانچ کر باقی کے بارے میں نتیجہ نکالنا ہے — یہی آڈیٹر کرتے ہیں "
            "جب لیجر میں ہزاروں قطاریں ہوں۔ یہ انتخاب کہ کون سی قطاریں دیکھنی ہیں وہی آڈٹ کی اصل مہارت ہے: "
            "رینڈم نمونے، بڑی رقم کی قطاریں، اور اصول پر مبنی چناؤ الگ الگ سوال کا جواب دیتے ہیں۔ "
            "ترازو کی نشانیاں اصول پر مبنی چناؤ ہیں — ہر قطار اسی شائع شدہ اصول سے جانچی جاتی ہے، اور آپ فیصلہ کرتے ہیں "
            "کہ کون سی نشان زد قطار باب بنے۔"
        ),
    },
    "human-in-the-loop": {
        "en": (
            "Human-in-the-loop means the machine may narrow the work, never close it. "
            "Tarazu's AI reads documents and its rules raise flags — but approving or "
            "rejecting an item is an act of professional judgement with your name on it, "
            "so it stays with you, and every decision you make is recorded as yours in the "
            "trail. The assistant you are talking to is under the same rule: it explains "
            "and computes, it never decides."
        ),
        "ur": (
            "ہیومن اِن دی لوپ کا مطلب ہے: مشین کام تنگ کر سکتی ہے، مکمل نہیں کرتی۔ "
            "ترازو کا AI دستاویزیں پڑھتا ہے اور اس کے اصول نشانیاں اٹھاتے ہیں — مگر کسی آئٹم کی منظوری یا رد کا فیصلہ "
            "پیشہ ورانہ فیصلہ ہے جس پر آپ کا نام ہے، اس لیے وہ آپ کے پاس رہتا ہے، اور آپ کا ہر فیصلہ ٹریل میں آپ ہی کے نام سے درج ہوتا ہے۔ "
            "جس اسسٹنٹ سے آپ بات کر رہے ہیں وہی اصول مانتا ہے: وہ سمجھاتا اور حساب کرتا ہے، فیصلہ کبھی نہیں کرتا۔"
        ),
    },
    "provenance": {
        "en": (
            "Provenance is the answer to \"says who?\" — where a value came from, exactly. "
            "Every number Tarazu shows carries its source: the document, the page, and the "
            "snippet for things a model read, or the spreadsheet row for things code read. "
            "It is what lets you check the machine's reading against the paper yourself, "
            "and it is why an answer from this assistant always cites where it stands."
        ),
        "ur": (
            "ماخذ (پروویننس) اس سوال کا جواب ہے: \"کہتا کون ہے؟\" — کوئی قدر کہاں سے آئی، بالکل۔ "
            "ترازو کا دکھایا ہر عدد اپنا ذریعہ ساتھ رکھتا ہے: دستاویز، صفحہ اور اقتباس اگر ماڈل نے پڑھا، "
            "یا اسپریڈ شیٹ کی قطار اگر کوڈ نے پڑھا۔ یہی چیز آپ کو مشین کی پڑھائی کاغذ سے خود جانچنے دیتی ہے، "
            "اور اسی لیے اس اسسٹنٹ کا ہر جواب بتاتا ہے کہ وہ کہاں کھڑا ہے۔"
        ),
    },
    "tolerance": {
        "en": (
            "A tolerance is the small difference two records may show and still count as "
            "agreeing — a bank posting a day after the ledger dates it, a rounding of "
            "rupees on a large amount. Zero tolerance would drown an audit in noise, so "
            "Tarazu's matching allows a date window and a small amount gap, marks those "
            "matches as partial, and tells you the exact difference so you can judge "
            "whether it is timing or something worth chasing."
        ),
        "ur": (
            "رخصت (ٹالرنس) وہ چھوٹا فرق ہے جو دو ریکارڈ دکھا کر بھی متفق سمجھے جائیں — "
            "بینک ادائیگی ایک دن بعد درج کرے، یا بڑی رقم پر چند روپے کا فرق۔ صفر رخصت آڈٹ کو شور میں ڈبو دے گی، "
            "اسی لیے ترازو کے میچنگ میں تاریخ کی مہلت اور تھوڑا رقم کا فرق شامل ہے، ایسے میچ جزوی کہلاتے ہیں، "
            "اور آپ کو بالکل فرق بتایا جاتا ہے تاکہ آپ فیصلہ کر سکیں کہ یہ ٹائمنگ ہے یا پیچھا کرنے والی بات۔"
        ),
    },
}

#: Topic keywords, matched like every other planner keyword. One tuple per
#: topic; a hit only matters together with an educational marker (see
#: `planner.plan`), except for the definitional markers, which alone are
#: enough — "what is Benford's law?" should explain the law, not read out the
#: case's result.
TOPIC_WORDS: dict[str, tuple[str, ...]] = {
    "reconciliation": ("reconcil*", "three-way match*", "three way match*", "تین طرفہ مطابقت", "مطابقت"),
    "benford": ("benford*", "بینفورڈ"),
    "red-flag": ("red flag*", "سرخ نشانی"),
    "approval-limit": ("approval limit*", "منظوری کی حد"),
    "duplicate-payment": ("duplicate payment*", "دوہری ادائیگی"),
    "matching": ("matched", "unmatched", "partial match*", "match strength*", "مماثل", "غیر مماثل", "جزوی"),
    "audit-trail": ("audit trail*", "آڈٹ ٹریل", "ٹریل"),
    "evidence": ("evidence", "supporting document*", "ثبوت"),
    "ledger": ("ledger", "لیجر"),
    "bank-statement": ("bank statement*", "بینک اسٹیٹمنٹ"),
    "materiality": ("materialit*", "material", "اہمیت"),
    "sampling": ("sampl*", "نمونہ"),
    "human-in-the-loop": ("human in the loop", "human-in-the-loop", "why do i have to approve", "approve everything myself", "انسانی فیصلہ"),
    "provenance": ("provenance", "source of a value", "ماخذ"),
    "tolerance": ("tolerance", "date window*", "رخصت"),
}

#: Topics that have a dedicated case-reading intent. A definitional question
#: ("what is a duplicate payment?") still routes to the glossary; a plain
#: mention ("any duplicate payments?") routes to the case data, which is the
#: richer answer when the user is asking about *their* books.
DEDICATED_TOPICS = frozenset({"benford", "red-flag", "duplicate-payment", "matching"})
