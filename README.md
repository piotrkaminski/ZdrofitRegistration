# Zdrofit Automatic Fitness Class Registration 🏋️‍♂️

Automatyczny skrypt do rejestracji na zajęcia fitness w sieci **Zdrofit** (np. *Sztangi* w niedzielę o 08:30 w klubie *Żerniki Wrocławskie Zasłuczańska*).

Skrypt został opracowany na podstawie szczegółowej analizy ruchu sieciowego z pliku HAR (`input-resources/zdrofit.pl.har`).

---

## 🔍 Wnioski z analizy pliku HAR

1. **Zasada 48 godzin**:
   - Rejestracja na zajęcia w Zdroficie otwiera się **dokładnie 48 godzin przed rozpoczęciem zajęć**.
   - Na zajęcia w **niedzielę o 08:30** (np. *Sztangi* 25.10.2026) rejestracja rusza w **piątek o 08:30:00**.
   - Skrypt liczy czas zawsze w strefie **Europe/Warsaw** (niezależnie od strefy ustawionej na Macu), a 48 godzin liczy „po zegarze" — także przy zmianie czasu letni/zimowy (niedziela 08:30 → piątek 08:30). Nie zostało to jeszcze potwierdzone na weekendzie zmiany czasu (25.10.2026).
   - Przed tym czasem element na liście ma status `item-registration-early` oraz informację: *"Za wcześnie by zarezerwować"*.
2. **Architektura rejestracji i CSRF**:
   - Każde zajęcia posiadają unikalny identyfikator (np. `2519672` dla Sztang w niedzielę, `2509771` dla Treningu Siłowego dla kobiet z pliku HAR).
   - Kliknięcie przycisku *"Zapisz się"* wysyła zapytanie `GET /kluby-fitness/{klub}/grafik-zajec/{id}` w celu pobrania formularza i jednorazowego tokena CSRF (`schedule_register_form[_token]`).
   - Następnie wysyłany jest `POST /kluby-fitness/{klub}/grafik-zajec/{id}` z parametrami:
     ```
     schedule_register_form[id]={id}
     schedule_register_form[_redirect]=
     schedule_register_form[_token]={csrf_token}
     ```
   - Po pomyślnym zapisie serwer zwraca stronę z blokiem danych zajęć `<div class="registration" id="a{id}">` zawierającym `<span class="icon labelled tick">Zapisano</span>` oraz link *"Anuluj rezerwację"* do `/grafik-zajec/{id}/zapisz` (tam znajduje się formularz *"Wypisz się"*).
   - **Uwaga:** skrypt potwierdza zapis wyłącznie na podstawie bloku `id="a{id}"` danych zajęć (lub formularza *"Wypisz się"* pod `/zapisz`). Każda odpowiedź serwera zawiera np. CSS `.sticky` i linki `#rezerwacja`, a strona może pokazywać *"Zapisano"* przy innych zajęciach — przeszukiwanie całej strony dawałoby fałszywe potwierdzenia.
3. **Zabezpieczenia CloudFront i AWS WAF**:
   - Serwis `zdrofit.pl` chroniony jest przez AWS WAF (`x-amzn-waf-action: challenge`). Zwykłe zapytania `curl` lub Python `requests` bez silnika przeglądarki otrzymują kod `202 Challenge`.
   - Z tego względu skrypt wykorzystuje **Playwright** z zainstalowaną na Twoim Macu przeglądarką **Google Chrome** (`/Applications/Google Chrome.app`), co pozwala bez problemu ominąć zabezpieczenia WAF i utrzymać aktywną sesję użytkownika w `session.json`.

---

## 🚀 Szybki start (Instalacja)

Projekt posiada skonfigurowane środowisko wirtualne `.venv` z wymaganymi bibliotekami (`playwright`, `beautifulsoup4`, `python-dateutil`).

Jeśli chcesz je zainstalować od nowa:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 🔑 Krok 1: Jednorazowe logowanie (`--login`)

Ponieważ formularz logowania do Zdrofit zawiera zabezpieczenie Google reCAPTCHA, najwygodniejszym i najbezpieczniejszym sposobem jest jednorazowe zalogowanie się w oknie przeglądarki:

```bash
.venv/bin/python3 register.py --login
```

1. Otworzy się okno Google Chrome ze stroną logowania Zdrofit.
2. Zaloguj się na swoje konto i rozwiąż ewentualną captchę.
3. Skrypt automatycznie wykryje zalogowanie i zapisze ciasteczka do pliku `session.json`.
4. Wszystkie kolejne uruchomienia będą działać **w pełni automatycznie w tle (headless)** bez otwierania widocznego okna.

---

## 📋 Krok 2: Sprawdzenie grafiku (`--list`)

Możesz przejrzeć dostępne zajęcia na dany dzień:

```bash
# Grafik na najbliższą niedzielę:
.venv/bin/python3 register.py --date next-sunday --list

# Grafik na dowolny dzień (np. jutro lub konkretna data):
.venv/bin/python3 register.py --date 2026-10-25 --list
```

Przykładowy wynik:
```
TIME    | ACTIVITY                       | TRAINER                | SPOTS  | STATUS
-------------------------------------------------------------------------------------
08:30   | Sztangi                        | Arkadiusz Zioło        | 0/30   | [EARLY - 48h]
09:40   | Zdrowy Kręgosłup               | Arkadiusz Zioło        | 0/30   | [EARLY - 48h]
10:40   | Techniki oddechowe             | Marta Kowalczyk        | 0/30   | [EARLY - 48h]
...
```

## 📋 Krok 3: Definiowanie stałych zajęć w pliku konfiguracyjnym (`classes.json`)

Możesz zdefiniować listę swoich ulubionych zajęć w pliku [classes.json](file:///Users/pkaminski/private/projects/ZdrofitRegistration/classes.json):

```json
{
  "club": "zerniki-wroclawskie-zasluczanska",
  "classes": [
    {
      "name": "Sztangi - Niedziela",
      "exercise": "Sztangi",
      "weekday": "Sunday",
      "time": "08:30",
      "enabled": true
    },
    {
      "name": "HIIT - Środa",
      "exercise": "HIIT",
      "weekday": "Wednesday",
      "time": "08:30",
      "enabled": true
    }
  ]
}
```

### Tryb synchronizacji (`./sync.sh` lub `--sync`):
Możesz uruchomić skrypt jednym prostym poleceniem:
```bash
./sync.sh
```
*(lub tradycyjnie: `.venv/bin/python3 register.py --sync`)*
Skrypt:
1. Pobiera grafik Twojego klubu (lub klubów — reguła może mieć własne pole `"club"`).
2. Weryfikuje każde zdefiniowane zajęcia w pliku `classes.json`. Dla każdej reguły wybiera **jedne, najlepiej dopasowane zajęcia na dany dzień** (dokładna nazwa ma pierwszeństwo, np. `HIIT` nie zapisze Cię na `HIIT Kids`).
3. Jeśli którekolwiek zajęcia **mieszczą się w oknie 48 godzin** i nie jesteś jeszcze zapisany — **automatycznie rejestruje Cię na nie w jednej sesji**!
4. Dla zajęć, na które jest jeszcze za wcześnie (> 48h), wyświetla dokładny czas otwarcia zapisów.
5. Jeśli zapisy na którekolwiek zajęcia ruszają w ciągu **najbliższych 6 minut**, automatycznie przechodzi w tryb oczekiwania (`--wait`) i zapisuje Cię co do milisekundy. Dlatego tryb synchronizacji należy uruchamiać **co 5 minut** (patrz Krok 5).
6. Reguły z błędami (brak pola `exercise`, zły format `time`, nieznany `weekday`, niepoprawna `date`) są pomijane ze statusem `⚠️ BŁĘDNA REGUŁA` — nie przerywają działania pozostałych.
7. Wyświetla podsumowanie w czytelnej tabeli:

```
==========================================================================================
  SYNC RESULTS SUMMARY
==========================================================================================
RULE NAME              | EXERCISE         | DATE & TIME      | STATUS          | DETAILS
------------------------------------------------------------------------------------------
Sztangi - Niedziela    | Sztangi          | 2026-10-25 08:30 | 🕒 ZA WCZEŚNIE   | Opens in 4 days, 15:23:58 (2026-10-23 08:30)
HIIT - Środa           | HIIT             | 2026-10-21 08:30 | 🕒 ZA WCZEŚNIE   | Opens in 15:23:58 (2026-10-19 08:30)
==========================================================================================
```

> **Wskazówka:** Możesz użyć opcji `--dry-run`, aby tylko sprawdzić status bez wysyłania żądań zapisu (działa także z `--wait` i `--now` — w trybie dry-run skrypt nigdy nie wysyła zapisu):
> ```bash
> .venv/bin/python3 register.py --sync --dry-run
> ```

---

## 🎯 Krok 4: Rejestracja pojedynczych zajęć z linii poleceń

### Sprawdzenie konkretnych zajęć (obsługa literówek np. `szangi`):
```bash
.venv/bin/python3 register.py --date next-sunday --time 08:30 --exercise szangi
```
*Skrypt dzięki algorytmowi podobieństwa napisów (fuzzy matching) automatycznie dopasuje `szangi` do `Sztangi`.*

### Tryb oczekiwania i rejestracji co do milisekundy (`--wait`):
Gdy uruchomisz skrypt z flagą `--wait`:
1. Obliczy dokładny moment otwarcia zapisów (48h przed zajęciami, np. piątek 08:30:00).
2. Poczeka do 15 sekund przed otwarciem zapisów.
3. Zainicjalizuje sesję w tle.
4. Dokładnie w ułamku sekundy `08:30:00.000` pobierze token i wyśle żądanie zapisu.
5. W razie minimalnego opóźnienia zegara serwera lub chwilowego błędu sieci ponawia próby (co 300–500 ms, przez maks. 15 sekund) aż do potwierdzenia zapisu.

```bash
.venv/bin/python3 register.py --date next-sunday --time 08:30 --exercise sztangi --wait
```

### Natychmiastowa rejestracja (`--now`):
Jeśli zapisy są już otwarte:
```bash
.venv/bin/python3 register.py --date tomorrow --time 19:30 --exercise sztangi --now
```

---

## ⏰ Krok 5: Automatyczne uruchamianie wg harmonogramu (macOS)

Aby nie musieć pamiętać o uruchamianiu skryptu, możesz skonfigurować harmonogram w systemie macOS.

Szczegółowe polecenia i gotowe szablony (z poprawnymi ścieżkami dla Twojego Maca) wyświetlisz poleceniem:
```bash
.venv/bin/python3 register.py --schedule-help
```

> **Wygasła sesja:** jeśli zapisana sesja (`session.json`) wygaśnie, skrypt wyświetli powiadomienie macOS z prośbą o ponowne uruchomienie `register.py --login`.

### Opcja A (zalecana): Synchronizacja `classes.json` co 5 minut
Uruchamia `--sync` co 5 minut. Każde zajęcia z `classes.json` zostaną zarezerwowane: przebieg, który wypadnie w ciągu 6 minut przed otwarciem zapisów, poczeka na nie i zapisze Cię co do milisekundy.

Wpis `cron` (`crontab -e`):
```cron
*/5 * * * * cd /Users/pkaminski/private/projects/ZdrofitRegistration && /Users/pkaminski/private/projects/ZdrofitRegistration/.venv/bin/python3 /Users/pkaminski/private/projects/ZdrofitRegistration/register.py --config classes.json --sync >> /Users/pkaminski/private/projects/ZdrofitRegistration/logs/sync_cron.log 2>&1
```
Lub usługa `launchd` (`StartInterval` = 300 s) — gotowy plik `com.zdrofit.sync.plist` wygeneruje `--schedule-help`.

### Opcja B: Pojedyncze zajęcia przez `cron`
Edytuj tabelę zadań:
```bash
crontab -e
```
Dodaj wpis uruchamiający skrypt w każdy piątek o godzinie 08:29 (minutę przed otwarciem zapisów):
```cron
29 8 * * 5 cd /Users/pkaminski/private/projects/ZdrofitRegistration && /Users/pkaminski/private/projects/ZdrofitRegistration/.venv/bin/python3 /Users/pkaminski/private/projects/ZdrofitRegistration/register.py --date 'next-sunday' --time '08:30' --exercise 'sztangi' --wait >> /Users/pkaminski/private/projects/ZdrofitRegistration/logs/cron.log 2>&1
```

### Opcja C: Pojedyncze zajęcia przez usługę macOS `launchd`
`launchd` potrafi wybudzić komputer lub uruchomić zadanie w tle.
Plik konfiguracji możesz zapisać w:
`~/Library/LaunchAgents/com.zdrofit.registration.plist`

I załadować:
```bash
launchctl load ~/Library/LaunchAgents/com.zdrofit.registration.plist
```

### Opcja D: Uruchomienie w tle z zapobieganiem uśpieniu (`caffeinate`)
Jeśli chcesz zostawić komputer włączony:
```bash
caffeinate -i .venv/bin/python3 register.py --date next-sunday --time 08:30 --exercise sztangi --wait &
```

---

## 📁 Struktura projektu

- `register.py`: Główny skrypt CLI (`--login`, `--list`, `--sync`, `--wait`, `--now`, `--dry-run`, `--schedule-help`).
- `sync.sh`: Skrót uruchamiający `--sync` (tworzy `.venv` w razie potrzeby i zapobiega uśpieniu Maca przez `caffeinate`).
- `classes.json`: Lista stałych zajęć do automatycznej rezerwacji.
- `zdrofit/client.py`: Klient Zdrofit oparty na Playwright — pobieranie grafiku, szybki zapis w kontekście strony, walidacja sesji.
- `zdrofit/date_parser.py`: Inteligentne parsowanie dat w języku polskim i angielskim (`niedziela`, `next-sunday`, `jutro`, `YYYY-MM-DD`) oraz zegar w strefie `Europe/Warsaw`.
- `zdrofit/matcher.py`: Fuzzy matching nazw ćwiczeń (np. `szangi` ➔ `Sztangi`, `trening silowy dla kobiet` ➔ `Trening siłowy dla kobiet`).
- `zdrofit/scheduler.py`: Generator konfiguracji dla `cron` oraz `launchd`.
- `session.json`: Zapisana sesja logowania (ciasteczka i stan przeglądarki).
- `input-resources/zdrofit.pl.har`: Załączony plik z ruchem sieciowym.
