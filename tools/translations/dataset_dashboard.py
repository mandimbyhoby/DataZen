"""Translations for the dynamic dataset quality dashboard labels."""

_KEYS = (
    "Lignes après nettoyage",
    "Doublons exacts",
    "Doublons potentiels",
    "Valeurs « Inconnu »",
    "Valeurs aberrantes",
    "Erreurs restantes",
    "identifiant",
    "email",
    "téléphone",
    "date",
    "numérique",
    "catégorie",
    "texte",
    "complétude",
    "validité",
    "unicité",
    "cohérence",
    "conformité",
    "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.",
    "%(count)s valeur(s) sont actuellement « Inconnu ».",
    "%(count)s doublon(s) potentiel(s) nécessitent une vérification.",
    "%(count)s valeur(s) aberrante(s) détectée(s) sur les colonnes numériques.",
    "Email invalide",
    "Valeur numérique invalide",
    "Date invalide",
    "Téléphone non standard",
    "YYYY-MM-DD",
    "Unknown",
)

_VALUES = {
    "en": ("Rows after cleaning", "Exact duplicates", "Potential duplicates", "Unknown values", "Outliers", "Remaining errors", "identifier", "email", "phone", "date", "numerical", "category", "text", "completeness", "validity", "uniqueness", "consistency", "conformity"),
    "es": ("Filas tras la limpieza", "Duplicados exactos", "Posibles duplicados", "Valores desconocidos", "Valores atípicos", "Errores restantes", "identificador", "correo electrónico", "teléfono", "fecha", "numérico", "categoría", "texto", "completitud", "validez", "unicidad", "coherencia", "conformidad"),
    "de": ("Zeilen nach der Bereinigung", "Exakte Duplikate", "Mögliche Duplikate", "Unbekannte Werte", "Ausreißer", "Verbleibende Fehler", "Kennung", "E-Mail", "Telefon", "Datum", "numerisch", "Kategorie", "Text", "Vollständigkeit", "Gültigkeit", "Eindeutigkeit", "Konsistenz", "Konformität"),
    "it": ("Righe dopo la pulizia", "Duplicati esatti", "Duplicati potenziali", "Valori sconosciuti", "Valori anomali", "Errori rimanenti", "identificativo", "email", "telefono", "data", "numerico", "categoria", "testo", "completezza", "validità", "unicità", "coerenza", "conformità"),
    "pt": ("Linhas após a limpeza", "Duplicados exatos", "Duplicados potenciais", "Valores desconhecidos", "Valores atípicos", "Erros restantes", "identificador", "email", "telefone", "data", "numérico", "categoria", "texto", "completude", "validade", "unicidade", "coerência", "conformidade"),
    "nl": ("Rijen na opschoning", "Exacte duplicaten", "Mogelijke duplicaten", "Onbekende waarden", "Uitschieters", "Resterende fouten", "identificatie", "e-mail", "telefoon", "datum", "numeriek", "categorie", "tekst", "volledigheid", "geldigheid", "uniciteit", "consistentie", "conformiteit"),
    "ar": ("الصفوف بعد التنظيف", "التكرارات المطابقة", "التكرارات المحتملة", "القيم غير المعروفة", "القيم الشاذة", "الأخطاء المتبقية", "المعرّف", "البريد الإلكتروني", "الهاتف", "التاريخ", "رقمي", "الفئة", "النص", "الاكتمال", "الصلاحية", "التفرّد", "الاتساق", "المطابقة"),
    "zh-hans": ("清理后的行数", "完全重复项", "潜在重复项", "未知值", "异常值", "剩余错误", "标识符", "电子邮件", "电话", "日期", "数值", "类别", "文本", "完整性", "有效性", "唯一性", "一致性", "符合性"),
    "ru": ("Строк после очистки", "Точные дубликаты", "Возможные дубликаты", "Неизвестные значения", "Выбросы", "Оставшиеся ошибки", "идентификатор", "электронная почта", "телефон", "дата", "числовой", "категория", "текст", "полнота", "достоверность", "уникальность", "согласованность", "соответствие"),
    "ja": ("クリーニング後の行数", "完全な重複", "重複の可能性", "不明な値", "外れ値", "残存エラー", "識別子", "メール", "電話番号", "日付", "数値", "カテゴリ", "テキスト", "完全性", "妥当性", "一意性", "整合性", "適合性"),
    "ko": ("정리 후 행", "정확히 중복된 항목", "중복 가능 항목", "알 수 없는 값", "이상치", "남은 오류", "식별자", "이메일", "전화번호", "날짜", "숫자", "범주", "텍스트", "완전성", "유효성", "고유성", "일관성", "적합성"),
    "sv": ("Rader efter rensning", "Exakta dubbletter", "Möjliga dubbletter", "Okända värden", "Avvikande värden", "Återstående fel", "identifierare", "e-post", "telefon", "datum", "numerisk", "kategori", "text", "fullständighet", "giltighet", "unikhet", "konsekvens", "överensstämmelse"),
    "da": ("Rækker efter oprydning", "Eksakte dubletter", "Mulige dubletter", "Ukendte værdier", "Afvigende værdier", "Resterende fejl", "identifikator", "e-mail", "telefon", "dato", "numerisk", "kategori", "tekst", "fuldstændighed", "gyldighed", "unikhed", "konsistens", "overensstemmelse"),
    "fi": ("Riviä siivouksen jälkeen", "Tarkat kaksoiskappaleet", "Mahdolliset kaksoiskappaleet", "Tuntemattomat arvot", "Poikkeavat arvot", "Jäljellä olevat virheet", "tunniste", "sähköposti", "puhelin", "päivämäärä", "numeerinen", "luokka", "teksti", "kattavuus", "kelpoisuus", "yksilöllisyys", "johdonmukaisuus", "vaatimustenmukaisuus"),
    "cs": ("Řádky po vyčištění", "Přesné duplicity", "Možné duplicity", "Neznámé hodnoty", "Odlehlé hodnoty", "Zbývající chyby", "identifikátor", "e-mail", "telefon", "datum", "číselný", "kategorie", "text", "úplnost", "platnost", "jedinečnost", "konzistence", "shoda"),
}

DASHBOARD_TRANSLATIONS = {
    code: dict(zip(_KEYS, values)) for code, values in _VALUES.items()
}
