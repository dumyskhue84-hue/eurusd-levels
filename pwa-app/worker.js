export default {
  async scheduled(event, env) {
    // Trigger level generation endpoint (GitHub Actions workflow or external cron)
    // In this repo, levels.json is regenerated daily by scripts/generate_levels_json.py
    // via .github/workflows/daily-levels.yml at 00:05 UTC, then Cloudflare Pages redeploys.
    console.log('daily levels cron tick', event.cron)
  },
  async fetch(request) {
    return new Response('EURUSD Levels worker - deploy via Pages', { status: 200 })
  },
}
