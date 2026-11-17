# Desktop workspace and progress

The desktop app uses a dark studio palette, a prominent Generate Shorts action,
and separate Create & monitor, AI settings and Activity log tabs.

Two bars show the current operation and the four-stage pipeline. The pipeline
bar counts stages; it does not estimate elapsed or remaining time. During
Whisper inference the operation bar reports source audio timeline coverage.
DeepSeek displays the current section and animates while waiting for a response.
Export progress combines encoded duration within each clip and the number of
clips, giving each clip equal weight. Creating covers and ZIPs is indeterminate.
Source preparation and live capture remain indeterminate when no total is known.
Live processing repeats the stages for each captured window.

Progress arrives from worker events and is refreshed once per second. Errors
and stopped jobs stop animation; completion fills the bars even if the source
produces no suitable clips (the job message reports that outcome).

Validation includes worker-to-presentation events, malformed events, terminal
states, Whisper timeline reporting and real FFmpeg rendering with fixture speech
and AI selections. Native Windows appearance and packaged startup still need
verification using a new Windows workflow build.
