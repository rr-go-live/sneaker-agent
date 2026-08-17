import { useState } from 'react'
import { getSwatchColor, getBrandTextColor } from '../utils/colors'

/**
 * SneakerCard
 * -----------
 * Flip card for a single sneaker. Front shows swatch + price. Back shows
 * full market data and a Purchase button that decrements live DB inventory.
 *
 * Props:
 *   sneaker  (object) — catalog entry with live quantity and in_stock fields
 *   username (string) — optional; if set, purchase is added to their wardrobe
 */
export default function SneakerCard({ sneaker, username }) {
  const [flipped,   setFlipped]   = useState(false)
  const [quantity,  setQuantity]  = useState(sneaker.quantity ?? (sneaker.in_stock ? 1 : 0))
  const [buying,    setBuying]    = useState(false)
  const [purchased, setPurchased] = useState(false)

  const inStock    = quantity > 0 && !purchased
  const swatchBg   = getSwatchColor(sneaker.colorway, sneaker.name)
  const brandColor = getBrandTextColor(sneaker.colorway, sneaker.name)
  const marketUp   = sneaker.market_value > sneaker.retail_price
  const gain       = (sneaker.market_value - sneaker.retail_price).toFixed(0)

  async function handlePurchase(e) {
    e.stopPropagation()
    if (!inStock || buying) return
    setBuying(true)
    try {
      const res = await fetch('/api/inventory/purchase', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          sneaker_name: sneaker.name,
          username:     username || null,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setQuantity(data.quantity)
        setPurchased(true)
      }
    } finally {
      setBuying(false)
    }
  }

  return (
    <div
      className={'sneaker-card-flip' + (flipped ? ' flipped' : '')}
      onClick={() => setFlipped(f => !f)}
    >
      <div className="card-flip-inner">

        {/* ── Front ── */}
        <div className="card-front">
          <div className="card-swatch" style={{ background: swatchBg }}>
            <span className="card-swatch-brand" style={{ color: brandColor }}>
              {sneaker.brand}
            </span>
          </div>
          <div className="card-body">
            <p className="card-name">{sneaker.name}</p>
            <div className="card-meta">
              <div className="card-price-row">
                <span className="card-retail">${sneaker.retail_price}</span>
                {marketUp && (
                  <span className="card-market up">↑ ${sneaker.market_value} resale</span>
                )}
              </div>
              <div className="card-badges">
                <span className={inStock ? 'badge badge-stock' : 'badge badge-nostock'}>
                  {purchased ? 'Purchased' : inStock ? 'In Stock' : 'Out of Stock'}
                </span>
                {sneaker.profile && (
                  <span className={`badge badge-${sneaker.profile}`}>{sneaker.profile}</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── Back ── */}
        <div className="card-back" style={{ background: swatchBg }}>
          <div className="card-back-inner">

            <div className="card-back-header">
              <span className="card-back-brand">{sneaker.brand}</span>
              {sneaker.profile && (
                <span className="card-back-profile">{sneaker.profile}</span>
              )}
            </div>

            <p className="card-back-name">{sneaker.name}</p>

            {sneaker.colorway && (
              <p className="card-back-colorway">{sneaker.colorway}</p>
            )}

            <div className="card-back-stats">
              <div className="stat">
                <span className="stat-label">Retail</span>
                <span className="stat-value">${sneaker.retail_price}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Market</span>
                <span className="stat-value">${sneaker.market_value}</span>
              </div>
              {sneaker.last_sale && (
                <div className="stat">
                  <span className="stat-label">Last Sale</span>
                  <span className="stat-value">${sneaker.last_sale}</span>
                </div>
              )}
              {sneaker.lowest_ask && (
                <div className="stat">
                  <span className="stat-label">Lowest Ask</span>
                  <span className="stat-value">${sneaker.lowest_ask}</span>
                </div>
              )}
              {marketUp && (
                <div className="stat">
                  <span className="stat-label">Gain</span>
                  <span className="stat-value stat-gain">+${gain}</span>
                </div>
              )}
              {sneaker.deadstock_sold && (
                <div className="stat">
                  <span className="stat-label">Total Sold</span>
                  <span className="stat-value">{sneaker.deadstock_sold.toLocaleString()}</span>
                </div>
              )}
            </div>

            {sneaker.release_date && (
              <p className="card-back-release">
                Released {new Date(sneaker.release_date).toLocaleDateString('en-US', {
                  year: 'numeric', month: 'short', day: 'numeric',
                })}
              </p>
            )}

            {/* Purchase button */}
            <button
              className={'card-purchase-btn' + (purchased ? ' purchased' : '') + (!inStock ? ' unavailable' : '')}
              onClick={handlePurchase}
              disabled={!inStock || buying}
            >
              {purchased ? '✓ Purchased' : buying ? 'Processing…' : inStock ? 'Purchase' : 'Out of Stock'}
            </button>

            <a
              className="card-back-link"
              href={sneaker.link}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
            >
              View on StockX ↗
            </a>
          </div>
        </div>

      </div>
    </div>
  )
}
