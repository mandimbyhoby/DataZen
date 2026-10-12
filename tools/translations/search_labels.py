"""Libellés de la recherche globale (palette Ctrl+K).

Ces chaînes sont produites par ``core/services/search.py`` : elles décrivent
la provenance d'un résultat (« colonne : email », « opération : … ») ou son
état (« actif », « révoqué »). Elles doivent donc être traduites comme le
reste de l'interface.

Les clés sont réparties en deux tranches alignées : chaque langue fournit un
couple de tuples de même longueur, vérifié à l'import.
"""

from __future__ import annotations

KEYS_A: tuple[str, ...] = (
    "%(count)s colonnes",
    "%(count)s lignes",
    "Jeton",
    "Règle",
    "URL",
    "actif",
)

KEYS_B: tuple[str, ...] = (
    "colonne : %(name)s",
    "détail",
    "inactive",
    "opération : %(name)s",
    "révoqué",
)

_VALUES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "en": (
        ("%(count)s columns", "%(count)s rows", "Token", "Rule", "URL", "active"),
        ("column: %(name)s", "detail", "inactive", "operation: %(name)s", "revoked"),
    ),
    "es": (
        ("%(count)s columnas", "%(count)s filas", "Token", "Regla", "URL", "activo"),
        ("columna: %(name)s", "detalle", "inactiva", "operación: %(name)s", "revocado"),
    ),
    "de": (
        ("%(count)s Spalten", "%(count)s Zeilen", "Token", "Regel", "URL", "aktiv"),
        ("Spalte: %(name)s", "Detail", "inaktiv", "Vorgang: %(name)s", "widerrufen"),
    ),
    "it": (
        ("%(count)s colonne", "%(count)s righe", "Token", "Regola", "URL", "attivo"),
        ("colonna: %(name)s", "dettaglio", "inattiva", "operazione: %(name)s", "revocato"),
    ),
    "pt": (
        ("%(count)s colunas", "%(count)s linhas", "Token", "Regra", "URL", "ativo"),
        ("coluna: %(name)s", "detalhe", "inativa", "operação: %(name)s", "revogado"),
    ),
    "nl": (
        ("%(count)s kolommen", "%(count)s rijen", "Token", "Regel", "URL", "actief"),
        ("kolom: %(name)s", "detail", "inactief", "bewerking: %(name)s", "ingetrokken"),
    ),
    "ar": (
        ("%(count)s أعمدة", "%(count)s صفوف", "رمز", "قاعدة", "عنوان URL", "نشط"),
        ("العمود: %(name)s", "تفاصيل", "غير نشطة", "العملية: %(name)s", "ملغى"),
    ),
    "zh-hans": (
        ("%(count)s 列", "%(count)s 行", "令牌", "规则", "网址", "有效"),
        ("列：%(name)s", "详情", "已停用", "操作：%(name)s", "已撤销"),
    ),
    "ru": (
        ("%(count)s столбцов", "%(count)s строк", "Токен", "Правило", "URL", "активен"),
        ("столбец: %(name)s", "подробности", "неактивна", "операция: %(name)s", "отозван"),
    ),
    "ja": (
        ("%(count)s 列", "%(count)s 行", "トークン", "ルール", "URL", "有効"),
        ("列: %(name)s", "詳細", "無効", "操作: %(name)s", "失効"),
    ),
    "ko": (
        ("%(count)s개 열", "%(count)s개 행", "토큰", "규칙", "URL", "활성"),
        ("열: %(name)s", "세부 정보", "비활성", "작업: %(name)s", "폐기됨"),
    ),
    "tr": (
        ("%(count)s sütun", "%(count)s satır", "Jeton", "Kural", "URL", "etkin"),
        ("sütun: %(name)s", "ayrıntı", "etkin değil", "işlem: %(name)s", "iptal edildi"),
    ),
    "hi": (
        ("%(count)s कॉलम", "%(count)s पंक्तियाँ", "टोकन", "नियम", "URL", "सक्रिय"),
        ("कॉलम: %(name)s", "विवरण", "निष्क्रिय", "ऑपरेशन: %(name)s", "निरस्त"),
    ),
    "pl": (
        ("%(count)s kolumn", "%(count)s wierszy", "Token", "Reguła", "URL", "aktywny"),
        ("kolumna: %(name)s", "szczegóły", "nieaktywna", "operacja: %(name)s", "unieważniony"),
    ),
    "sv": (
        ("%(count)s kolumner", "%(count)s rader", "Token", "Regel", "URL", "aktiv"),
        ("kolumn: %(name)s", "detalj", "inaktiv", "åtgärd: %(name)s", "återkallad"),
    ),
    "da": (
        ("%(count)s kolonner", "%(count)s rækker", "Token", "Regel", "URL", "aktiv"),
        ("kolonne: %(name)s", "detalje", "inaktiv", "handling: %(name)s", "tilbagekaldt"),
    ),
    "fi": (
        ("%(count)s saraketta", "%(count)s riviä", "Token", "Sääntö", "URL", "aktiivinen"),
        ("sarake: %(name)s", "tiedot", "ei käytössä", "toiminto: %(name)s", "peruutettu"),
    ),
    "cs": (
        ("%(count)s sloupců", "%(count)s řádků", "Token", "Pravidlo", "URL", "aktivní"),
        ("sloupec: %(name)s", "detail", "neaktivní", "operace: %(name)s", "odvoláno"),
    ),
    "ro": (
        ("%(count)s coloane", "%(count)s rânduri", "Token", "Regulă", "URL", "activ"),
        ("coloană: %(name)s", "detaliu", "inactivă", "operațiune: %(name)s", "revocat"),
    ),
    "vi": (
        ("%(count)s cột", "%(count)s dòng", "Token", "Quy tắc", "URL", "đang hoạt động"),
        ("cột: %(name)s", "chi tiết", "không hoạt động", "thao tác: %(name)s", "đã thu hồi"),
    ),
    "th": (
        ("%(count)s คอลัมน์", "%(count)s แถว", "โทเคน", "กฎ", "URL", "ใช้งานอยู่"),
        ("คอลัมน์: %(name)s", "รายละเอียด", "ไม่ใช้งาน", "การดำเนินการ: %(name)s", "เพิกถอนแล้ว"),
    ),
    "id": (
        ("%(count)s kolom", "%(count)s baris", "Token", "Aturan", "URL", "aktif"),
        ("kolom: %(name)s", "detail", "nonaktif", "operasi: %(name)s", "dicabut"),
    ),
}

for _code, (_first, _second) in _VALUES.items():
    if len(_first) != len(KEYS_A) or len(_second) != len(KEYS_B):
        raise ValueError(f"traductions désalignées pour {_code}")

SEARCH_LABEL_TRANSLATIONS: dict[str, dict[str, str]] = {
    code: dict(zip(KEYS_A, first)) | dict(zip(KEYS_B, second))
    for code, (first, second) in _VALUES.items()
}
