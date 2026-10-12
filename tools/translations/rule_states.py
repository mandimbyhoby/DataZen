"""États d'activation d'une règle de nettoyage.

Ces deux chaînes remplacent l'ancien littéral français inséré dans
``views.rule_toggle`` : elles doivent donc être traduisibles
(``_("activée")`` / ``_("désactivée")``).
"""

_ENABLED = "activée"
_DISABLED = "désactivée"

_TRANSLATIONS = {
    "en": ("enabled", "disabled"),
    "es": ("activada", "desactivada"),
    "de": ("aktiviert", "deaktiviert"),
    "it": ("attivata", "disattivata"),
    "pt": ("ativada", "desativada"),
    "nl": ("ingeschakeld", "uitgeschakeld"),
    "ar": ("نشطة", "غير نشطة"),
    "zh-hans": ("已启用", "已停用"),
    "ru": ("включено", "отключено"),
    "ja": ("有効化しました", "無効化しました"),
    "ko": ("활성화되었습니다", "비활성화되었습니다"),
    "tr": ("etkinleştirildi", "devre dışı bırakıldı"),
    "hi": ("सक्रिय", "निष्क्रिय"),
    "pl": ("włączona", "wyłączona"),
    "sv": ("aktiverad", "inaktiverad"),
    "da": ("aktiveret", "deaktiveret"),
    "fi": ("otettu käyttöön", "poistettu käytöstä"),
    "cs": ("aktivováno", "deaktivováno"),
    "ro": ("activată", "dezactivată"),
    "vi": ("đã bật", "đã tắt"),
    "th": ("เปิดใช้งานแล้ว", "ปิดใช้งานแล้ว"),
    "id": ("diaktifkan", "dinonaktifkan"),
}

RULE_STATE_TRANSLATIONS = {
    code: {_ENABLED: forms[0], _DISABLED: forms[1]}
    for code, forms in _TRANSLATIONS.items()
}
