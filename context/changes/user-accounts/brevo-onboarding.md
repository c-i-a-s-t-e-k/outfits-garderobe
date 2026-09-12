# Brevo — onboarding dla Fazy 4 (produkcyjna wysyłka maili)

> Status: **research zamknięty, do wykonania przed Fazą 4**. Data: 2026-09-12.
> Uzupełnia `plan.md` → *Phase 4 → 1. Settings — production email* i *6. Railway environment*,
> które zakładały, że konto Brevo już istnieje. Ten dokument je zakłada od zera.
> Fakty pochodzą z dokumentacji Brevo, Railway i django-anymail (linki w *Źródłach*);
> ścieżki w panelu Brevo są aktualne na dzień researchu i mogą się przesunąć.

## 0. Dwa ustalenia, które unieważniają część planu

**A. Railway blokuje wychodzące SMTP na planach Free/Trial/Hobby.** Dokumentacja Railway:
*„SMTP is only available on the Pro plan and above; Free, Trial, and Hobby plans must use
transactional email services with HTTPS APIs."* Projekt jest na Hobby
(`context/foundation/infrastructure.md:18`). Zapis w `plan.md:344` — stockowy backend SMTP
Django z `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`
— **nie zadziała**: `smtp-relay.brevo.com:587` nie połączy się z kontenera. Brevo zostaje,
ale przez **REST API po HTTPS (port 443)**, z tym samym limitem 300 maili/dzień na planie Free.

**B. Brevo wysyła bez własnej domeny, ale przepisuje adres nadawcy.** Pojedynczy nadawca
(np. `@gmail.com`) daje się zweryfikować linkiem z maila, natomiast Brevo:
*„replaces any free email address used for sending, regardless of the recipients"* —
domena w polu From zostaje podmieniona na `@<id>.brevosend.com`. Mail dochodzi; odbiorca
widzi obcy adres. Plan Free dokleja też sticker „Sent with Brevo" do każdego maila,
transakcyjnych włącznie (add-on usuwający: ~$9/mies.). Przy własnej, uwierzytelnionej
domenie obu efektów nie ma (poza stickerem).

Konsekwencja: **przed krokiem 1 trzeba podjąć decyzję o domenie** (sekcja 2).

## 1. Fakty, na których opiera się ten dokument

| Fakt | Źródło |
|---|---|
| Plan Free: 300 maili/dzień, API + SMTP + webhooki, bez karty | Brevo — Free SMTP server; FAQ Free plan limits |
| SMTP zablokowany na Railway Hobby; zalecane HTTPS API | Railway — Outbound Networking |
| Endpoint: `POST https://api.brevo.com/v3/smtp/email`, nagłówek `api-key`, odpowiedź 201 z `messageId` | Brevo — Send a transactional email |
| Każdy nadawca musi być zweryfikowany (link z maila) przed użyciem | Brevo — Create a new sender |
| Domen darmowych skrzynek (gmail.com, yahoo.com…) nie da się uwierzytelnić; From jest podmieniany na `brevosend.com` | Brevo — Why replace your free email address; Comply with Gmail/Yahoo requirements |
| Sticker „Sent with Brevo" na planie Free, także transakcyjne | Brevo — FAQ Free plan limits |
| `django-anymail` ma backend Brevo (status *Full*), klucz **v3**, `ANYMAIL['BREVO_API_KEY']` | anymail — Brevo |
| DMARC: `gmail.com`/`outlook.com` `p=none`; **`duck.com` `p=quarantine`**; `icloud.com` `p=quarantine`; `yahoo.com` `p=reject` | `dig txt _dmarc.<domena>` z 2026-09-12 |

Ostatni wiersz przesądza wybór adresu nadawcy bez domeny: From z `duck.com` wysłany przez
Brevo (SPF/DKIM nieuzgodnione) podpada pod `p=quarantine` odbiorcy → spam. Z `gmail.com`
(`p=none`) — nie.

## 2. Decyzja: domena czy nie

| | Bez domeny | Własna domena (rekomendowane) |
|---|---|---|
| Koszt | 0 zł | ~25–60 zł/rok (Porkbun: `.eu` $5.88 flat, `.fyi` $5.66 flat, `.dev` $8.75 → $12.87; **unikać** `.xyz` $2.04 → $14.21 i `.online`/`.site` $1.96 → $28.84 przy odnowieniu) |
| Nadawca | dedykowany Gmail założony pod projekt, np. `outfits.garderobe@gmail.com` | `noreply@<domena>` |
| Co widzi odbiorca | `outfits.garderobe@<id>.brevosend.com` + sticker | `noreply@<domena>` + sticker |
| Ryzyko spamu | realne (shared pool + brak alignmentu) | niskie po DKIM/DMARC |
| Bonus | — | ładny URL na Railway (Hobby: 2 custom domains/serwis, bez dopłaty); otwarta droga do Resend/Mailtrap |

Darmowe subdomeny z delegacją NS (DigitalPlat `.dpdns.org`, eu.org) technicznie działają
z DKIM, ale reputacja stref jest słaba i zniknięcie usługi = utrata nadawcy. Nie dla maili
z linkami logowania.

**Nigdy** jako nadawca: adres `@duck.com`, `@icloud.com`, `@yahoo.com` (tabela DMARC wyżej).

## 3. Kroki

Wykonuje człowiek w przeglądarce; kroki 3.6–3.8 to zmiany w repo, które zastępują
odpowiednie punkty Fazy 4 w `plan.md`.

### 3.1 Konto Brevo

1. `https://app.brevo.com/` → rejestracja. Do logowania można użyć dowolnego adresu (Brevo
   będzie namawiać na „professional email" — to komunikat marketingowy, nie blokada).
2. Potwierdzić adres z maila powitalnego. Bez tego panel nie odblokuje wysyłki.
3. Plan: **Free**. Karta niepotrzebna.

Niepotwierdzone w dokumentacji (help center blokuje automatyczny odczyt): czy nowe konto
przechodzi ręczną walidację przez Brevo przed pierwszą wysyłką na zewnątrz. Historycznie
tak bywało. Jeśli po kroku 3.5 API zwraca 401/403 mimo poprawnego klucza — sprawdzić
banner w panelu i ewentualnie wypełnić formularz walidacji.

### 3.2 Nadawca (zawsze)

1. Panel → **Senders, Domains & Dedicated IPs → Senders → Add a sender**.
2. From name: `Outfits Garderobe`. From email: adres z decyzji w sekcji 2.
3. Brevo wysyła link weryfikacyjny na ten adres → kliknąć.
4. Zapisać dokładny adres — będzie `DEFAULT_FROM_EMAIL`. Brevo odrzuca wysyłkę z adresu,
   którego nie ma na liście zweryfikowanych nadawców.

### 3.3 Domena (tylko wariant z domeną)

1. Panel → **Senders, Domains & Dedicated IPs → Domains → Add a domain**.
2. Brevo pokaże rekordy do wpisania w DNS: kod weryfikacyjny (TXT), **DKIM** (TXT/CNAME
   pod `mail._domainkey` lub podobnym selektorem — skopiować dokładnie z panelu) oraz
   **DMARC** (`_dmarc` TXT, na start `v=DMARC1; p=none`).
3. Po propagacji (minuty–godziny) kliknąć **Authenticate** w panelu. Dopóki domena nie ma
   statusu uwierzytelnionej, Brevo podmienia From na `brevosend.com` — nie jest to błąd
   aplikacji, tylko sygnał, że DKIM nie przeszedł.
4. Dopiero teraz dodać `noreply@<domena>` jako nadawcę (3.2) — weryfikacja nadawcy w
   uwierzytelnionej domenie przechodzi bez klikania linku.

### 3.4 Klucz API (nie SMTP key)

1. Panel → prawy górny róg → **Settings → SMTP & API → zakładka API Keys → Generate a new
   API key**. Nazwa: `outfits-garderobe-railway`.
2. Klucz jest pokazywany **raz**. Skopiować od razu do menedżera haseł; do repo nigdy.
3. To musi być klucz **v3** (`xkeysib-…`). anymail: *„Must be a v3 key; v2 keys don't
   work."* Zakładka **SMTP** obok generuje inny sekret (SMTP key), który nas nie dotyczy —
   SMTP jest zablokowane na Railway Hobby.

### 3.5 Test poza aplikacją

Zanim cokolwiek trafi do Django, potwierdzić, że konto + nadawca + klucz działają razem.
Z lokalnej maszyny (nie z Railway — tu chodzi o Brevo, nie o sieć):

```bash
curl --request POST --url https://api.brevo.com/v3/smtp/email \
  --header "api-key: $BREVO_API_KEY" \
  --header 'content-type: application/json' \
  --data '{
    "sender": {"name": "Outfits Garderobe", "email": "<DEFAULT_FROM_EMAIL>"},
    "to": [{"email": "<skrzynka testowa, inna niż nadawca>"}],
    "subject": "Brevo smoke",
    "textContent": "Jesli to czytasz, konto Brevo jest gotowe."
  }'
```

Oczekiwane: HTTP **201** i `{"messageId": "..."}`. Potem sprawdzić skrzynkę odbiorcy
(w tym spam) i zapisać, jak wygląda pole From — w wariancie bez domeny będzie to
`…@<id>.brevosend.com`. Skrzynka testowa **nie może** być adresem nadawcy
(`plan-brief.md:68`); mail sam do siebie nic nie mówi o dostarczalności.

Panel → **Transactional → Logs** pokazuje zdarzenie (sent / delivered / soft-bounce); to
pierwsze miejsce do debugowania, gdy mail „nie doszedł".

### 3.6 Zależność w repo

```bash
uv add "django-anymail[brevo]"
```

Ekstra `[brevo]` dociąga `requests`. `pip-audit` po instalacji, jak przy allauth
(kryterium 2.7).

### 3.7 Settings

`outfits_garderobe/settings.py` — zamiast bloku SMTP z `plan.md:344`:

```python
INSTALLED_APPS += ['anymail']  # w istniejącej liście, obok 'allauth'

# Railway Hobby blokuje wychodzące SMTP (docs.railway.com/networking/outbound-networking),
# więc produkcja mówi do Brevo po HTTPS. Klucz czytany przez os.environ[...] z tego samego
# powodu co SECRET_KEY i MEDIA_ROOT: brak klucza ma wywrócić boot, nie cicho gubić
# linki resetu hasła.
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
    ANYMAIL = {'BREVO_API_KEY': os.environ['BREVO_API_KEY']}

# Musi być adresem zweryfikowanym w Brevo (Senders), inaczej wysyłka jest odrzucana.
DEFAULT_FROM_EMAIL = os.environ['DEFAULT_FROM_EMAIL']
```

`outfits_garderobe/settings_test.py` — do istniejącego bloku `setdefault`
(`settings_test.py:16-19`), z tego samego powodu co `SECRET_KEY`: suite działa z
`DEBUG=False`, więc bez stubów import settings rzuci `KeyError` i nic się nie zbierze:

```python
os.environ.setdefault('BREVO_API_KEY', 'test-only-not-a-real-key')
os.environ.setdefault('DEFAULT_FROM_EMAIL', 'test@example.invalid')
```

Backend w testach nadpisać na `locmem` (pytest-django robi to domyślnie przez
`django.test` — potwierdzić w suite, że żaden test nie próbuje uderzyć w Brevo).

`.env.example` — zamiast sześciu `EMAIL_*`:

```
BREVO_API_KEY=xkeysib-...          # Brevo → Settings → SMTP & API → API Keys (v3)
DEFAULT_FROM_EMAIL=noreply@example.com  # musi być zweryfikowanym nadawcą w Brevo
```

Pozostałe punkty Fazy 4 (`ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'`, HSTS,
`SESSION_COOKIE_AGE`, guard `check --deploy`) są niezależne od transportu i zostają bez
zmian.

### 3.8 Zmienne na Railway

Serwis `outfits-garderobe`, środowisko production:

```bash
railway variables --set "BREVO_API_KEY=xkeysib-..." --set "DEFAULT_FROM_EMAIL=<adres z 3.2>"
```

(lub Railway → serwis → Variables). Ustawić **przed** deployem z 3.7 — inaczej boot
wywróci się na `KeyError: 'BREVO_API_KEY'` i `/health/` nie wróci do 200.

### 3.9 Weryfikacja end-to-end

Odpowiada kryteriom 4.9–4.11 w `plan.md`:

1. Deploy zdrowy: `/health/` → 200; logi bez `KeyError`.
2. Rejestracja na produkcji ze skrzynki testowej → mail potwierdzający dochodzi, link jest
   `https://`, klik oznacza adres jako zweryfikowany.
3. Reset hasła → mail dochodzi, link działa.
4. Brevo → Transactional → Logs pokazuje oba zdarzenia jako *delivered*.
5. Zanotować w `change.md`: wariant nadawcy (domena / brevosend), data, ile z 300/dzień
   zużywa jeden pełny przebieg (rejestracja + reset = 2).

## 4. Delta względem `plan.md` (do wniesienia przy aktualizacji planu)

- **Phase 4 → 1. Settings — production email**: kontrakt SMTP (`EMAIL_HOST`… ×6) →
  `django-anymail[brevo]`, `ANYMAIL['BREVO_API_KEY']`, `DEFAULT_FROM_EMAIL`. Intent zyskuje
  zdanie o blokadzie SMTP na Railway Hobby.
- **Phase 4 → 6. Railway environment**: lista zmiennych → `BREVO_API_KEY`,
  `DEFAULT_FROM_EMAIL`. Kontrakt: „API key v3, nie SMTP key".
- **Phase 4 → nowy pkt 0. Brevo prerequisite**: odsyłacz do tego dokumentu; checkboxy w
  Progress: *4.0a konto + zweryfikowany nadawca*, *4.0b test curl → 201*, *4.0c decyzja
  domena/bez domeny zapisana w change.md*.
- **plan-brief.md:29** („Brevo SMTP, verified single sender") → „Brevo HTTP API; nadawca:
  domena własna lub Gmail z podmianą From". Ryzyko z `plan-brief.md:65` doprecyzować:
  „From przepisany na `brevosend.com` dopóki brak uwierzytelnionej domeny".
- **Performance Considerations**: nadal synchronicznie w request — HTTP zamiast SMTP nic
  tu nie zmienia; timeout anymail domyślnie 30 s (`ANYMAIL['REQUESTS_TIMEOUT']`), warto
  zejść do ~10 s, żeby awaria Brevo dawała błąd, nie zawieszony formularz.
- **Key Discoveries**: dodać wpis o blokadzie SMTP na Railway Hobby i o polityce DMARC
  `duck.com` (`p=quarantine`).

## 5. Pułapki

- **SMTP key ≠ API key.** Dwie zakładki obok siebie w panelu; tylko API key (v3) działa
  z anymail. SMTP key nie ma tu zastosowania w ogóle (Railway Hobby).
- **Nadawca niezweryfikowany = 4xx z API**, nie cicha porażka. Dobrze — ale tylko jeśli
  `DEFAULT_FROM_EMAIL` jest literalnie tym samym stringiem, co na liście Senders.
- **From `@duck.com`** wygląda kusząco (to Twój adres) i jest najgorszym możliwym wyborem
  spośród darmowych — `p=quarantine`.
- **Podmiana From na `brevosend.com` nie jest błędem**; jest udokumentowanym zachowaniem
  przy nieuwierzytelnionej domenie. Jedyne lekarstwo to uwierzytelnienie własnej domeny.
- **300/dzień liczy się per konto**, kampanie i transakcyjne razem. Na MVP nieosiągalne;
  gdy kiedyś sięgnie, panel pokaże `daily limit reached` w logach.
- **Klucz pokazany raz.** Zgubiony → wygenerować nowy, stary unieważnić w panelu,
  podmienić na Railway. Rotacja nie wymaga deployu, tylko restartu serwisu.

## Źródła

- Railway — Outbound Networking: https://docs.railway.com/networking/outbound-networking
- Brevo — Send a transactional email (endpoint, nagłówek, curl): https://developers.brevo.com/docs/send-a-transactional-email
- Brevo — SMTP relay integration (dla porównania; SMTP key vs API key): https://developers.brevo.com/docs/smtp-integration
- Brevo — Free SMTP server / plan Free: https://www.brevo.com/free-smtp-server/
- Brevo — FAQ: limits of the Free plan (sticker): https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan
- Brevo — Create a new sender: https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email
- Brevo — Why you need to replace your free email address: https://help.brevo.com/hc/en-us/articles/4410613910418-Why-you-need-to-replace-your-free-email-address-with-a-professional-one
- Brevo — Comply with Gmail, Yahoo and Microsoft's requirements: https://help.brevo.com/hc/en-us/articles/14925263522578-Comply-with-Gmail-Yahoo-and-Microsoft-s-requirements-for-email-senders
- Brevo — Authenticate your domain (Brevo code, DKIM, DMARC): https://help.brevo.com/hc/en-us/articles/12163873383186-Authenticate-your-domain-with-Brevo-Brevo-code-DKIM-DMARC
- Brevo Community — Sender domain not authenticated (odpowiedź staff o podmianie From): https://community.brevo.com/t/sender-domain-not-authenticated/746
- django-anymail — Brevo: https://anymail.dev/en/stable/esps/brevo/
- django-anymail — Installation: https://anymail.dev/en/stable/installation/
- Porkbun — ceny domen (rejestracja vs odnowienie): https://porkbun.com/products/domains
- Railway — custom domain limit na Hobby: https://station.railway.com/questions/custom-domain-limit-f4c63116
