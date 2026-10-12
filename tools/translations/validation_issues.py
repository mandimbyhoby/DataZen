"""Translations for the dataset validation-issues review table."""

from .en import TRANSLATIONS as EN_TRANSLATIONS
from .es import TRANSLATIONS as ES_TRANSLATIONS
from .de import TRANSLATIONS as DE_TRANSLATIONS
from .it import TRANSLATIONS as IT_TRANSLATIONS
from .pt import TRANSLATIONS as PT_TRANSLATIONS
from .nl import TRANSLATIONS as NL_TRANSLATIONS
from .ar import TRANSLATIONS as AR_TRANSLATIONS
from .zh import TRANSLATIONS as ZH_TRANSLATIONS
from .ru import TRANSLATIONS as RU_TRANSLATIONS
from .ja import TRANSLATIONS as JA_TRANSLATIONS
from .ko import TRANSLATIONS as KO_TRANSLATIONS
from .sv import TRANSLATIONS as SV_TRANSLATIONS
from .da import TRANSLATIONS as DA_TRANSLATIONS
from .fi import TRANSLATIONS as FI_TRANSLATIONS
from .cs import TRANSLATIONS as CS_TRANSLATIONS

_ISSUE_OVERRIDES = {
    "en": {
        "Afficher les détails des anomalies": "Show anomaly details",
        "Ligne": "Row",
        "Colonne": "Column",
        "Valeur": "Value",
        "Motif": "Reason",
        "Email invalide": "Invalid email",
        "Téléphone non standard": "Non-standard phone number",
        "Date invalide": "Invalid date",
        "Valeur numérique invalide": "Invalid numeric value",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s error(s) could not be corrected automatically.",
    },
    "es": {
        "Afficher les détails des anomalies": "Mostrar detalles de anomalías",
        "Ligne": "Fila", "Colonne": "Columna", "Valeur": "Valor", "Motif": "Motivo",
        "Email invalide": "Correo electrónico no válido",
        "Téléphone non standard": "Número de teléfono no estándar",
        "Date invalide": "Fecha no válida",
        "Valeur numérique invalide": "Valor numérico no válido",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "No se pudieron corregir automáticamente %(count)s errores.",
    },
    "de": {
        "Afficher les détails des anomalies": "Anomaliedetails anzeigen",
        "Ligne": "Zeile", "Colonne": "Spalte", "Valeur": "Wert", "Motif": "Grund",
        "Email invalide": "Ungültige E-Mail-Adresse",
        "Téléphone non standard": "Telefonnummer mit ungültigem Format",
        "Date invalide": "Ungültiges Datum",
        "Valeur numérique invalide": "Ungültiger Zahlenwert",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s Fehler konnten nicht automatisch korrigiert werden.",
    },
    "it": {
        "Afficher les détails des anomalies": "Mostra i dettagli delle anomalie",
        "Ligne": "Riga", "Colonne": "Colonna", "Valeur": "Valore", "Motif": "Motivo",
        "Email invalide": "Indirizzo email non valido",
        "Téléphone non standard": "Numero di telefono con formato non standard",
        "Date invalide": "Data non valida",
        "Valeur numérique invalide": "Valore numerico non valido",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "Impossibile correggere automaticamente %(count)s errori.",
    },
    "pt": {
        "Afficher les détails des anomalies": "Mostrar detalhes das anomalias",
        "Ligne": "Linha", "Colonne": "Coluna", "Valeur": "Valor", "Motif": "Motivo",
        "Email invalide": "Email inválido",
        "Téléphone non standard": "Número de telefone fora do padrão",
        "Date invalide": "Data inválida",
        "Valeur numérique invalide": "Valor numérico inválido",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "Não foi possível corrigir automaticamente %(count)s erro(s).",
    },
    "nl": {
        "Afficher les détails des anomalies": "Details van afwijkingen weergeven",
        "Ligne": "Rij", "Colonne": "Kolom", "Valeur": "Waarde", "Motif": "Reden",
        "Email invalide": "Ongeldig e-mailadres",
        "Téléphone non standard": "Telefoonnummer met afwijkend formaat",
        "Date invalide": "Ongeldige datum",
        "Valeur numérique invalide": "Ongeldige numerieke waarde",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s fout(en) konden niet automatisch worden gecorrigeerd.",
    },
    "ar": {
        "Afficher les détails des anomalies": "عرض تفاصيل الحالات غير الطبيعية",
        "Ligne": "الصف", "Colonne": "العمود", "Valeur": "القيمة", "Motif": "السبب",
        "Email invalide": "بريد إلكتروني غير صالح",
        "Téléphone non standard": "رقم هاتف بتنسيق غير قياسي",
        "Date invalide": "تاريخ غير صالح",
        "Valeur numérique invalide": "قيمة رقمية غير صالحة",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "تعذّر تصحيح %(count)s من الأخطاء تلقائيًا.",
    },
    "zh-hans": {
        "Afficher les détails des anomalies": "显示异常详情",
        "Ligne": "行", "Colonne": "列", "Valeur": "值", "Motif": "原因",
        "Email invalide": "无效电子邮件",
        "Téléphone non standard": "格式不规范的电话号码",
        "Date invalide": "无效日期",
        "Valeur numérique invalide": "无效数值",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s 个错误无法自动修正。",
    },
    "ru": {
        "Afficher les détails des anomalies": "Показать подробности аномалий",
        "Ligne": "Строка", "Colonne": "Столбец", "Valeur": "Значение", "Motif": "Причина",
        "Email invalide": "Недействительный адрес электронной почты",
        "Téléphone non standard": "Номер телефона в нестандартном формате",
        "Date invalide": "Недействительная дата",
        "Valeur numérique invalide": "Недопустимое числовое значение",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "Не удалось автоматически исправить ошибок: %(count)s.",
    },
    "ja": {
        "Afficher les détails des anomalies": "異常の詳細を表示",
        "Ligne": "行", "Colonne": "列", "Valeur": "値", "Motif": "理由",
        "Email invalide": "無効なメールアドレス",
        "Téléphone non standard": "標準形式ではない電話番号",
        "Date invalide": "無効な日付",
        "Valeur numérique invalide": "無効な数値",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s 件のエラーを自動修正できませんでした。",
    },
    "ko": {
        "Afficher les détails des anomalies": "이상 항목 세부정보 표시",
        "Ligne": "행", "Colonne": "열", "Valeur": "값", "Motif": "사유",
        "Email invalide": "잘못된 이메일",
        "Téléphone non standard": "표준 형식이 아닌 전화번호",
        "Date invalide": "잘못된 날짜",
        "Valeur numérique invalide": "잘못된 숫자 값",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "오류 %(count)s개를 자동으로 수정하지 못했습니다.",
    },
    "sv": {
        "Afficher les détails des anomalies": "Visa avvikelsedetaljer",
        "Ligne": "Rad", "Colonne": "Kolumn", "Valeur": "Värde", "Motif": "Orsak",
        "Email invalide": "Ogiltig e-postadress",
        "Téléphone non standard": "Telefonnummer med avvikande format",
        "Date invalide": "Ogiltigt datum",
        "Valeur numérique invalide": "Ogiltigt numeriskt värde",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s fel kunde inte korrigeras automatiskt.",
    },
    "da": {
        "Afficher les détails des anomalies": "Vis detaljer om afvigelser",
        "Ligne": "Række", "Colonne": "Kolonne", "Valeur": "Værdi", "Motif": "Årsag",
        "Email invalide": "Ugyldig e-mailadresse",
        "Téléphone non standard": "Telefonnummer i ikke-standardformat",
        "Date invalide": "Ugyldig dato",
        "Valeur numérique invalide": "Ugyldig numerisk værdi",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s fejl kunne ikke rettes automatisk.",
    },
    "fi": {
        "Afficher les détails des anomalies": "Näytä poikkeamien tiedot",
        "Ligne": "Rivi", "Colonne": "Sarake", "Valeur": "Arvo", "Motif": "Syy",
        "Email invalide": "Virheellinen sähköpostiosoite",
        "Téléphone non standard": "Puhelinnumero ei ole vakiomuodossa",
        "Date invalide": "Virheellinen päivämäärä",
        "Valeur numérique invalide": "Virheellinen lukuarvo",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s virhettä ei voitu korjata automaattisesti.",
    },
    "cs": {
        "Afficher les détails des anomalies": "Zobrazit podrobnosti anomálií",
        "Ligne": "Řádek", "Colonne": "Sloupec", "Valeur": "Hodnota", "Motif": "Důvod",
        "Email invalide": "Neplatný e-mail",
        "Téléphone non standard": "Telefonní číslo v nestandardním formátu",
        "Date invalide": "Neplatné datum",
        "Valeur numérique invalide": "Neplatná číselná hodnota",
        "%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.": "%(count)s chyb se nepodařilo automaticky opravit.",
    },
}

ISSUE_UI_TRANSLATIONS = {
    "en": EN_TRANSLATIONS,
    "es": ES_TRANSLATIONS,
    "de": DE_TRANSLATIONS,
    "it": IT_TRANSLATIONS,
    "pt": PT_TRANSLATIONS,
    "nl": NL_TRANSLATIONS,
    "ar": AR_TRANSLATIONS,
    "zh-hans": ZH_TRANSLATIONS,
    "ru": RU_TRANSLATIONS,
    "ja": JA_TRANSLATIONS,
    "ko": KO_TRANSLATIONS,
    "sv": SV_TRANSLATIONS,
    "da": DA_TRANSLATIONS,
    "fi": FI_TRANSLATIONS,
    "cs": CS_TRANSLATIONS,
}
for _code, _catalog in ISSUE_UI_TRANSLATIONS.items():
    _catalog.update(_ISSUE_OVERRIDES.get(_code, {}))
