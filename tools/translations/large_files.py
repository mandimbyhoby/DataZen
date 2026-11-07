"""Traductions des messages liés aux gros fichiers.

Les listes très longues (doublons potentiels, anomalies) ne sont affichées
qu'en partie sur la page d'un fichier : ce message indique le total et
renvoie vers le rapport téléchargeable, qui reste complet.
"""

_TRUNCATED = (
    "Seuls les %(shown)s premiers éléments sur %(total)s sont affichés ici ; "
    "le rapport téléchargeable contient la liste complète."
)

_TRANSLATIONS = {
    "en": "Only the first %(shown)s of %(total)s items are shown here; the downloadable report contains the full list.",
    "es": "Aquí solo se muestran los primeros %(shown)s de %(total)s elementos; el informe descargable contiene la lista completa.",
    "de": "Hier werden nur die ersten %(shown)s von %(total)s Einträgen angezeigt; der herunterladbare Bericht enthält die vollständige Liste.",
    "it": "Qui sono mostrati solo i primi %(shown)s elementi su %(total)s; il report scaricabile contiene l'elenco completo.",
    "pt": "Aqui são mostrados apenas os primeiros %(shown)s de %(total)s elementos; o relatório transferível contém a lista completa.",
    "nl": "Hier worden alleen de eerste %(shown)s van %(total)s items getoond; het downloadbare rapport bevat de volledige lijst.",
    "ar": "تُعرض هنا أول %(shown)s عناصر فقط من أصل %(total)s؛ يحتوي التقرير القابل للتنزيل على القائمة الكاملة.",
    "zh-hans": "此处仅显示 %(total)s 项中的前 %(shown)s 项；可下载的报告包含完整列表。",
    "ru": "Здесь показаны только первые %(shown)s из %(total)s элементов; полный список содержится в загружаемом отчёте.",
    "ja": "ここには %(total)s 件中最初の %(shown)s 件のみ表示しています。完全な一覧はダウンロード可能なレポートに含まれています。",
    "ko": "여기에는 %(total)s개 중 처음 %(shown)s개만 표시됩니다. 전체 목록은 다운로드 가능한 보고서에 포함되어 있습니다.",
    "tr": "Burada %(total)s öğeden yalnızca ilk %(shown)s tanesi gösteriliyor; indirilebilir rapor tam listeyi içerir.",
    "hi": "यहाँ %(total)s में से केवल पहले %(shown)s आइटम दिखाए गए हैं; डाउनलोड की जा सकने वाली रिपोर्ट में पूरी सूची है।",
    "pl": "Wyświetlono tu tylko pierwsze %(shown)s z %(total)s elementów; pełna lista znajduje się w raporcie do pobrania.",
    "sv": "Här visas bara de första %(shown)s av %(total)s posterna; den nedladdningsbara rapporten innehåller hela listan.",
    "da": "Her vises kun de første %(shown)s af %(total)s elementer; den rapport, der kan downloades, indeholder hele listen.",
    "fi": "Tässä näytetään vain ensimmäiset %(shown)s / %(total)s kohdetta; ladattava raportti sisältää koko luettelon.",
    "cs": "Zde je zobrazeno pouze prvních %(shown)s z %(total)s položek; úplný seznam obsahuje stažitelná zpráva.",
    "ro": "Aici sunt afișate doar primele %(shown)s din %(total)s elemente; raportul descărcabil conține lista completă.",
    "vi": "Chỉ hiển thị %(shown)s mục đầu tiên trên tổng số %(total)s tại đây; báo cáo có thể tải xuống chứa danh sách đầy đủ.",
    "th": "แสดงเฉพาะ %(shown)s รายการแรกจากทั้งหมด %(total)s รายการที่นี่ รายงานที่ดาวน์โหลดได้มีรายการครบถ้วน",
    "id": "Hanya %(shown)s item pertama dari %(total)s yang ditampilkan di sini; laporan yang dapat diunduh berisi daftar lengkap.",
}

LARGE_FILE_TRANSLATIONS = {
    code: {_TRUNCATED: text} for code, text in _TRANSLATIONS.items()
}
