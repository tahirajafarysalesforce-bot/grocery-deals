# Grocery Deals

One page that shows this week's deals from Giant, Lidl, Aldi and Lotte Plaza Market, searchable from your laptop or phone.

Stores don't offer a feed of their deals (Aldi's site also forbids automated access), so the weekly flow is: **you add the flyer, the app reads it.**

## Each week (about 2 minutes)

1. Open each store's weekly ad and save it as a screenshot or PDF. On a phone, screenshots work fine; take one per page.
2. In your GitHub repo, open the matching folder (`flyers/giant`, `flyers/lidl`, `flyers/aldi`, `flyers/lotte`), choose **Add file → Upload files**, and commit.
3. A GitHub Action reads the new flyers with Claude, writes the deals into `data/`, and rebuilds `data/deals.json`. The page updates in a minute or two.

Old flyers: delete the file from its folder and its deals are removed. Deals past their end date are hidden automatically.

Aldi's ad starts Wednesday in most areas; Giant, Lidl and Lotte have their own days, so upload whenever a new one appears.

## One-time setup

1. Create a new GitHub repository (public is simplest, because free GitHub Pages needs a public repo) and upload everything in this folder.
2. **Settings → Secrets and variables → Actions → New repository secret**: name `ANTHROPIC_API_KEY`, value is your key from console.anthropic.com. Reading flyers is billed to that key, typically cents per week.
3. **Settings → Pages → Build and deployment**: Source "Deploy from a branch", branch `main`, folder `/ (root)`.
4. Your site is at `https://<your-username>.github.io/<repo-name>/`.
5. On your phone, open that link and use **Add to Home Screen** so it opens like an app.

Until you add real flyers the page shows clearly labeled sample data.

## Using the page

- Search any word ("chicken", "coffee"); every word must match.
- Tap store chips to include or hide a store.
- **My watch list**: add items you always want. Matching deals get an outline, and "Watch list only" hides everything else. The list is saved in your browser, per device.
- Sort by lowest price, ending soonest, store, or name.

## Running it on your own computer instead

```bash
pip install anthropic pillow
export ANTHROPIC_API_KEY=...
python scripts/extract_flyers.py   # reads new files in flyers/*
python scripts/build_deals.py      # writes data/deals.json
python -m http.server 8000         # open http://localhost:8000
```

## Notes

- Image files over about 4.5 MB are shrunk automatically before reading.
- Prices come from reading the flyer image, so skim for mistakes on anything you'd drive for. The deal cards show the price exactly as extracted.
- To change the model, set the `DEALS_MODEL` environment variable.
