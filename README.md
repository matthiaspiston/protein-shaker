# Ti22 — titanium protein shaker storefront

A static, single-page storefront for the Ti22 Grade 5 titanium shaker.

```
index.html      page markup
styles.css      design tokens (top of file) and all styles, light + dark
app.js          finish/size configurator, bag drawer (saved in localStorage), forms
assets/img/     product renders (transparent WebP)
tools/render.py procedural renderer that generates every product image
```

Run it with any static server, e.g. `python3 -m http.server` and open http://localhost:8000.

## Re-skinning

All colours, fonts, type scale and spacing live as CSS custom properties in the
`:root` block at the top of `styles.css`. Change them there; components only use tokens.

## Regenerating the product images

```
pip install numpy pillow
python3 tools/render.py                 # everything
python3 tools/render.py raw aurora      # just some shots
```

Shots: `raw`, `obsidian`, `bronze`, `aurora` (colourways), `exploded`, `trio`,
`macro`, `pair`. Geometry is defined as 2D profiles at the top of the script;
materials and the studio lighting are just below.

## Not wired up yet

- **Checkout** — `#checkout` in `app.js` shows a notice; connect Stripe/Shopify there.
- **Newsletter** — the form validates in the page but doesn't send anywhere.
