// Byte-exact check of encryptPayload() against RFC 8291 Appendix A
// (Section 5 example: "When I grow up, I want to be a watermelon").
// Run: node push-worker/test/webpush.test.mjs
import assert from 'node:assert/strict'
import { encryptPayload, un64, concat, VAPID_PUBLIC_KEY } from '../src/webpush.js'

// ---- RFC 8291 A inputs (base64url, whitespace removed) ----
const PLAINTEXT = 'When I grow up, I want to be a watermelon'
const AUTH_SECRET = 'BTBZMqHH6r4Tts7J_aSIgg'
const UA_PUBLIC =
  'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcx' +
  'aOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4'
const AS_PRIVATE = 'yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw'
const AS_PUBLIC =
  'BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIg' +
  'Dll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8'
const SALT = 'DGv6ra1nlYgDCS1FRnbzlw'

// Expected result: Section 5 push body (header || ciphertext), base64url.
const EXPECTED_BODY =
  'DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml' +
  'mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT' +
  'pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN'

// Intermediate values (A) for pinpointing failures.
const ECDH_SECRET = 'kyrL1jIIOHEzg3sM2ZWRHDRB62YACZhhSlknJ672kSs'
const IKM = 'S4lYMb_L0FxCeq0WhDx813KgSYqU26kOyzWUdsXYyrg'
const CEK = 'oIhVW04MRdy2XN9CiKLxTg'
const NONCE = '4h_95klXJ5E_qnoN'

// ---- helpers ----
const hex = (h) => Uint8Array.from(h.replace(/\s+/g, '').match(/../g) || [],
  (x) => parseInt(x, 16))

// Raw 32-byte P-256 scalar -> PKCS#8 DER:
// SEQUENCE { 0, algId, OCTET { SEQUENCE { 1, OCTET { scalar } } } }
function p256Pkcs8(raw) {
  const priv = concat(new Uint8Array([0x04, 0x20]), raw)
  const ecKey = concat(new Uint8Array([0x02, 0x01, 0x01]), priv)
  const ecSeq = concat(new Uint8Array([0x30, ecKey.length]), ecKey)
  const oct = concat(new Uint8Array([0x04, ecSeq.length]), ecSeq)
  const algId = hex('301306072a8648ce3d020106082a8648ce3d030107')
  const content = concat(new Uint8Array([0x02, 0x01, 0x00]), algId, oct)
  return concat(new Uint8Array([0x30, content.length]), content)
}

async function main() {
  const sub = { keys: { p256dh: UA_PUBLIC, auth: AUTH_SECRET } }
  const body = await encryptPayload(sub, null, null, {
    plaintext: PLAINTEXT,
    salt: un64(SALT),
    asPrivatePkcs8: p256Pkcs8(un64(AS_PRIVATE)),
    asPublic: un64(AS_PUBLIC),
  })

  // 1) Byte-exact against RFC 8291 Section 5.
  assert.deepEqual(body, un64(EXPECTED_BODY), 'body matches RFC 8291 A')

  // 2) Framing invariants (RFC 8188 header).
  assert.equal(body[20], 65, 'idlen = 65')
  assert.deepEqual(body.slice(16, 20), new Uint8Array([0, 0, 0x10, 0]), 'rs = 4096')
  assert.deepEqual(body.slice(21, 86), un64(AS_PUBLIC), 'keyid = as_public')

  // 3) Deterministic: same inputs -> same output.
  const again = await encryptPayload(sub, null, null, {
    plaintext: PLAINTEXT,
    salt: un64(SALT),
    asPrivatePkcs8: p256Pkcs8(un64(AS_PRIVATE)),
    asPublic: un64(AS_PUBLIC),
  })
  assert.deepEqual(again, body, 'deterministic with pinned inputs')

  // 4) Real path (random ephemeral key): framing still holds.
  const live = await encryptPayload(sub, { title: 'x', body: 'y' })
  assert.equal(live.length, 16 + 4 + 1 + 65 + JSON.stringify({ title: 'x', body: 'y' }).length + 1 + 16,
    'live framing length')
  assert.notDeepEqual(live.slice(86), body.slice(86), 'live ephemeral key differs')

  // 5) Sanity: derived intermediates (documented in A) are stable inputs
  //    only via full-body match above; assert key lengths here.
  assert.equal(un64(ECDH_SECRET).length, 32, 'ecdh secret 32B')
  assert.equal(un64(IKM).length, 32, 'IKM 32B')
  assert.equal(un64(CEK).length, 16, 'CEK 16B')
  assert.equal(un64(NONCE).length, 12, 'NONCE 12B')

  // 6) VAPID public key shape (65-byte P-256 point, base64url).
  const vapid = un64(VAPID_PUBLIC_KEY)
  assert.equal(vapid.length, 65, 'vapid pubkey 65B')
  assert.equal(vapid[0], 0x04, 'vapid uncompressed')

  console.log('webpush.test: OK (RFC 8291 Appendix A byte-exact)')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
