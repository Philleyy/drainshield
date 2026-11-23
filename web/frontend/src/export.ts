// The cleaning list as a spreadsheet file, made in the browser (nothing to install, nothing sent anywhere).
// Tab-separated UTF-16 opens straight into columns in Excel whatever the computer's language, accents included.

export function downloadTable(filename: string, header: string[], rows: (string | number)[][]) {
  const clean = (v: string | number) => String(v).replace(/[\t\r\n]+/g, ' ')
  const text = [header, ...rows].map(r => r.map(clean).join('\t')).join('\r\n')
  const bytes = new Uint8Array(2 + text.length * 2)
  bytes[0] = 0xff; bytes[1] = 0xfe                                     // UTF-16 little-endian byte order mark
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i)
    bytes[2 + 2 * i] = c & 0xff; bytes[3 + 2 * i] = c >> 8
  }
  const url = URL.createObjectURL(new Blob([bytes], { type: 'text/csv;charset=utf-16le' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}
