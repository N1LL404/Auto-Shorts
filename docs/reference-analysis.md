# DrDonut reference analysis

Nine edited Shorts were supplied, reported by the editor as having 45K–3M views, plus one unedited stream recording. All nine Shorts are 2160×3840 at 60 fps. Their median duration is 51.73 seconds. Seven run between 32 and 63 seconds, with two longer examples near 100 and 110 seconds. The examples show how the edits are constructed. They do not establish which editing choices caused the view counts.

## Frame measurements

Every decoded frame was measured at reduced spatial resolution with original frame cadence preserved. The scan calculated mean brightness and frame-to-frame RGB change in eight horizontal bands. In the table, “Visual peaks” lists up to six of the largest gameplay region changes. A peak required mean change of at least 20 on the 0–255 scale and change above 15 in at least five of the six lower bands. Nearby detections within 0.45 seconds were grouped. These are timestamps to inspect for fast movement, menu transitions or edits. The metric cannot reliably distinguish those causes. Visual content was reviewed using time-indexed contact sheets and larger stills.

| Clip | Duration | Frames | Observed structure | Visual peaks (s) |
| --- | ---: | ---: | --- | --- |
| 03 | 45.23 s | 2,714 | Persistent “IRON GOLEM + MACE” headline. Tower setup, airborne attack, then ground-level aftermath. | 26.80, 36.90, 42.73, 43.27, 43.90, 44.90 |
| 04 | 109.60 s | 6,576 | A conversation with another player in a diamond-block room. Player view, chat and inventory take turns providing context. Dialogue captions appear above the HUD. | 61.93, 62.83, 67.63, 79.13, 79.67, 103.33 |
| 05 | 62.17 s | 3,730 | Starts at a structure, pulls out to a flight sequence, then returns to the build and nearby activity. | 17.17, 19.60, 20.77, 26.27, 51.70, 55.83 |
| 06 | 50.67 s | 3,040 | Movement into a dark enclosed space, a long inventory and reaction beat, then a death screen. | 2.77, 3.37, 3.87, 4.47, 6.47, 15.40 |
| 07 | 59.40 s | 3,564 | A group encounter turns into lava, outdoor combat and underground movement. | 12.50, 13.00, 16.03, 26.50, 29.60, 47.77 |
| 08 | 32.17 s | 1,930 | A tight passage leads into a trap sequence, inventory and a visible death. Short emphasized dialogue captions. | 5.47, 6.63, 8.27, 12.37, 13.90, 16.27 |
| 09 | 99.70 s | 5,982 | Extended interaction in a hall followed by outdoor device and player activity. The camera can hold still for context. | 32.17, 33.00, 42.17, 63.90, 85.77, 86.53 |
| 10 | 46.27 s | 2,776 | Question headline persists through inventory, flight, a large portrait reveal around 20–25 s, and the reaction afterward. | 1.70, 9.47, 12.33, 41.43, 42.67, 43.63 |
| 12 | 51.73 s | 3,104 | Underground with another player, a chest, a dark opening, then death. The payoff arrives well after the first movement shifts. | 9.20, 9.87, 32.50, 43.77, 44.30, 46.97 |

## Editing choices in the tool

- **Frame:** The facecam occupies approximately the top quarter. Gameplay fills the lower pane. The source recording has an embedded top-left camera and a bottom-center HUD. Auto-Shorts crops the two regions separately and anchors the gameplay pane at the bottom.
- **Text:** Compact uppercase seam headlines establish the premise before the payoff. White text with a dark outline is readable across both panes. Several references also emphasize select words with color. Optional dialogue captions sit higher than the HUD. The export currently uses a white outlined hook with optional yellow emphasis and grouped captions.
- **Timing:** Footage often remains continuous through a setup, action and reaction. Some payoffs are quiet or happen with a menu open. Audio, gameplay activity and optional Minecraft speech cues are combined, with a manual trim path for nuanced beats.
- **Source recording:** 1,792 decoded frames at 30 fps, 1918×1078, about 59.73 seconds. The most sustained camera movement is in the first ~18 seconds. Much of the remainder holds on the framed display with intermittent webcam reactions. This is suitable for layout and selection testing. The original streams corresponding to the published Shorts were unavailable, so exact edit decision lists could not be reconstructed.

No example videos or stream recordings are committed to this repository.
