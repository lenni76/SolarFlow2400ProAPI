# API-Abgleich SolarFlow2400-API – 19.10.2026

**Fortgeschriebener Stand:** Die vier anschließend beauftragten Verbesserungen
für Schreibreduzierung, Fehlerbehandlung, Recovery/Diagnosen und Bedienung sind
inzwischen lokal umgesetzt und durch insgesamt **68 Tests** geprüft. Die
[Umsetzung und Bedienung](VERBESSERUNGEN-UND-BEDIENUNG.md) beschreibt den aktuellen
Stand. Die unten stehenden ursprünglichen Vorschläge dokumentieren die vorherige
Prüfung; sie sind für diese vier Punkte durch die Umsetzung überholt.

Die lokal vorbereitete Version 1.2.1 berücksichtigt nach den unten beschriebenen
Korrekturen die dokumentierten Mess- und Steuerfelder der lokalen HTTP-API.
Es bleiben Dokumentationswidersprüche und Verbesserungsvorschläge offen.
Ein vollständiger Funktionstest an der SolarFlow oder in HA fand nicht statt.
GitHub, die installierte HACS-Version, Firmware und Geräteeinstellungen wurden
bei dieser Prüfung nicht verändert.

## Geprüfte Grundlagen

- Integrationsbasis: Version 1.2.0, Commit
  `59b8ee3aae43a28be15a12a5d813d4975a3d7c42`.
- Aktueller offizieller zenSDK-Hauptzweig am Prüftag: Commit
  [`9b683892e84b8ffeb905ed52c066ea9b3ebc42c8`](https://github.com/Zendure/zenSDK/commit/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8),
  17.10.2026, OpenAPI-Dokumentversion **1.0.2**. Diese Dokumentversion ist weder
  die Gerätefirmware noch das Feld `version: 3` deines Geräteberichts.
- Herstellerquellen: [OpenAPI](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/docs/openapi.yaml),
  [englische Eigenschaften](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/docs/en_properties.md),
  [chinesische Eigenschaften](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/docs/zh_properties.md),
  [Discovery und HTTP](https://github.com/Zendure/zenSDK/blob/9b683892e84b8ffeb905ed52c066ea9b3ebc42c8/README.md),
  [Zendures eigene HA-Integration](https://github.com/Zendure/Zendure-HA/blob/master/custom_components/zendure_ha/entity.py).
- Dein übermittelter echter Report, in der Test-Fixture mit ersetzten
  Seriennummern. Die Firmwarezuordnung 2.0.2 stammt aus deiner früheren Angabe;
  der Bericht selbst bestätigt diese Gerätefirmwareversion nicht.
- Zielsystem: dein gemeldeter Core 2026.10.2. Core und Supervisor 2026.10.2 sowie
  HA OS 18.3 sind am Prüftag weiterhin der
  [offizielle stabile Stand](https://github.com/home-assistant/version/blob/master/stable.json).

## Abdeckung und Grenzen

| Bereich | Ergebnis |
|---|---|
| `GET /properties/report` | Richtiger Pfad; Hauptgerätewerte und separate `packData` werden verarbeitet. Dein Bericht enthält genau eine interne Batterie. |
| `POST /properties/write` | Richtiger Pfad und Körper `sn` plus `properties`; ein Feld pro Aufruf. Keine zusätzlichen automatischen Schreibbefehle eingeführt. |
| 13 Felder im Schreibschema | Alle bereits durch Number, Select oder Switch abgedeckt: `acMode`, `inputLimit`, `outputLimit`, `socSet`, `minSoc`, `gridReverse`, `inverseMaxPower`, `gridStandard`, `smartMode`, `batCalTime`, `Fanmode`, `Fanspeed`, `gridOffMode`. |
| 51 im Geräte-Reportschema aufgeführte Felder | Bestehende Sensoren, binäre Sensoren, Steuerungen oder deaktivierte Rohwertdiagnose. Dies sind teilweise auch schreibbare Felder, keine 51 ausschließlich lesbaren Eigenschaften. |
| 12 Batterie-Felder einschließlich `sn` | Nach Ergänzung `packType` und `heatState` vollständig zugeordnet. `sn` ist die Geräteidentität; elf mögliche Sensoren. Nur tatsächlich gemeldete Felder werden angelegt. |
| Zusätzliche Firmwarefelder | `oldMode`, `offGridState`, `socCompSwitch` und unbekannte Hauptgeräte-Skalare bleiben als deaktivierte Rohwertdiagnose erhalten. Keine erfundene Bedeutung. |
| mDNS | Der angekündigte HTTP-Port wird jetzt berücksichtigt; IPv6-Literale erhalten URL-Klammern. Ohne Port bleibt HTTP-Port 80. |
| `/rpc` | Dient laut SDK zur MQTT-Konfiguration und Statusabfrage. Nicht Bestandteil dieser HTTP-Polling-Integration; nicht ergänzt. Für ihre bestehende lokale Funktion nicht erforderlich. |

Die Rohwertdiagnose des Hauptgeräts wird beim Setup angelegt. Neue, erst später
auftauchende Hauptgerätefelder benötigen bislang einen erneuten Aufbau der
Integration. Für unbekannte zusätzliche Batteriefelder gibt es keinen generischen
Sensor-Fallback. Beide Erweiterungen bleiben Vorschläge.

`writeRsp` ist in der Eigenschaftstabelle als Antwortfeld ohne schreibbaren
Datentyp beschrieben und fehlt im aktuellen Schreibschema. Daraus wurde kein
zusätzliches Bedienelement abgeleitet. Der Wert wird intern mitgeführt, bisher
jedoch nicht als eigener Sensor angezeigt.

## Lokal umgesetzte API-Korrekturen

| Feld | Bisher | Korrigiertes Ergebnis aus deinem Report | Nachweis |
|---|---|---|---|
| `packData.batcur` | Nur Multiplikation mit 0,1; `65534` wurde 6553,4 A | Vorzeichenbehaftete 16-Bit-Auswertung, danach durch 10: **−0,2 A** | OpenAPI 1.0.2; auch Zendure-HA |
| `packData.totalVol` | `4780` wurde als 4780 V ausgegeben | Durch 100: **47,80 V** | Zendure-HA verwendet ausdrücklich Faktor 100; OpenAPI nennt nur V und lässt den Rohwertfaktor offen |
| `hyperTmp` | Deaktivierter Rohwertsensor ohne Temperatureinheit | `(2971−2731)/10` = **24,0 °C** | OpenAPI 1.0.2 |
| `packType`, Batterie-`heatState` | Keine Batterie-Sensoren dafür | Ergänzte, standardmäßig deaktivierte Diagnose-Sensoren | OpenAPI 1.0.2; Typ bleibt reservierter Rohwert |
| Discovery-Port | Automatisch entdeckter Port ignoriert | Angekündigten Port in Probe und gespeicherter Adresse verwenden | SDK-Discovery; HA-`ZeroconfServiceInfo` |

Die bisherigen Unique IDs bleiben unverändert. `hyperTmp` und `batcur` bleiben
standardmäßig deaktiviert. Dein Report ergänzt genau einen Batterie-Diagnosesensor
`packType`; `heatState` fehlt darin und wird deshalb nicht angelegt. Bei gleichem
Report sind damit zehn statt bisher neun Batterie-Entitäten zu erwarten,
einschließlich deaktivierter Entitäten. Die vorhandenen neun bleiben erhalten.

**Auswirkung auf Verläufe:** Die Spannungskorrektur verändert den Zahlenmaßstab
von `totalVol` bei gleichbleibender Einheit V und bestehender Entität. Frühere
falsch skalierte Zustände und Statistiken werden nicht rückwirkend korrigiert.
Eine eigene Automation oder Vorlage, die bislang manuell durch 100 geteilt hat,
muss beim späteren Update angepasst werden. Auch eine aktivierte Stromdiagnose
oder ein bisher als Rohwert verwendetes `hyperTmp` verändert seinen Zahlenwert.
Die jetzige lokale Vorbereitung verändert noch keine HA-Daten.

## Bewusst beibehaltene Werte und Dokumentationswidersprüche

- `socSet: 990` ergibt **99 %**, `minSoc: 60` ergibt **6 %**. Die chinesische
  Herstellerdokumentation nennt ausdrücklich Rohwerte 700–1000 bzw. 0–500.
  Das aktuelle OpenAPI-Schreibschema nennt dagegen Prozentgrenzen 70–100 und
  0–50. Eine strikte Schema-Validierung dieser Grenzen auf dem übertragenen
  Rohwert wäre für deine nachgewiesene Firmware falsch. Die bestehende
  Umrechnung beim Lesen und Schreiben bleibt daher erhalten.
- `maxTemp: 2901` ergibt unverändert **17,0 °C**; `BatVolt: 4777` ergibt
  **47,77 V**, `maxVol: 319` **3,19 V**, `minVol: 316` **3,16 V**.
- `Fanspeed` umfasst 0/1/2. Dies bestätigt OpenAPI 1.0.2 und löst den Widerspruch
  zwischen Tabellenbereich 0–1 und Beschreibung 0–2 im englischen Text auf.
- Die bisherige Auswahl für `gridReverse` bleibt aus Kompatibilitätsgründen
  `0`/`1`/`2`. Die chinesische Herstellerreferenz erklärt diese als deaktiviert /
  Rückspeisung erlauben / Rückspeisung verbieten. Lesbarere Beschriftungen können
  wir getrennt besprechen; eine Änderung der Auswahltexte kann Automationen betreffen.
- `acCouplingState: 57346` bleibt roh. Die Dokumentation erklärt nur Bits 0–3;
  weitere gesetzte Bits erlauben keine verifizierte Fehlerinterpretation.
- `dryNodeState` ist in OpenAPI widersprüchlich erklärt. Keine zusätzliche
  Interpretation als sicher offen/geschlossen eingeführt.
- Die Leistungsgrenzen 2400 W sowie 1440 Minuten bei `batCalTime` sind
  Integrations-/UI-Grenzen; keine durch das aktuelle SDK belegten Universalmaxima.
- Dein Bericht meldet **`smartMode: 1`**. Laut SDK unterdrückt dies das dauerhafte
  Speichern von Einstellungen im Flash; nach Neustart gelten zuvor gespeicherte
  Einstellungen. Das ist kein Nachweis für die Anzahl physischer Flash-Schreibzyklen
  und kein Anlass, automatisch Geräteeinstellungen zu ändern.

## Korrektur des früheren Prüfberichts

Der frühere Befund, eine leere erfolgreiche HTTP-200-Schreibantwort löse einen
Fehler aus, ist **zurückgezogen**. Der damalige Test simulierte den JSON-Decoder
falsch. [aiohttp 3.14.5](https://github.com/aio-libs/aiohttp/blob/v3.14.5/aiohttp/client_reqrep.py)
liefert für leere/weiße Antwortkörper `None`; der bestehende Client macht daraus
bereits `{}`. Bestätigt mit dem echten Decoder am unveränderten Original und am
vorbereiteten Stand. Dafür wurde kein unnötiger Client-Umbau vorgenommen.
Prüfbericht und ursprüngliches Szenario 16 wurden entsprechend korrigiert.

## Ursprüngliche Verbesserungsvorschläge und nachfolgende Umsetzung

**Verbindliche Zielvorgabe aus deiner Rückmeldung:** Netzeinspeisung vermeiden
und einen kleinen positiven Netzbezug bevorzugen. Du hast **20 W** bestätigt;
der Wert bleibt in der Visualisierung des separaten Reglers einstellbar.
Die API-Korrekturen verändern keine Leistungs-
oder Netzbezugs-Sollwerte. Dein Report meldet `gridReverse: 2`; laut chinesischer
Herstellerreferenz bedeutet dies Rückspeisung verbieten. Dies ersetzt keine
Regelung anhand der gemessenen Leistung am Netzanschlusspunkt und belegt keine
garantierte Nulleinspeisung der gesamten Anlage.

Für die vorgeschlagene Schreibreduzierung gilt deshalb: Die Gegenregelung bei
gemessener Einspeisung darf nicht durch pauschale Mindestabstände oder eine
symmetrische Totzone ausgebremst werden. Einen positiven Zielbezug einstellbar
machen und in allen Regelmodi berücksichtigen; Messalter, Stellbestätigung,
tatsächliche Ausgangsleistung und Ausfallverhalten gemeinsam prüfen. Diese
Regelungsänderungen am separaten Regler sind hier nicht umgesetzt. Die
Schreibreduzierung verwendet deshalb ausschließlich exakte kürzlich bestätigte
Werte; keine zusätzliche Totzone oder Mindestpause. Nullleistungsbefehle werden
immer gesendet. Die folgenden Punkte sind der ursprüngliche Vorschlagsstand;
Einzelheiten zur inzwischen erfolgten Umsetzung stehen im verlinkten Dokument.

1. **Schreibbefehle verringern und sichtbar machen.** Gleiche Sollwerte anhand
   hinreichend aktueller Rückmeldungen überspringen; bei Leistungsregelung
   konfigurierbare Mindestabstände und Hysterese prüfen. Tatsächliche HTTP-Aufrufe,
   Wiederholungen und Recovery getrennt zählen. Diese Zahlen nicht als gemessene
   physische Flash-Schreibvorgänge bezeichnen. Bei `smartMode: 1` eine bewusste
   Wiederherstellung der gewünschten HA-Sollwerte nach Geräte-Neustart besprechen.
2. **Fehlgeschlagene Befehle zuverlässig melden.** Nach endgültig fehlgeschlagener
   Bestätigung einen klaren HA-Servicefehler liefern und Diagnosen bei jedem
   Ausgangspfad abschließen. Derzeit kann eine ignorierte Anforderung ohne
   Ausnahme zurückkehren; Wiederholungsfehler werden anders behandelt.
3. **Recovery absichern.** Den ursprünglichen AC-Modus auch bei Abbruch oder
   Wiederherstellungsfehler behandeln und verbleibende Abweichungen klar melden.
   Recovery ist optional und standardmäßig aus. Keine automatische Aktivierung.
4. **Diagnosen belastbarer machen.** Gerätefehler `is_error` und veraltete
   Rückmeldungen berücksichtigen; alten Befehlsfehler und aktuellen Gerätezustand
   trennen. `writeRsp` gegebenenfalls als Rohwert ergänzen.
5. **Antworten strenger prüfen.** Fremde/leere Geräteidentität erkennen;
   Batterien gezielt aus `packData` statt aus beliebigen Objektlisten bilden.
   Neue Felder dynamisch ergänzen und unbekannte Batterie-Rohwerte erhalten.
6. **Bedienung verbessern.** Verständliche deutsche Namen, Erklärung des
   Flash-Verhaltens bei smartMode, tatsächlich verfügbare Leistungsgrenzen in
   der Oberfläche und verifizierte AC-Coupling-Bits als einzelne Diagnosen.
   Bestehende Automationen und unbekannte Bits dabei erhalten.
7. **Veröffentlichungen absichern.** Echte HA-Tests sowie hassfest/HACS-Prüfung
   automatisieren; reproduzierbare Versionen und Release-Tags bereitstellen.

Die ersten beiden Punkte haben aus der Codeprüfung den größten praktischen
Nutzen für deine ausschließliche HA-Steuerung. Die konkrete Einsparung lässt
sich erst mit deinen Automationen und der Häufigkeit ihrer Stellbefehle bestimmen.

## Prüfung und Übergabe

Die zunächst 30 isolierten Regressionstests prüfen die bisherigen HA-Kompatibilitätsänderungen
sowie API-Feldabdeckung, deinen anonymisierten Report, Vorzeichen-/Wertgrenzen,
SOC-Lese-/Schreibwerte, echte aiohttp-JSON-Decodierung, fehlerhafte Antworten,
Discovery-Port und unveränderte Unique IDs. Mit den vier Verbesserungen sind es
jetzt 68 Tests, einschließlich Befehlsfehlern, Recovery-Abbrüchen und UI. Keine
Netzwerkverbindung zum Gerät.

HA-Dienste sind Test-Doubles; dies ersetzt keinen vollständigen HA-/Gerätetest
und beweist nicht die Wirkung von Befehlen unter Firmware 2.0.4. Diese Firmware
wurde weder installiert noch durch einen Report geprüft. Tests verwenden Python
3.12.14 und aiohttp 3.14.5, entsprechend der in Core 2026.10.2 festgelegten
aiohttp-Version. Keine neue Laufzeitabhängigkeit in der Integration.

Die bereits vorbereiteten Umstellungen `via_device_id` und einzelner Reload
bleiben im gemeinsamen lokalen Stand enthalten. HACS-Veröffentlichung und
Installation erfolgen erst später nach ausdrücklichem Auftrag.
