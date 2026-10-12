"""Messages remontés par les services d'arrière-plan (API, nettoyage).

Ces libellés sont produits par ``core/services/api.py`` lors de la validation
d'une URL de webhook et par ``core/services/async_runner.py`` lorsqu'un
nettoyage échoue. Ils sont ensuite affichés tels quels dans le formulaire, dans
l'administration ou sur la page de détail : ils doivent donc être traduits
comme le reste de l'interface.

Le module est tenu à part des catalogues ``<code>.py`` parce que ces chaînes
appartiennent aux services internes plutôt qu'aux écrans.
"""

SERVICE_MESSAGE_TRANSLATIONS = {
    "en": {
        "Une URL de destination est requise.": "A destination URL is required.",
        "URL illisible.": "Unreadable URL.",
        "Seuls les schémas http et https sont autorisés.": (
            "Only http and https schemes are allowed."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Credentials embedded in the URL are refused."
        ),
        "Le nom d'hôte est absent de l'URL.": "The URL has no host name.",
        "Le port est invalide.": "The port is invalid.",
        "Les adresses locales sont refusées.": "Local addresses are refused.",
        "Les adresses internes sont refusées.": "Internal addresses are refused.",
        "Le nom d'hôte du webhook est introuvable.": (
            "The webhook host name cannot be resolved."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "The webhook host name points to an internal address."
        ),
        "référence": "reference",
        "Échec du nettoyage": "Cleaning failed",
    },
    "es": {
        "Une URL de destination est requise.": "Se requiere una URL de destino.",
        "URL illisible.": "URL ilegible.",
        "Seuls les schémas http et https sont autorisés.": (
            "Solo se permiten los esquemas http y https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Se rechazan las credenciales incluidas en la URL."
        ),
        "Le nom d'hôte est absent de l'URL.": "Falta el nombre de host en la URL.",
        "Le port est invalide.": "El puerto no es válido.",
        "Les adresses locales sont refusées.": "Se rechazan las direcciones locales.",
        "Les adresses internes sont refusées.": "Se rechazan las direcciones internas.",
        "Le nom d'hôte du webhook est introuvable.": (
            "No se encuentra el nombre de host del webhook."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "El nombre de host del webhook apunta a una dirección interna."
        ),
        "référence": "referencia",
        "Échec du nettoyage": "Error de limpieza",
    },
    "de": {
        "Une URL de destination est requise.": "Eine Ziel-URL ist erforderlich.",
        "URL illisible.": "URL nicht lesbar.",
        "Seuls les schémas http et https sont autorisés.": (
            "Nur die Schemata http und https sind erlaubt."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "In der URL eingebettete Anmeldedaten werden abgelehnt."
        ),
        "Le nom d'hôte est absent de l'URL.": "Der Hostname fehlt in der URL.",
        "Le port est invalide.": "Der Port ist ungültig.",
        "Les adresses locales sont refusées.": "Lokale Adressen werden abgelehnt.",
        "Les adresses internes sont refusées.": "Interne Adressen werden abgelehnt.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Der Hostname des Webhooks wurde nicht gefunden."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Der Hostname des Webhooks verweist auf eine interne Adresse."
        ),
        "référence": "Referenz",
        "Échec du nettoyage": "Bereinigung fehlgeschlagen",
    },
    "it": {
        "Une URL de destination est requise.": "È richiesto un URL di destinazione.",
        "URL illisible.": "URL illeggibile.",
        "Seuls les schémas http et https sont autorisés.": (
            "Sono ammessi solo gli schemi http e https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Le credenziali incorporate nell'URL sono rifiutate."
        ),
        "Le nom d'hôte est absent de l'URL.": "Manca il nome host nell'URL.",
        "Le port est invalide.": "La porta non è valida.",
        "Les adresses locales sont refusées.": "Gli indirizzi locali sono rifiutati.",
        "Les adresses internes sont refusées.": "Gli indirizzi interni sono rifiutati.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Il nome host del webhook è introvabile."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Il nome host del webhook punta a un indirizzo interno."
        ),
        "référence": "riferimento",
        "Échec du nettoyage": "Pulizia non riuscita",
    },
    "pt": {
        "Une URL de destination est requise.": "É necessária uma URL de destino.",
        "URL illisible.": "URL ilegível.",
        "Seuls les schémas http et https sont autorisés.": (
            "Apenas os esquemas http e https são permitidos."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "As credenciais incorporadas na URL são recusadas."
        ),
        "Le nom d'hôte est absent de l'URL.": "Falta o nome do host na URL.",
        "Le port est invalide.": "A porta é inválida.",
        "Les adresses locales sont refusées.": "Os endereços locais são recusados.",
        "Les adresses internes sont refusées.": "Os endereços internos são recusados.",
        "Le nom d'hôte du webhook est introuvable.": (
            "O nome do host do webhook não foi encontrado."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "O nome do host do webhook aponta para um endereço interno."
        ),
        "référence": "referência",
        "Échec du nettoyage": "Falha na limpeza",
    },
    "nl": {
        "Une URL de destination est requise.": "Een doel-URL is verplicht.",
        "URL illisible.": "URL onleesbaar.",
        "Seuls les schémas http et https sont autorisés.": (
            "Alleen de schema's http en https zijn toegestaan."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Inloggegevens in de URL worden geweigerd."
        ),
        "Le nom d'hôte est absent de l'URL.": "De hostnaam ontbreekt in de URL.",
        "Le port est invalide.": "De poort is ongeldig.",
        "Les adresses locales sont refusées.": "Lokale adressen worden geweigerd.",
        "Les adresses internes sont refusées.": "Interne adressen worden geweigerd.",
        "Le nom d'hôte du webhook est introuvable.": (
            "De hostnaam van de webhook is niet gevonden."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "De hostnaam van de webhook verwijst naar een intern adres."
        ),
        "référence": "referentie",
        "Échec du nettoyage": "Opschonen mislukt",
    },
    "ar": {
        "Une URL de destination est requise.": "مطلوب عنوان URL للوجهة.",
        "URL illisible.": "تعذّر قراءة عنوان URL.",
        "Seuls les schémas http et https sont autorisés.": (
            "يُسمح بمخططي http و https فقط."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "بيانات الاعتماد المضمّنة في عنوان URL مرفوضة."
        ),
        "Le nom d'hôte est absent de l'URL.": "اسم المضيف مفقود في عنوان URL.",
        "Le port est invalide.": "المنفذ غير صالح.",
        "Les adresses locales sont refusées.": "العناوين المحلية مرفوضة.",
        "Les adresses internes sont refusées.": "العناوين الداخلية مرفوضة.",
        "Le nom d'hôte du webhook est introuvable.": (
            "تعذّر العثور على اسم مضيف الـ webhook."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "اسم مضيف الـ webhook يشير إلى عنوان داخلي."
        ),
        "référence": "المرجع",
        "Échec du nettoyage": "فشل التنظيف",
    },
    "zh-hans": {
        "Une URL de destination est requise.": "需要目标 URL。",
        "URL illisible.": "URL 无法读取。",
        "Seuls les schémas http et https sont autorisés.": "仅允许 http 和 https 协议。",
        "Les identifiants intégrés à l'URL sont refusés.": "拒绝 URL 中嵌入的凭据。",
        "Le nom d'hôte est absent de l'URL.": "URL 中缺少主机名。",
        "Le port est invalide.": "端口无效。",
        "Les adresses locales sont refusées.": "拒绝本地地址。",
        "Les adresses internes sont refusées.": "拒绝内部地址。",
        "Le nom d'hôte du webhook est introuvable.": "找不到 Webhook 的主机名。",
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Webhook 的主机名指向内部地址。"
        ),
        "référence": "引用",
        "Échec du nettoyage": "清理失败",
    },
    "ru": {
        "Une URL de destination est requise.": "Требуется URL назначения.",
        "URL illisible.": "Нечитаемый URL.",
        "Seuls les schémas http et https sont autorisés.": (
            "Разрешены только схемы http и https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Учётные данные, встроенные в URL, отклоняются."
        ),
        "Le nom d'hôte est absent de l'URL.": "В URL отсутствует имя хоста.",
        "Le port est invalide.": "Недопустимый порт.",
        "Les adresses locales sont refusées.": "Локальные адреса отклоняются.",
        "Les adresses internes sont refusées.": "Внутренние адреса отклоняются.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Имя хоста вебхука не найдено."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Имя хоста вебхука указывает на внутренний адрес."
        ),
        "référence": "ссылка",
        "Échec du nettoyage": "Сбой очистки",
    },
    "ja": {
        "Une URL de destination est requise.": "宛先 URL が必要です。",
        "URL illisible.": "URL を読み取れません。",
        "Seuls les schémas http et https sont autorisés.": (
            "使用できるのは http と https スキームのみです。"
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "URL に埋め込まれた認証情報は拒否されます。"
        ),
        "Le nom d'hôte est absent de l'URL.": "URL にホスト名がありません。",
        "Le port est invalide.": "ポートが無効です。",
        "Les adresses locales sont refusées.": "ローカルアドレスは拒否されます。",
        "Les adresses internes sont refusées.": "内部アドレスは拒否されます。",
        "Le nom d'hôte du webhook est introuvable.": (
            "Webhook のホスト名が見つかりません。"
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Webhook のホスト名が内部アドレスを指しています。"
        ),
        "référence": "参照",
        "Échec du nettoyage": "クリーニングに失敗しました",
    },
    "ko": {
        "Une URL de destination est requise.": "대상 URL이 필요합니다.",
        "URL illisible.": "URL을 읽을 수 없습니다.",
        "Seuls les schémas http et https sont autorisés.": (
            "http 및 https 스킴만 허용됩니다."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "URL에 포함된 자격 증명은 거부됩니다."
        ),
        "Le nom d'hôte est absent de l'URL.": "URL에 호스트 이름이 없습니다.",
        "Le port est invalide.": "포트가 유효하지 않습니다.",
        "Les adresses locales sont refusées.": "로컬 주소는 거부됩니다.",
        "Les adresses internes sont refusées.": "내부 주소는 거부됩니다.",
        "Le nom d'hôte du webhook est introuvable.": (
            "웹훅의 호스트 이름을 찾을 수 없습니다."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "웹훅의 호스트 이름이 내부 주소를 가리킵니다."
        ),
        "référence": "참조",
        "Échec du nettoyage": "정리 실패",
    },
    "tr": {
        "Une URL de destination est requise.": "Bir hedef URL gerekli.",
        "URL illisible.": "URL okunamıyor.",
        "Seuls les schémas http et https sont autorisés.": (
            "Yalnızca http ve https şemalarına izin verilir."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "URL'ye gömülü kimlik bilgileri reddedilir."
        ),
        "Le nom d'hôte est absent de l'URL.": "URL'de ana makine adı yok.",
        "Le port est invalide.": "Bağlantı noktası geçersiz.",
        "Les adresses locales sont refusées.": "Yerel adresler reddedilir.",
        "Les adresses internes sont refusées.": "İç adresler reddedilir.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Webhook ana makine adı bulunamadı."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Webhook ana makine adı bir iç adrese işaret ediyor."
        ),
        "référence": "referans",
        "Échec du nettoyage": "Temizleme başarısız",
    },
    "hi": {
        "Une URL de destination est requise.": "गंतव्य URL आवश्यक है।",
        "URL illisible.": "URL पढ़ा नहीं जा सका।",
        "Seuls les schémas http et https sont autorisés.": (
            "केवल http और https स्कीम की अनुमति है।"
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "URL में एम्बेड किए गए क्रेडेंशियल अस्वीकार किए जाते हैं।"
        ),
        "Le nom d'hôte est absent de l'URL.": "URL में होस्ट नाम मौजूद नहीं है।",
        "Le port est invalide.": "पोर्ट अमान्य है।",
        "Les adresses locales sont refusées.": "स्थानीय पते अस्वीकार किए जाते हैं।",
        "Les adresses internes sont refusées.": "आंतरिक पते अस्वीकार किए जाते हैं।",
        "Le nom d'hôte du webhook est introuvable.": "वेबहुक का होस्ट नाम नहीं मिला।",
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "वेबहुक का होस्ट नाम किसी आंतरिक पते की ओर इशारा करता है।"
        ),
        "référence": "संदर्भ",
        "Échec du nettoyage": "सफ़ाई विफल",
    },
    "pl": {
        "Une URL de destination est requise.": "Docelowy adres URL jest wymagany.",
        "URL illisible.": "Nieczytelny adres URL.",
        "Seuls les schémas http et https sont autorisés.": (
            "Dozwolone są tylko schematy http i https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Dane uwierzytelniające osadzone w adresie URL są odrzucane."
        ),
        "Le nom d'hôte est absent de l'URL.": "W adresie URL brakuje nazwy hosta.",
        "Le port est invalide.": "Nieprawidłowy port.",
        "Les adresses locales sont refusées.": "Adresy lokalne są odrzucane.",
        "Les adresses internes sont refusées.": "Adresy wewnętrzne są odrzucane.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Nie znaleziono nazwy hosta webhooka."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Nazwa hosta webhooka wskazuje na adres wewnętrzny."
        ),
        "référence": "odniesienie",
        "Échec du nettoyage": "Czyszczenie nie powiodło się",
    },
    "sv": {
        "Une URL de destination est requise.": "En mål-URL krävs.",
        "URL illisible.": "URL:en går inte att läsa.",
        "Seuls les schémas http et https sont autorisés.": (
            "Endast schemana http och https tillåts."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Inloggningsuppgifter inbäddade i URL:en avvisas."
        ),
        "Le nom d'hôte est absent de l'URL.": "Värdnamnet saknas i URL:en.",
        "Le port est invalide.": "Porten är ogiltig.",
        "Les adresses locales sont refusées.": "Lokala adresser avvisas.",
        "Les adresses internes sont refusées.": "Interna adresser avvisas.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Webhookens värdnamn hittades inte."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Webhookens värdnamn pekar på en intern adress."
        ),
        "référence": "referens",
        "Échec du nettoyage": "Rensning misslyckades",
    },
    "da": {
        "Une URL de destination est requise.": "En destinations-URL er påkrævet.",
        "URL illisible.": "URL kan ikke læses.",
        "Seuls les schémas http et https sont autorisés.": (
            "Kun skemaerne http og https er tilladt."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Legitimationsoplysninger indlejret i URL'en afvises."
        ),
        "Le nom d'hôte est absent de l'URL.": "Værtsnavnet mangler i URL'en.",
        "Le port est invalide.": "Porten er ugyldig.",
        "Les adresses locales sont refusées.": "Lokale adresser afvises.",
        "Les adresses internes sont refusées.": "Interne adresser afvises.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Webhookens værtsnavn blev ikke fundet."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Webhookens værtsnavn peger på en intern adresse."
        ),
        "référence": "reference",
        "Échec du nettoyage": "Oprydning mislykkedes",
    },
    "fi": {
        "Une URL de destination est requise.": "Kohde-URL vaaditaan.",
        "URL illisible.": "URL ei ole luettavissa.",
        "Seuls les schémas http et https sont autorisés.": (
            "Vain http- ja https-skeemat ovat sallittuja."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "URL-osoitteeseen upotetut tunnistetiedot hylätään."
        ),
        "Le nom d'hôte est absent de l'URL.": "URL-osoitteesta puuttuu isäntänimi.",
        "Le port est invalide.": "Portti on virheellinen.",
        "Les adresses locales sont refusées.": "Paikalliset osoitteet hylätään.",
        "Les adresses internes sont refusées.": "Sisäiset osoitteet hylätään.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Webhookin isäntänimeä ei löytynyt."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Webhookin isäntänimi osoittaa sisäiseen osoitteeseen."
        ),
        "référence": "viite",
        "Échec du nettoyage": "Siivous epäonnistui",
    },
    "cs": {
        "Une URL de destination est requise.": "Je vyžadována cílová URL.",
        "URL illisible.": "URL nelze přečíst.",
        "Seuls les schémas http et https sont autorisés.": (
            "Povolena jsou pouze schémata http a https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Přihlašovací údaje vložené do URL jsou odmítnuty."
        ),
        "Le nom d'hôte est absent de l'URL.": "V URL chybí název hostitele.",
        "Le port est invalide.": "Neplatný port.",
        "Les adresses locales sont refusées.": "Místní adresy jsou odmítnuty.",
        "Les adresses internes sont refusées.": "Interní adresy jsou odmítnuty.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Název hostitele webhooku nebyl nalezen."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Název hostitele webhooku ukazuje na interní adresu."
        ),
        "référence": "reference",
        "Échec du nettoyage": "Čištění selhalo",
    },
    "ro": {
        "Une URL de destination est requise.": (
            "Este necesară o adresă URL de destinație."
        ),
        "URL illisible.": "Adresă URL ilizibilă.",
        "Seuls les schémas http et https sont autorisés.": (
            "Sunt permise doar schemele http și https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Datele de autentificare incluse în adresă sunt refuzate."
        ),
        "Le nom d'hôte est absent de l'URL.": "Numele de gazdă lipsește din adresă.",
        "Le port est invalide.": "Portul este invalid.",
        "Les adresses locales sont refusées.": "Adresele locale sunt refuzate.",
        "Les adresses internes sont refusées.": "Adresele interne sunt refuzate.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Numele de gazdă al webhook-ului nu a fost găsit."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Numele de gazdă al webhook-ului indică o adresă internă."
        ),
        "référence": "referință",
        "Échec du nettoyage": "Curățarea a eșuat",
    },
    "vi": {
        "Une URL de destination est requise.": "Cần có URL đích.",
        "URL illisible.": "Không đọc được URL.",
        "Seuls les schémas http et https sont autorisés.": (
            "Chỉ cho phép lược đồ http và https."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Thông tin đăng nhập nhúng trong URL bị từ chối."
        ),
        "Le nom d'hôte est absent de l'URL.": "Thiếu tên máy chủ trong URL.",
        "Le port est invalide.": "Cổng không hợp lệ.",
        "Les adresses locales sont refusées.": "Địa chỉ cục bộ bị từ chối.",
        "Les adresses internes sont refusées.": "Địa chỉ nội bộ bị từ chối.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Không tìm thấy tên máy chủ của webhook."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Tên máy chủ của webhook trỏ đến một địa chỉ nội bộ."
        ),
        "référence": "tham chiếu",
        "Échec du nettoyage": "Làm sạch thất bại",
    },
    "th": {
        "Une URL de destination est requise.": "ต้องระบุ URL ปลายทาง",
        "URL illisible.": "อ่าน URL ไม่ได้",
        "Seuls les schémas http et https sont autorisés.": (
            "อนุญาตเฉพาะสคีมา http และ https เท่านั้น"
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "ข้อมูลรับรองที่ฝังใน URL จะถูกปฏิเสธ"
        ),
        "Le nom d'hôte est absent de l'URL.": "ไม่มีชื่อโฮสต์ใน URL",
        "Le port est invalide.": "พอร์ตไม่ถูกต้อง",
        "Les adresses locales sont refusées.": "ที่อยู่ภายในเครื่องจะถูกปฏิเสธ",
        "Les adresses internes sont refusées.": "ที่อยู่ภายในจะถูกปฏิเสธ",
        "Le nom d'hôte du webhook est introuvable.": "ไม่พบชื่อโฮสต์ของเว็บฮุก",
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "ชื่อโฮสต์ของเว็บฮุกชี้ไปที่ที่อยู่ภายใน"
        ),
        "référence": "เอกสารอ้างอิง",
        "Échec du nettoyage": "การล้างข้อมูลล้มเหลว",
    },
    "id": {
        "Une URL de destination est requise.": "URL tujuan wajib diisi.",
        "URL illisible.": "URL tidak terbaca.",
        "Seuls les schémas http et https sont autorisés.": (
            "Hanya skema http dan https yang diizinkan."
        ),
        "Les identifiants intégrés à l'URL sont refusés.": (
            "Kredensial yang disematkan di URL ditolak."
        ),
        "Le nom d'hôte est absent de l'URL.": "Nama host tidak ada di URL.",
        "Le port est invalide.": "Port tidak valid.",
        "Les adresses locales sont refusées.": "Alamat lokal ditolak.",
        "Les adresses internes sont refusées.": "Alamat internal ditolak.",
        "Le nom d'hôte du webhook est introuvable.": (
            "Nama host webhook tidak ditemukan."
        ),
        "Le nom d'hôte du webhook pointe vers une adresse interne.": (
            "Nama host webhook mengarah ke alamat internal."
        ),
        "référence": "referensi",
        "Échec du nettoyage": "Pembersihan gagal",
    },
}

__all__ = ["SERVICE_MESSAGE_TRANSLATIONS"]