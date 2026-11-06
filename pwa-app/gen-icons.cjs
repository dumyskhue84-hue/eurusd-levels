const sharp = require('sharp')
;(async () => {
  const bg = '#0f1419'
  const s192 = `<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192"><rect fill="${bg}" width="192" height="192" rx="32"/><text x="50%" y="120" font-size="96" text-anchor="middle" fill="#1d9bf0" font-family="sans-serif">\u20AC</text></svg>`
  const s512 = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect fill="${bg}" width="512" height="512" rx="80"/><text x="50%" y="320" font-size="256" text-anchor="middle" fill="#1d9bf0" font-family="sans-serif">\u20AC</text></svg>`
  await sharp(Buffer.from(s192)).png().toFile('public/icon-192.png')
  await sharp(Buffer.from(s512)).png().toFile('public/icon-512.png')
  console.log('icons ok')
})()
