/**
 * getSwatchColor
 * --------------
 * Derives a swatch background color from a sneaker's colorway string.
 * Falls back to the sneaker name when colorway is absent (sneakerdata.json
 * doesn't have a colorway field, but color keywords appear in the name).
 *
 * @param {string} colorway    - explicit colorway, e.g. "White/Cool Grey"
 * @param {string} fallbackName - sneaker name used when colorway is empty
 * @returns {string} hex color
 */
export function getSwatchColor(colorway, fallbackName = '') {
  const c = (colorway || fallbackName || '').toLowerCase()

  if (c.includes('cinder'))                                                    return '#464B53'
  if (c.includes('infrared'))                                                  return '#A84040'
  if (c.includes('blue') || c.includes('unc') || c.includes('navy') || c.includes('frost')) return '#6A8EA0'
  if (c.includes('red') || c.includes('university red') || c.includes('bred')) return '#9E4040'
  if (c.includes('orange') || c.includes('del sol'))                          return '#C07844'
  if (c.includes('green') || c.includes('malachite') || c.includes('mint') || c.includes('sage') || c.includes('pine')) return '#7A9E8E'
  if (c.includes('coral') || c.includes('bleached'))                          return '#C49080'
  if (c.includes('teal'))                                                      return '#6A9E9E'
  if (c.includes('grey') || c.includes('gray') || c.includes('fog') || c.includes('stone') || c.includes('cement')) return '#8A8C88'
  if (c.includes('black') && !c.includes('white'))                            return '#2A2D30'
  if (c.includes('white') && !c.includes('black'))                            return '#D8D4CE'
  if (c.includes('black') && c.includes('white'))                             return '#3C3F44'
  if (c.includes('panda'))                                                     return '#3C3F44'
  if (c.includes('zebra'))                                                     return '#3C3F44'

  return '#B8BDA7'
}

/**
 * getBrandTextColor
 * -----------------
 * Returns a legible label color for the brand name on the swatch.
 *
 * @param {string} colorway
 * @param {string} fallbackName
 * @returns {string} rgba color string
 */
export function getBrandTextColor(colorway, fallbackName = '') {
  const c = (colorway || fallbackName || '').toLowerCase()
  const isLight =
    (c.includes('white') && !c.includes('black')) ||
    c.includes('mint') ||
    c.includes('platinum')

  return isLight ? 'rgba(70,75,83,0.6)' : 'rgba(255,255,255,0.7)'
}
