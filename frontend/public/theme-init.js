// FOUC prevention: applies the stored theme, palette and privacy mode before
// the first paint. An external file rather than an inline <script> so the
// Content-Security-Policy can keep `script-src 'self'`. It must stay a plain,
// synchronous, render-blocking script in <head>, after the theme-color meta.
(function () {
  try {
    var t = localStorage.getItem('finlytics_theme') || 'system'
    if (t === 'system') t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    document.documentElement.setAttribute('data-theme', t)
    var m = document.querySelector('meta[name="theme-color"]')
    if (m) m.setAttribute('content', t === 'dark' ? '#0c1420' : '#f4f6f9')
    var p = localStorage.getItem('finlytics_accent_palette') || 'classic'
    if (['classic', 'emerald', 'violet', 'amber', 'contrast'].indexOf(p) === -1) p = 'classic'
    document.documentElement.setAttribute('data-palette', p)
    // Without this the amounts render sharp for one frame on every
    // reload, which is exactly what the privacy toggle exists to avoid.
    if (localStorage.getItem('finlytics_privacy') === '1') {
      document.documentElement.setAttribute('data-privacy', 'on')
    }
  } catch (e) { /* ignore */ }
})()
