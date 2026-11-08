"""Traductions des îlots React de l'interface (zone d'envoi interactive).

Les libellés sont rendus par Django dans des attributs ``data-dz-msg-*`` du
formulaire d'envoi, puis lus par ``frontend/src/ui/main.jsx`` : le bundle
JavaScript ne contient donc aucun texte à traduire.
"""

_KEYS = (
    "Glissez-déposez votre fichier ici",
    "ou cliquez pour parcourir vos fichiers",
    "Relâchez pour ajouter le fichier",
    "Envoi en cours…",
    "Fichier envoyé, ouverture de l’analyse…",
    "Retirer le fichier",
    "L’envoi a échoué. Vérifiez votre connexion, puis réessayez.",
)

_VALUES = {
    "en": ("Drag and drop your file here", "or click to browse your files", "Release to add the file", "Uploading…", "File uploaded, opening the analysis…", "Remove the file", "The upload failed. Check your connection, then try again."),
    "es": ("Arrastre y suelte su archivo aquí", "o haga clic para explorar sus archivos", "Suelte para añadir el archivo", "Enviando…", "Archivo enviado, abriendo el análisis…", "Quitar el archivo", "El envío ha fallado. Compruebe su conexión y vuelva a intentarlo."),
    "de": ("Datei hierher ziehen und ablegen", "oder klicken, um Ihre Dateien zu durchsuchen", "Loslassen, um die Datei hinzuzufügen", "Wird hochgeladen…", "Datei hochgeladen, Analyse wird geöffnet…", "Datei entfernen", "Das Hochladen ist fehlgeschlagen. Prüfen Sie Ihre Verbindung und versuchen Sie es erneut."),
    "it": ("Trascina qui il tuo file", "oppure fai clic per sfogliare i tuoi file", "Rilascia per aggiungere il file", "Invio in corso…", "File inviato, apertura dell’analisi…", "Rimuovi il file", "Invio non riuscito. Controlla la connessione e riprova."),
    "pt": ("Arraste e largue o seu ficheiro aqui", "ou clique para procurar os seus ficheiros", "Largue para adicionar o ficheiro", "A enviar…", "Ficheiro enviado, a abrir a análise…", "Remover o ficheiro", "O envio falhou. Verifique a sua ligação e tente novamente."),
    "nl": ("Sleep je bestand hierheen", "of klik om je bestanden te doorzoeken", "Loslaten om het bestand toe te voegen", "Bezig met uploaden…", "Bestand geüpload, analyse wordt geopend…", "Bestand verwijderen", "Het uploaden is mislukt. Controleer je verbinding en probeer het opnieuw."),
    "ar": ("اسحب ملفك وأفلته هنا", "أو انقر لتصفح ملفاتك", "أفلت لإضافة الملف", "جارٍ الإرسال…", "تم إرسال الملف، جارٍ فتح التحليل…", "إزالة الملف", "فشل الإرسال. تحقّق من اتصالك ثم أعد المحاولة."),
    "zh-hans": ("将文件拖放到此处", "或点击浏览文件", "松开以添加文件", "正在上传…", "文件已上传，正在打开分析…", "移除文件", "上传失败。请检查网络连接后重试。"),
    "ru": ("Перетащите файл сюда", "или нажмите, чтобы выбрать файл", "Отпустите, чтобы добавить файл", "Отправка…", "Файл отправлен, открываем анализ…", "Убрать файл", "Не удалось отправить файл. Проверьте подключение и повторите попытку."),
    "ja": ("ここにファイルをドラッグ＆ドロップ", "またはクリックしてファイルを選択", "離すとファイルを追加します", "アップロード中…", "アップロード完了。分析を開いています…", "ファイルを削除", "アップロードに失敗しました。接続を確認して、もう一度お試しください。"),
    "ko": ("여기에 파일을 끌어다 놓으세요", "또는 클릭하여 파일을 찾아보세요", "놓으면 파일이 추가됩니다", "업로드 중…", "파일 업로드 완료, 분석을 여는 중…", "파일 제거", "업로드에 실패했습니다. 연결을 확인한 후 다시 시도하세요."),
    "tr": ("Dosyanızı buraya sürükleyip bırakın", "veya dosyalarınıza göz atmak için tıklayın", "Dosyayı eklemek için bırakın", "Gönderiliyor…", "Dosya gönderildi, analiz açılıyor…", "Dosyayı kaldır", "Gönderim başarısız oldu. Bağlantınızı kontrol edip yeniden deneyin."),
    "hi": ("अपनी फ़ाइल यहाँ खींचकर छोड़ें", "या अपनी फ़ाइलें देखने के लिए क्लिक करें", "फ़ाइल जोड़ने के लिए छोड़ें", "भेजा जा रहा है…", "फ़ाइल भेज दी गई, विश्लेषण खुल रहा है…", "फ़ाइल हटाएँ", "भेजना विफल रहा। अपना कनेक्शन जाँचें, फिर दोबारा प्रयास करें।"),
    "pl": ("Przeciągnij i upuść plik tutaj", "lub kliknij, aby przeglądać pliki", "Upuść, aby dodać plik", "Wysyłanie…", "Plik wysłany, otwieranie analizy…", "Usuń plik", "Wysyłanie nie powiodło się. Sprawdź połączenie i spróbuj ponownie."),
    "sv": ("Dra och släpp din fil här", "eller klicka för att bläddra bland dina filer", "Släpp för att lägga till filen", "Laddar upp…", "Filen har laddats upp, analysen öppnas…", "Ta bort filen", "Uppladdningen misslyckades. Kontrollera anslutningen och försök igen."),
    "da": ("Træk og slip din fil her", "eller klik for at gennemse dine filer", "Slip for at tilføje filen", "Sender…", "Filen er sendt, analysen åbnes…", "Fjern filen", "Afsendelsen mislykkedes. Tjek din forbindelse, og prøv igen."),
    "fi": ("Vedä ja pudota tiedosto tähän", "tai napsauta selataksesi tiedostojasi", "Vapauta lisätäksesi tiedoston", "Lähetetään…", "Tiedosto lähetetty, analyysi avataan…", "Poista tiedosto", "Lähetys epäonnistui. Tarkista yhteys ja yritä uudelleen."),
    "cs": ("Přetáhněte soubor sem", "nebo klikněte a vyberte soubor", "Pusťte pro přidání souboru", "Odesílání…", "Soubor odeslán, otevírá se analýza…", "Odebrat soubor", "Odeslání se nezdařilo. Zkontrolujte připojení a zkuste to znovu."),
    "ro": ("Trageți și plasați fișierul aici", "sau faceți clic pentru a răsfoi fișierele", "Eliberați pentru a adăuga fișierul", "Se trimite…", "Fișier trimis, se deschide analiza…", "Eliminați fișierul", "Trimiterea a eșuat. Verificați conexiunea, apoi încercați din nou."),
    "vi": ("Kéo và thả tệp của bạn vào đây", "hoặc nhấp để duyệt tệp", "Thả ra để thêm tệp", "Đang tải lên…", "Đã tải tệp lên, đang mở phân tích…", "Gỡ tệp", "Tải lên thất bại. Hãy kiểm tra kết nối rồi thử lại."),
    "th": ("ลากและวางไฟล์ของคุณที่นี่", "หรือคลิกเพื่อเลือกไฟล์", "ปล่อยเพื่อเพิ่มไฟล์", "กำลังส่ง…", "ส่งไฟล์แล้ว กำลังเปิดการวิเคราะห์…", "นำไฟล์ออก", "การส่งล้มเหลว โปรดตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"),
    "id": ("Seret dan lepas file Anda di sini", "atau klik untuk menelusuri file Anda", "Lepaskan untuk menambahkan file", "Mengunggah…", "File terunggah, membuka analisis…", "Hapus file", "Pengunggahan gagal. Periksa koneksi Anda, lalu coba lagi."),
}

for _code, _texts in _VALUES.items():
    if len(_texts) != len(_KEYS):
        raise ValueError(f"ui_islands : {_code} a {len(_texts)} libellés au lieu de {len(_KEYS)}")

UI_ISLAND_TRANSLATIONS = {
    code: dict(zip(_KEYS, texts)) for code, texts in _VALUES.items()
}
