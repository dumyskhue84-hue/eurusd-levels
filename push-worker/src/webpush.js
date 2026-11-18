// Web Push crypto: RFC 8291 (message encryption) + RFC 8292 (VAPID).
// Pure WebCrypto, no dependencies. Verified against RFC 8291 Appendix A
// test vectors in test/webpush.test.mjs.

const te = new TextEncoder()

export const VAPID_PUBLIC_KEY =
  'BMc69gjBD_D_i8Dc44S4hDFLD9kEllfKnDesmLApm-D9XWWeI4Lfei_r63PEZ0U0RWx_2RA4x2BTQO3OTOcIauU'

export function b64url(bytes) {
  let s = ''
  for (const b of bytes) s += String.fromCharCode(b)
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

// Tolerant decoder: accepts base64, base64url, padded or not.
export function un64(s) {
  const t = s.replace(/-/g, '+').replace(/_/g, '/')
  const pad = '='.repeat((4 - (t.length % 4)) % 4)
  const bin = atob(t + pad)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

export function concat(...parts) {
  let n = 0
  for (const p of parts) n += p.length
  const out = new Uint8Array(n)
  let o = 0
  for (const p of parts) {
    out.set(p, o)
    o += p.length
  }
  return out
}

// RFC 5869 HKDF (extract + expand) via WebCrypto.
async function hkdf(salt, ikm, info, length) {
  const key = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits'])
  const bits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info }, key, length * 8)
  return new Uint8Array(bits)
}

// RFC 8291 §3.4: encrypt a push message payload for a Push API subscription.
// Returns the full aes128gcm body (salt || rs || idlen || keyid || ciphertext).
// opts (tests only): { plaintext, salt, asPrivatePkcs8, asPublic } pin the
// inputs so output can be compared byte-for-byte against RFC 8291 App. A.
export async function encryptPayload(sub, plaintextObj, salt = null, opts = {}) {
  const uaPublic = un64(sub.keys.p256dh)   // 65-byte uncompressed P-256 point
  const authSecret = un64(sub.keys.auth)   // 16 octets
  if (uaPublic.length !== 65 || uaPublic[0] !== 0x04) {
    throw new Error('bad p256dh key')
  }
  if (authSecret.length < 16) throw new Error('bad auth secret')
  if (opts.salt) salt = opts.salt
  if (!salt) salt = crypto.getRandomValues(new Uint8Array(16))

  // Ephemeral application-server ECDH key pair (per message).
  let privateKey, asPublic
  if (opts.asPrivatePkcs8) {
    privateKey = await crypto.subtle.importKey(
      'pkcs8', opts.asPrivatePkcs8, { name: 'ECDH', namedCurve: 'P-256' },
      false, ['deriveBits'])
    asPublic = opts.asPublic
  } else {
    const pair = await crypto.subtle.generateKey(
      { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits'])
    privateKey = pair.privateKey
    asPublic = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey))
  }
  const uaKey = await crypto.subtle.importKey(
    'raw', uaPublic, { name: 'ECDH', namedCurve: 'P-256' }, false, [])
  const ecdhSecret = new Uint8Array(await crypto.subtle.deriveBits(
    { name: 'ECDH', public: uaKey }, privateKey, 256))

  // key_info = "WebPush: info" || 0x00 || ua_public || as_public
  const keyInfo = concat(te.encode('WebPush: info'), new Uint8Array([0]), uaPublic, asPublic)
  const ikm = await hkdf(authSecret, ecdhSecret, keyInfo, 32)

  // RFC 8188 CEK / NONCE derivation.
  const cek = await hkdf(salt, ikm,
    concat(te.encode('Content-Encoding: aes128gcm'), new Uint8Array([0])), 16)
  const nonce = await hkdf(salt, ikm,
    concat(te.encode('Content-Encoding: nonce'), new Uint8Array([0])), 12)

  // Single record (RFC 8291 §4): plaintext || 0x02 delimiter, empty AAD.
  const raw = opts.plaintext != null ? opts.plaintext : JSON.stringify(plaintextObj)
  const pt = concat(te.encode(raw), new Uint8Array([0x02]))
  const aesKey = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['encrypt'])
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, aesKey, pt))

  // Header: salt(16) || rs(4 BE = 4096) || idlen(1) || keyid(65)
  const rs = new Uint8Array([0x00, 0x00, 0x10, 0x00])
  return concat(salt, rs, new Uint8Array([65]), asPublic, ct)
}

// RFC 8292 VAPID: Authorization header with an ES256 JWT.
export async function vapidAuthHeader(endpoint, privateKeyB64, subject) {
  const now = Math.floor(Date.now() / 1000)
  const header = b64url(te.encode(JSON.stringify({ typ: 'JWT', alg: 'ES256' })))
  const claims = b64url(te.encode(JSON.stringify({
    aud: new URL(endpoint).origin,
    exp: now + 12 * 3600,
    sub: subject,
  })))
  const data = `${header}.${claims}`
  const key = await crypto.subtle.importKey('pkcs8', un64(privateKeyB64),
    { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign'])
  const sig = new Uint8Array(await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' }, key, te.encode(data)))
  return `vapid t=${data}.${b64url(sig)}, k=${VAPID_PUBLIC_KEY}`
}

// POST an encrypted notification to the push service endpoint.
// Returns { ok, status }; status 404/410 => expired subscription.
export async function sendPush(env, sub, message) {
  const body = await encryptPayload(sub, message)
  const auth = await vapidAuthHeader(sub.endpoint, env.VAPID_PRIVATE_KEY, env.VAPID_SUBJECT)
  const res = await fetch(sub.endpoint, {
    method: 'POST',
    headers: {
      'Content-Encoding': 'aes128gcm',
      'Content-Type': 'application/octet-stream',
      Authorization: auth,
      TTL: '86400',
      Urgency: 'normal',
    },
    body,
  })
  return { ok: res.ok, status: res.status }
}
