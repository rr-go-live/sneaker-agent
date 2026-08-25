/**
 * getReferenceCode
 * -----------------
 * Derives a stable 4-digit index tag from a sneaker's name — styled like a
 * museum accession number or library catalog code. Purely a browsing device
 * (it distinguishes visually similar entries, e.g. Women's/GS variants of
 * the same release) and is not read anywhere as real inventory data.
 *
 * Deterministic: the same name always produces the same code, so a card's
 * tag doesn't change between renders or catalog reloads.
 *
 * @param {string} name - sneaker name
 * @returns {string} 4-digit code, e.g. "0412"
 */
export function getReferenceCode(name) {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return String(hash % 10000).padStart(4, '0')
}
