# NEXUS website

Static site: one `index.html`, no build step, no dependencies (Google Fonts only).

## Host free

**GitHub Pages**
1. Create a repo (e.g. `nexus-site`), upload these files to the root.
2. Settings → Pages → Deploy from branch → `main` / root.
3. Live at `https://OMDESHMUKH1045.github.io/nexus-site/`

**Netlify** — drag the unzipped folder onto https://app.netlify.com/drop

**Cloudflare Pages / Vercel** — connect the repo, no build command, output dir `/`.

## After hosting
- Add your live URL as `<link rel="canonical">` and `og:url` in `index.html`.
- Optional: add a 1200x630 PNG and an `og:image` tag for link previews.
