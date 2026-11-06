# ChessLens

ChessLens liest das Schachbrett auf deinem ersten Monitor ab, erkennt die Figuren und zeigt dir auf dem zweiten Monitor das Brett mit dem besten Zug als Pfeil – inklusive Bewertung, Alternativen und einer kurzen Erklärung auf Deutsch. Läuft komplett offline mit Stockfish.

> Gedacht für Partien gegen Bots, Training und Analyse. Online gegen fremde Spieler gilt Engine-Hilfe als Betrug und führt zu Account-Sperren.

## Installation

1. `ChessLens-windows.zip` entpacken (den kompletten Ordner, nicht nur die .exe).
2. `ChessLens\ChessLens.exe` starten.
3. Beim ersten Start meldet sich eventuell der Windows-SmartScreen („Unbekannter Herausgeber“): auf **Weitere Informationen → Trotzdem ausführen** klicken.

Es muss nichts installiert werden. Einstellungen und gelernte Profile liegen unter `%APPDATA%\ChessLens`.

## So funktioniert es

1. Schachspiel auf dem **ersten Monitor** öffnen, ChessLens erscheint automatisch auf dem **zweiten**.
2. Eine **neue Partie starten**, sodass die Grundstellung zu sehen ist. ChessLens lernt daraus den Figurensatz dieser Plattform und merkt sich ihn als Profil. Das passiert einmal pro Plattform (chess.com, lichess, eine App, …) – danach geht es auch mitten in einer Partie.
3. Spielen. Nach jedem Zug aktualisiert sich die Anzeige von selbst:
   - **Dicker grüner Pfeil** = dein empfohlener Zug. Oben rechts steht er groß in Notation (z. B. `Sf6`) und in Worten („Springer g8 → f6“).
   - **Dünne Pfeile** (gelb, blau) = zweit- und drittbester Zug.
   - **Balken links** = wer steht besser (weißer Anteil = Vorteil Weiß).
   - **„Warum dieser Zug“** = Erklärung: Schach, Gabel, Fesselung, Drohung, Material, Idee aus der Hauptvariante.
   - **Alternativen** = die drei besten Züge mit Bewertung und Fortsetzung.
   - Ist der Gegner am Zug, zeigt ein roter Pfeil, was er wahrscheinlich spielt.

## Spielstile

Oben in der Mitte umschaltbar:

| Stil | Was er tut |
|---|---|
| **Engine pur** | Der objektiv beste Zug. |
| **Aggressiv** | Bevorzugt Schachs, Angriffe auf den König, Opfer und Druck. |
| **Solide** | Bevorzugt sichere Züge ohne hängende Figuren, Rochade, Entwicklung. |
| **Trickreich** | Bevorzugt Züge, bei denen die naheliegende Antwort des Gegners verliert („Fallen“). |

Ein Stil darf nur Züge wählen, die höchstens eine bestimmte Spanne schlechter sind als der beste Zug (einstellbar unter **Einstellungen → Spielstil darf …**, Standard 0,60 Bauern). Bei Mattvarianten zählt immer nur der beste Zug.

## Tasten und Knöpfe

| Im ChessLens-Fenster | Überall (auch wenn das Schach im Vordergrund ist) | Wirkung |
|---|---|---|
| **F9** | **Strg+Alt+P** | Pause / Fortsetzen |
| **F10** | **Strg+Alt+B** | Brett neu suchen (z. B. nach Fensterwechsel) |
| **F11** | **Strg+Alt+Z** | Zugrecht tauschen – wenn nach einem Neustart mitten in der Partie die falsche Seite am Zug ist |
| **F12** | **Strg+Alt+D** | Brett drehen – wenn Weiß und Schwarz vertauscht angezeigt werden |

Die systemweiten Kürzel lassen sich in den Einstellungen abschalten.

## Einstellungen

- **Monitore**: Auf welchem Monitor das Schach läuft und wo ChessLens angezeigt wird.
- **Brett von Hand festlegen**: Falls die automatische Erkennung das Brett nicht findet (sehr ungewöhnliche Designs), ein Quadrat über die 64 Felder ziehen.
- **Rechenzeit**: Wie lange Stockfish pro Stellung rechnet (Standard 2,5 s). Mehr Zeit = stärker, aber langsamer.
- **CPU-Kerne**: Standard „Automatisch“ (alle bis auf zwei).
- **Ton**: Kurzer Klang, sobald ein neuer Vorschlag fertig ist und du am Zug bist.
- **Profile**: Gelernte Figurensätze verwalten. Mitgeliefert: ein Profil für die App aus den Screenshots und eines für den lichess-Standardsatz.

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| „Suche Schachbrett …“ bleibt stehen | Brett muss vollständig sichtbar sein, nicht von Fenstern verdeckt. Prüfen, ob in den Einstellungen der richtige Monitor gewählt ist. Sonst „Brett von Hand festlegen“. |
| „Bitte eine neue Partie starten“ | Für diese Plattform gibt es noch kein Profil. Einmal die Grundstellung zeigen (neue Partie). |
| Falsche Seite am Zug | F11. |
| Brett steht Kopf | F12. |
| Figuren werden falsch erkannt | Einstellungen → Profil löschen und mit einer neuen Partie neu lernen. Verschiedene Brettfarben derselben Plattform sind kein Problem. |
| Stockfish fehlt | Das ZIP komplett entpacken; der Ordner `_internal\stockfish` muss vorhanden sein. |

**Diagnose:** Einstellungen → **„Diagnose speichern“** legt Screenshot, Brett-Ausschnitt und die Erkennung aller 64 Felder unter `%APPDATA%\ChessLens\diagnose` ab (der Ordner öffnet sich automatisch). Diese Bilder zeigen genau, was ChessLens sieht – ideal zum Weiterschicken, wenn etwas nicht erkannt wird.

Log-Datei bei Fehlern: `%APPDATA%\ChessLens\chesslens.log`.

## Selbst bauen

Windows mit Python 3.11/3.12: `build.bat` doppelklicken → `dist\ChessLens\ChessLens.exe`.
Die GitHub-Action in `.github/workflows/build.yml` baut bei jedem Push auf den Branch `chesslens` automatisch ein Release.

## Technik

- Bildschirmaufnahme: `mss`
- Brett-Erkennung: OpenCV – sucht gleichmäßig gefärbte Quadrate gleicher Größe, legt ein Raster hindurch und prüft das Schachbrettmuster (funktioniert für jede Plattform, Farbe und Fenstergröße)
- Figuren: Vorlagen, die aus der Grundstellung gelernt werden (Masken-Überlappung + normierte Kreuzkorrelation), Figurenfarbe über Helligkeit
- Partie: `python-chess` rekonstruiert aus zwei Stellungen den gespielten Zug (inkl. Rochade, en passant, Umwandlung)
- Engine: Stockfish 17.1 (GPLv3, Quellcode: https://github.com/official-stockfish/Stockfish), bis zu 5 Varianten
- Oberfläche: PySide6 (Qt), Figurengrafiken aus python-chess (CC BY-SA), Schrift Manrope (OFL)
