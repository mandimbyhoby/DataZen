"""Traductions des cartes « offre » de la page d'accueil (section 25 du CSS).

Chaque carte présente une fonctionnalité réelle : formats acceptés (3),
corrections automatiques activées par défaut (6), dimensions du score (5),
formats d'export du fichier nettoyé (3).
"""

_KEYS = (
    "Populaire",
    "formats acceptés",
    "corrections automatiques",
    "dimensions mesurées",
    "formats d'export",
    "CSV, XLSX et XLS",
    "Séparateur détecté automatiquement",
    "Jusqu'à 20 Mo par fichier",
    "Espaces, casse et e-mails",
    "Téléphones, dates et montants",
    "Doublons signalés, jamais supprimés d'office",
    "Complétude, validité et unicité",
    "Cohérence et conformité",
    "Chaque point perdu expliqué",
    "CSV, Excel et JSON",
    "Rapports PDF et HTML",
    "Journal complet des modifications",
)

_VALUES = {
    "en": ("Popular", "accepted formats", "automatic corrections", "measured dimensions", "export formats", "CSV, XLSX and XLS", "Separator detected automatically", "Up to 20 MB per file", "Spaces, case and e-mails", "Phones, dates and amounts", "Duplicates flagged, never deleted by default", "Completeness, validity and uniqueness", "Consistency and conformity", "Every lost point explained", "CSV, Excel and JSON", "PDF and HTML reports", "Full change log"),
    "es": ("Popular", "formatos admitidos", "correcciones automáticas", "dimensiones medidas", "formatos de exportación", "CSV, XLSX y XLS", "Separador detectado automáticamente", "Hasta 20 MB por archivo", "Espacios, mayúsculas y correos", "Teléfonos, fechas e importes", "Duplicados señalados, nunca eliminados de oficio", "Completitud, validez y unicidad", "Coherencia y conformidad", "Cada punto perdido explicado", "CSV, Excel y JSON", "Informes PDF y HTML", "Registro completo de cambios"),
    "de": ("Beliebt", "unterstützte Formate", "automatische Korrekturen", "gemessene Dimensionen", "Exportformate", "CSV, XLSX und XLS", "Trennzeichen automatisch erkannt", "Bis zu 20 MB pro Datei", "Leerzeichen, Groß-/Kleinschreibung und E-Mails", "Telefonnummern, Datumsangaben und Beträge", "Duplikate markiert, nie automatisch gelöscht", "Vollständigkeit, Gültigkeit und Eindeutigkeit", "Konsistenz und Konformität", "Jeder verlorene Punkt erklärt", "CSV, Excel und JSON", "PDF- und HTML-Berichte", "Vollständiges Änderungsprotokoll"),
    "it": ("Popolare", "formati supportati", "correzioni automatiche", "dimensioni misurate", "formati di esportazione", "CSV, XLSX e XLS", "Separatore rilevato automaticamente", "Fino a 20 MB per file", "Spazi, maiuscole ed e-mail", "Telefoni, date e importi", "Duplicati segnalati, mai eliminati d'ufficio", "Completezza, validità e unicità", "Coerenza e conformità", "Ogni punto perso spiegato", "CSV, Excel e JSON", "Report PDF e HTML", "Registro completo delle modifiche"),
    "pt": ("Popular", "formatos aceites", "correções automáticas", "dimensões medidas", "formatos de exportação", "CSV, XLSX e XLS", "Separador detetado automaticamente", "Até 20 MB por ficheiro", "Espaços, maiúsculas e e-mails", "Telefones, datas e montantes", "Duplicados assinalados, nunca eliminados por defeito", "Completude, validade e unicidade", "Coerência e conformidade", "Cada ponto perdido explicado", "CSV, Excel e JSON", "Relatórios PDF e HTML", "Registo completo de alterações"),
    "nl": ("Populair", "ondersteunde formaten", "automatische correcties", "gemeten dimensies", "exportformaten", "CSV, XLSX en XLS", "Scheidingsteken automatisch herkend", "Tot 20 MB per bestand", "Spaties, hoofdletters en e-mails", "Telefoonnummers, datums en bedragen", "Duplicaten gemarkeerd, nooit standaard verwijderd", "Volledigheid, geldigheid en uniciteit", "Consistentie en conformiteit", "Elk verloren punt uitgelegd", "CSV, Excel en JSON", "PDF- en HTML-rapporten", "Volledig wijzigingslogboek"),
    "ar": ("الأكثر شيوعًا", "صيغ مدعومة", "تصحيحات تلقائية", "أبعاد مُقاسة", "صيغ تصدير", "CSV وXLSX وXLS", "اكتشاف الفاصل تلقائيًا", "حتى 20 ميغابايت لكل ملف", "المسافات وحالة الأحرف والبريد الإلكتروني", "الهواتف والتواريخ والمبالغ", "تُرصد التكرارات ولا تُحذف تلقائيًا أبدًا", "الاكتمال والصلاحية والتفرّد", "الاتساق والمطابقة", "شرح كل نقطة مفقودة", "CSV وExcel وJSON", "تقارير PDF وHTML", "سجل كامل للتعديلات"),
    "zh-hans": ("热门", "支持的格式", "项自动纠正", "个质量维度", "种导出格式", "CSV、XLSX 和 XLS", "自动检测分隔符", "每个文件最大 20 MB", "空格、大小写和电子邮件", "电话、日期和金额", "标记重复项，绝不默认删除", "完整性、有效性和唯一性", "一致性和规范性", "解释每一处扣分", "CSV、Excel 和 JSON", "PDF 和 HTML 报告", "完整的修改日志"),
    "ru": ("Популярное", "поддерживаемых формата", "автоматических исправлений", "измеряемых показателей", "формата экспорта", "CSV, XLSX и XLS", "Разделитель определяется автоматически", "До 20 МБ на файл", "Пробелы, регистр и e-mail", "Телефоны, даты и суммы", "Дубликаты помечаются, но не удаляются по умолчанию", "Полнота, валидность и уникальность", "Согласованность и соответствие", "Объяснение каждого потерянного балла", "CSV, Excel и JSON", "Отчёты PDF и HTML", "Полный журнал изменений"),
    "ja": ("人気", "対応形式", "件の自動修正", "つの品質指標", "種類のエクスポート形式", "CSV・XLSX・XLS", "区切り文字を自動検出", "1 ファイル最大 20 MB", "空白・大文字小文字・メール", "電話番号・日付・金額", "重複は通知のみで自動削除はしません", "完全性・妥当性・一意性", "一貫性・適合性", "減点理由をすべて説明", "CSV・Excel・JSON", "PDF・HTML レポート", "完全な変更履歴"),
    "ko": ("인기", "지원 형식", "자동 수정", "측정 지표", "내보내기 형식", "CSV, XLSX 및 XLS", "구분자 자동 감지", "파일당 최대 20MB", "공백, 대소문자, 이메일", "전화번호, 날짜, 금액", "중복은 표시만 하고 기본적으로 삭제하지 않음", "완전성, 유효성, 고유성", "일관성과 적합성", "감점 사유를 모두 설명", "CSV, Excel, JSON", "PDF 및 HTML 보고서", "전체 변경 기록"),
    "tr": ("Popüler", "desteklenen biçim", "otomatik düzeltme", "ölçülen boyut", "dışa aktarma biçimi", "CSV, XLSX ve XLS", "Ayırıcı otomatik algılanır", "Dosya başına 20 MB'a kadar", "Boşluklar, büyük/küçük harf ve e-postalar", "Telefonlar, tarihler ve tutarlar", "Yinelenenler işaretlenir, varsayılan olarak asla silinmez", "Eksiksizlik, geçerlilik ve benzersizlik", "Tutarlılık ve uygunluk", "Kaybedilen her puan açıklanır", "CSV, Excel ve JSON", "PDF ve HTML raporları", "Eksiksiz değişiklik günlüğü"),
    "hi": ("लोकप्रिय", "समर्थित प्रारूप", "स्वचालित सुधार", "मापे गए आयाम", "निर्यात प्रारूप", "CSV, XLSX और XLS", "विभाजक अपने-आप पहचाना जाता है", "प्रति फ़ाइल 20 MB तक", "रिक्त स्थान, अक्षरों का आकार और ई-मेल", "फ़ोन, तिथियाँ और राशियाँ", "डुप्लिकेट चिह्नित होते हैं, डिफ़ॉल्ट रूप से कभी हटाए नहीं जाते", "पूर्णता, वैधता और अद्वितीयता", "संगति और अनुरूपता", "हर कटे अंक की व्याख्या", "CSV, Excel और JSON", "PDF और HTML रिपोर्ट", "परिवर्तनों का पूरा लॉग"),
    "pl": ("Popularne", "obsługiwane formaty", "automatycznych poprawek", "mierzonych wymiarów", "formaty eksportu", "CSV, XLSX i XLS", "Separator wykrywany automatycznie", "Do 20 MB na plik", "Spacje, wielkość liter i e-maile", "Telefony, daty i kwoty", "Duplikaty oznaczane, nigdy nieusuwane domyślnie", "Kompletność, poprawność i unikalność", "Spójność i zgodność", "Wyjaśnienie każdego utraconego punktu", "CSV, Excel i JSON", "Raporty PDF i HTML", "Pełny dziennik zmian"),
    "sv": ("Populär", "format som stöds", "automatiska korrigeringar", "uppmätta dimensioner", "exportformat", "CSV, XLSX och XLS", "Avgränsare identifieras automatiskt", "Upp till 20 MB per fil", "Mellanslag, versaler och e-post", "Telefonnummer, datum och belopp", "Dubbletter flaggas, tas aldrig bort som standard", "Fullständighet, giltighet och unikhet", "Konsekvens och överensstämmelse", "Varje förlorad poäng förklaras", "CSV, Excel och JSON", "PDF- och HTML-rapporter", "Fullständig ändringslogg"),
    "da": ("Populær", "understøttede formater", "automatiske rettelser", "målte dimensioner", "eksportformater", "CSV, XLSX og XLS", "Separator registreres automatisk", "Op til 20 MB pr. fil", "Mellemrum, store/små bogstaver og e-mails", "Telefonnumre, datoer og beløb", "Dubletter markeres, slettes aldrig som standard", "Fuldstændighed, gyldighed og entydighed", "Konsistens og overensstemmelse", "Hvert tabt point forklares", "CSV, Excel og JSON", "PDF- og HTML-rapporter", "Komplet ændringslog"),
    "fi": ("Suosittu", "tuettua muotoa", "automaattista korjausta", "mitattua ulottuvuutta", "vientimuotoa", "CSV, XLSX ja XLS", "Erotin tunnistetaan automaattisesti", "Enintään 20 Mt tiedostoa kohden", "Välilyönnit, kirjainkoko ja sähköpostit", "Puhelinnumerot, päivämäärät ja summat", "Kaksoiskappaleet merkitään, niitä ei koskaan poisteta oletuksena", "Kattavuus, oikeellisuus ja yksilöllisyys", "Johdonmukaisuus ja vaatimustenmukaisuus", "Jokainen menetetty piste selitetään", "CSV, Excel ja JSON", "PDF- ja HTML-raportit", "Täydellinen muutosloki"),
    "cs": ("Oblíbené", "podporované formáty", "automatických oprav", "měřených dimenzí", "formáty exportu", "CSV, XLSX a XLS", "Oddělovač rozpoznán automaticky", "Až 20 MB na soubor", "Mezery, velikost písmen a e-maily", "Telefony, data a částky", "Duplicity označeny, nikdy automaticky nesmazány", "Úplnost, platnost a jedinečnost", "Konzistence a shoda", "Každý ztracený bod vysvětlen", "CSV, Excel a JSON", "Zprávy PDF a HTML", "Úplný protokol změn"),
    "ro": ("Popular", "formate acceptate", "corecturi automate", "dimensiuni măsurate", "formate de export", "CSV, XLSX și XLS", "Separator detectat automat", "Până la 20 MB per fișier", "Spații, majuscule și e-mailuri", "Telefoane, date și sume", "Duplicatele sunt semnalate, niciodată șterse implicit", "Completitudine, validitate și unicitate", "Coerență și conformitate", "Fiecare punct pierdut explicat", "CSV, Excel și JSON", "Rapoarte PDF și HTML", "Jurnal complet al modificărilor"),
    "vi": ("Phổ biến", "định dạng được hỗ trợ", "sửa lỗi tự động", "chiều đo chất lượng", "định dạng xuất", "CSV, XLSX và XLS", "Tự động nhận diện dấu phân cách", "Tối đa 20 MB mỗi tệp", "Khoảng trắng, chữ hoa/thường và e-mail", "Số điện thoại, ngày và số tiền", "Bản trùng lặp được đánh dấu, không bao giờ tự động xóa", "Tính đầy đủ, hợp lệ và duy nhất", "Tính nhất quán và tuân thủ", "Giải thích từng điểm bị trừ", "CSV, Excel và JSON", "Báo cáo PDF và HTML", "Nhật ký thay đổi đầy đủ"),
    "th": ("ยอดนิยม", "รูปแบบที่รองรับ", "การแก้ไขอัตโนมัติ", "มิติที่วัด", "รูปแบบการส่งออก", "CSV, XLSX และ XLS", "ตรวจจับตัวคั่นโดยอัตโนมัติ", "สูงสุด 20 MB ต่อไฟล์", "ช่องว่าง ตัวพิมพ์ และอีเมล", "โทรศัพท์ วันที่ และจำนวนเงิน", "แจ้งข้อมูลซ้ำ แต่ไม่ลบโดยอัตโนมัติ", "ความครบถ้วน ความถูกต้อง และความไม่ซ้ำ", "ความสอดคล้องและการเป็นไปตามข้อกำหนด", "อธิบายทุกคะแนนที่หายไป", "CSV, Excel และ JSON", "รายงาน PDF และ HTML", "บันทึกการแก้ไขฉบับเต็ม"),
    "id": ("Populer", "format didukung", "koreksi otomatis", "dimensi diukur", "format ekspor", "CSV, XLSX, dan XLS", "Pemisah terdeteksi otomatis", "Hingga 20 MB per file", "Spasi, huruf besar/kecil, dan e-mail", "Telepon, tanggal, dan jumlah", "Duplikat ditandai, tidak pernah dihapus secara bawaan", "Kelengkapan, validitas, dan keunikan", "Konsistensi dan kesesuaian", "Setiap poin yang hilang dijelaskan", "CSV, Excel, dan JSON", "Laporan PDF dan HTML", "Log perubahan lengkap"),
}

for _code, _texts in _VALUES.items():
    if len(_texts) != len(_KEYS):
        raise ValueError(f"feature_plans : {_code} a {len(_texts)} libellés au lieu de {len(_KEYS)}")

FEATURE_PLAN_TRANSLATIONS = {
    code: dict(zip(_KEYS, texts)) for code, texts in _VALUES.items()
}
