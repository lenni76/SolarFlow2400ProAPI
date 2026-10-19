# Vier Verbesserungen – lokaler Stand vom 19.10.2026

Die vier besprochenen Verbesserungen sind im unveröffentlichten gemeinsamen
Stand 1.2.1 umgesetzt. Grundlage bleibt die über HACS installierte Version 1.2.0.
GitHub, deine HA-Installation und die SolarFlow wurden nicht verändert.

**Dein bestätigtes Regelungsziel bleibt 20 W Netzbezug**, in der Visualisierung
des separaten Nulleinspeisungs-Reglers veränderbar. In die API-Integration wurde
kein zweiter Zielwert eingebaut. Sie kennt keine Messung am Netzanschlusspunkt
und ersetzt deshalb nicht diesen Regler. Seine PID-Parameter und Regelmodi
wurden hier nicht verändert; frühere Befunde an diesem separaten Regler bleiben
gesondert zu bearbeiten.

## 1. Unnötige Schreibbefehle verringern

- Identische Sollwerte werden nur übersprungen, wenn sie im letzten erfolgreichen
  Bericht des richtigen Geräts enthalten waren und dessen Abruf höchstens fünf
  Sekunden zurückliegt. Nach einem Schreibversuch oder Lesefehler ist diese
  Bestätigung ungültig, bis ein neuer passender Bericht vorliegt.
- Veraltete oder vor einem zwischenzeitlichen Schreibversuch begonnene
  Geräteabfragen dürfen keine frische Bestätigung für Doppelbefehle liefern.
- Nach einem fehlgeschlagenen Befehl wird die nächste Anforderung nicht aufgrund
  des Zwischenspeichers übersprungen.
- **0 W bei Ausgangsleistung oder AC-Ladeleistung werden immer gesendet.**
- Es gibt keine zusätzliche Mindestpause, Leistungs-Totzone oder Hysterese.
  Die bislang vorhandene Schreibsperre und Prüfwartezeit bleiben bestehen.
  Eine laufende Bestätigung kann deshalb nachfolgende Befehle weiterhin aufhalten;
  eine sofortige, verzögerungsfreie physische Gegenregelung wird nicht behauptet.
- Die Unterdrückung ist im Optionsdialog abschaltbar und standardmäßig an.

Vier neue Diagnose-Sensoren zählen seit dem Start/Neuladen der Integration:

| Anzeige | Bedeutung |
|---|---|
| API-Schreibversuche | Alle versuchten HTTP-Schreibaufrufe einschließlich Wiederholungen und Recovery; auch ein Aufruf mit ausbleibender Antwort zählt. |
| Vermiedene Schreibbefehle | Wegen eines passenden, kürzlich abgerufenen Sollwerts übersprungene Anforderungen. |
| Befehlswiederholungen | Zusätzliche normale Schreibversuche nach fehlender Bestätigung. |
| Recovery-Schreibversuche | Teilmenge der API-Aufrufe für Moduswechsel, Wiederherstellung und erneuten Stellbefehl während Recovery. |

Diese Zähler messen **keine physischen Flash-Schreibvorgänge**. Alle Werte beginnen
nach Neuladen der Integration neu bei null. Das tatsächliche Einsparpotenzial
hängt von der Häufigkeit gleicher Sollwerte deiner Automationen ab.

## 2. Fehler zuverlässig an HA melden

Bei aktivierter Befehlsprüfung muss der Sollwert im Bericht des konfigurierten
Geräts exakt bestätigt werden. Nach der einmaligen Wiederholung und gegebenenfalls
zulässiger Recovery führt eine weiter fehlende Bestätigung zu einem
`HomeAssistantError`. Auch Netzwerkfehler bei der Wiederholung werden einheitlich
behandelt. Der aufrufende Regler erhält dadurch einen Fehler statt einer
scheinbar erfolgreichen Service-Antwort.

Das Befehlsresultat wird zusammen mit seiner bestätigenden Rückmeldung an die
Entitäten veröffentlicht. Ohne aktivierte Prüfung steht ausdrücklich
**„Gesendet, nicht geprüft“**, Erfolg bleibt unbekannt. Ein bestätigtes
Sollwertregister ist weiterhin kein Beleg für die tatsächlich abgegebene Leistung.

Quelle für das HA-Fehlerverhalten:
[Fehler bei fehlgeschlagenen Aktionen](https://contributors.home-assistant.io/core/quality-scale/action-exceptions/).

## 3. Recovery und Diagnosen absichern

Recovery bleibt **standardmäßig aus**; bestehende Optionswerte werden beibehalten.
Sie ist nur zulässig, wenn ein frischer Gerätebericht folgende Voraussetzungen
bestätigt: Ausgangsbefehl über 0 W, `acMode: 2` und `gridReverse: 2`.
Eine Ladesteuerung darf zur Recovery nicht kurzzeitig Entladen aktivieren.
Eine fehlende Rückspeisesperre wird nicht eigenmächtig eingeschaltet.

Der ursprüngliche AC-Modus wird auch nach ausbleibender Antwort des ersten
Moduswechsels oder einem Abbruch wiederherzustellen versucht. Die Wiederherstellung
wird anhand einer erneuten Geräteabfrage geprüft, bei Bedarf höchstens einmal
wiederholt. Eine verlorene Schreibantwort erfordert keine zweite Wiederherstellung,
wenn der Bericht bereits den richtigen Modus bestätigt.

Bei Abbruch wartet der Ablauf auf die durch vorhandene HTTP-Zeitlimits begrenzte
Wiederherstellung. Die Schreibsperre bleibt dabei gehalten, sodass ein nachfolgender
Befehl nicht mit dem Aufräumen kollidiert. Schlägt die Wiederherstellung fehl,
werden der ausstehende Modus und **„AC-Modus unbestätigt“** angezeigt. Der Zielbefehl
wird dann nicht noch einmal angewendet. Ein späterer passender Bericht kann den
aktuellen Modusalarm aufheben; der historische Befehlsfehler bleibt erhalten.
Bei unabhängig abgebrochener Wiederherstellung bleibt das Ergebnis unbestätigt.

**Zendure Status/Zustand** beschreiben jetzt den aktuellen Beobachtungsstand,
einschließlich Gerätefehler `is_error`, veralteter/fehlgeschlagener Abfrage und
ungeklärtem AC-Modus. **Letzter Steuerbefehl** hält getrennt davon Status, Fehler,
Soll-/Rückmeldewert und Zähler bereit. Ein früherer Befehlsfehler wird nicht als
dauerhaft aktueller Gerätefehler ausgegeben. Eine erfolgreich gelesene Rückmeldung
beseitigt umgekehrt keinen historischen Befehlsfehler.

Die Recovery kann nicht garantieren, dass ein nicht erreichbares Gerät einen
Rückstellbefehl übernimmt. Auch `gridReverse: 2` ist keine Garantie für die
Nulleinspeisung deiner gesamten Anlage. Herstellerreferenz:
[AC-Modus und Rückspeisungsmodus](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/docs/zh_properties.md).

## 4. Verständlichere Bedienung

- Deutsche und englische Namen für die dokumentierten Messwerte und Bedienelemente.
- Bestehende Unique IDs und Auswahlwerte bleiben erhalten. Bestehende Entity IDs
  werden nicht aktiv umbenannt; selbst vergebene Namen bleiben in HA maßgeblich.
- Ausgangs- und AC-Ladeleistung in **1-W-Schritten**; deren angezeigte Obergrenzen
  berücksichtigen die gemeldete Wechselrichter-/Ladegrenze innerhalb der bisherigen
  UI-Obergrenze von 2400 W. Fehlende oder ungültige Angaben fallen auf diese
  UI-Obergrenze zurück; daraus wird kein universelles Herstellermaximum abgeleitet.
- smartMode heißt **„Flash-Speicherung unterdrücken (smartMode)“**. Sein Hinweis
  erklärt: eingeschaltet werden Änderungen nicht dauerhaft gespeichert; nach
  Geräte-Neustart gelten vorher gespeicherte Werte. Kein automatisches Umschalten.

Die Auswahltexte von `acMode` und `gridReverse` bleiben für bestehende Automationen
unverändert. Bei `gridReverse` bedeutet 2 laut Hersteller Rückspeisung verbieten.

## Spätere Kontrolle über die Oberfläche

Erst nach Veröffentlichung und HACS-Update mit vollständigem HA-Neustart:

1. Unter **Einstellungen → Geräte & Dienste → SolarFlow2400-API → Konfigurieren**
   die neue Option für bereits bestätigte gleiche Sollwerte prüfen. Befehlsprüfung
   eingeschaltet und Recovery zunächst ausgeschaltet lassen.
2. Im bearbeitbaren Dashboard **Bearbeiten → Karte hinzufügen → Entitäten** wählen.
   Die vorhandene **Ziel-Netzbezug**-Entität deines separaten Reglers mit aktuell
   **20 W**, die Netzleistung deines Zählers, die Ausgangsleistung zum Haus,
   die Ausgangsleistungsbegrenzung und die vier neuen Zähler auswählen.
   Die tatsächlichen vorhandenen Entitäten auswählen; keine neuen IDs abtippen.
3. **Letzter Steuerbefehl** und **Zendure Zustand** ergänzen. Im Detaildialog des
   letzten Befehls sind Bestätigung, letzter Fehler und ausstehender AC-Modus sichtbar.
4. Normale Lastwechsel beobachten: Ziel-Netzbezug, gemessene Netzleistung,
   angeforderte Begrenzung und tatsächliche Ausgangsleistung getrennt vergleichen.
   Keine absichtlichen Recovery-/Ausfallversuche am laufenden Gerät erforderlich.

Bei unverändertem Report entstehen vier zusätzliche Hauptgeräte-Diagnosen und
eine Batterie-Diagnose: voraussichtlich **68 Hauptgeräte- und 10 Batterie-Entitäten**
einschließlich deaktivierter Entitäten. Die Zahl hängt vom gemeldeten Datensatz ab.

## Validierung und verbleibende Arbeit

**68 isolierte Tests erfolgreich**, darunter der vollständige geänderte Coordinator
mit simuliertem Gerät, ignorierten Befehlen, Schreib-/Lesefehlern, verlorenen
Antworten, Gegenregelungsbefehlen, Recovery-Abbruch und wiederholter Abbruchanforderung.
UI-Limits, Übersetzungsstruktur, Optionen, bestehende Unique IDs sowie die früheren
API-/HA-Korrekturen werden mitgeprüft. Ruff-Lint und Formatierung des vollständigen
Integrations- und Testcodes sind erfolgreich.

Python 3.12.14, aiohttp 3.14.5; HA-Dienste sind Test-Doubles. Kein vollständiger
HA-/Hardwaretest, kein hassfest-/HACS-Validator-Lauf. Es wurden keine Gerätebefehle
an deine SolarFlow geschickt. Neue unbekannte Batterie-Felder, gezielte
`packData`-Normalisierung, automatische Wiederherstellung der HA-Sollwerte nach
Geräteneustart und eine Veröffentlichungs-CI bleiben gesonderte Erweiterungen.
