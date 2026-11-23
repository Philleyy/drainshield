// Relay for the DrainShield site, run free on Cloudflare Workers.
// McGill's network blocks *.ample.run, so the same site is also served from a workers.dev address:
// this script fetches each page from Ample and hands it back unchanged.
const TARGET = 'https://x9unyy6jkf5h.ample.run'

export default {
  async fetch(request) {
    const url = new URL(request.url)
    const headers = new Headers(request.headers)
    headers.delete('host')
    // the site refuses sign-ins and saves sent from another address, so they arrive as if from its own
    if (headers.get('origin') === url.origin) headers.set('origin', TARGET)   // any other site is still refused
    // keeps the sign-in attempt limit per person rather than shared by everyone behind the relay
    headers.set('x-forwarded-for', request.headers.get('cf-connecting-ip') || '')
    return fetch(TARGET + url.pathname + url.search, {
      method: request.method,
      headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(),
      redirect: 'manual',
    })
  },
}
