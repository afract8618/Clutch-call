# 🏈 Clutch Call

**The daily two-minute drill.** You're trailing late in the fourth quarter. Call every play, read the defense, manage the clock, and try to win it. Then see if you did better than the AI coach, who ran the same drive with the same luck.

## Modes

- **Daily Drive**: one new situation every day, the same for everyone. Results go into a shareable emoji grid (🟩🟨⬜🟥🏈).
- **Survivor**: random drives that get harder each round. One loss ends the run.

## How it plays

- Each snap the defense shows a look (Cover 0 blitz, two-high shell, loaded box, press man, soft zone). Some plays beat some looks.
- When the clock is running, 14–20 seconds burn before the next snap. Incompletions and out-of-bounds plays stop it. Timeouts and spikes save time.
- Weather matters: snow, wind, rain and fog change passing and kicking.
- Score too early and the opponent gets the ball back with whatever time you left them.

## Files

Everything is plain HTML, no build step.

| File | What it is |
|---|---|
| `index.html` | The whole game |
| `icon.svg` | App icon source |
| `icon-*.png`, `apple-touch-icon.png`, `favicon-32.png` | Icons |
| `manifest.webmanifest`, `sw.js` | Add-to-home-screen and offline support |

## Play it online (GitHub Pages)

1. Upload all files to the root of the repo.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, set Source to **Deploy from a branch**, branch **main**, folder **/ (root)**, then **Save**.
4. After a minute the game is live at `https://<your-username>.github.io/<repo-name>/`.
5. On iPhone, open it in Safari → Share → **Add to Home Screen** to get the icon on your phone.

## Customizing

Situations live in the `SCEN` list in `index.html`. Each one sets the scores, seconds left, field position (`yl` = yards from your own goal line), timeouts, weather and how often the defense shows each look. Add your own and they'll rotate into the daily schedule.
