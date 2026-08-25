import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { getSwatchColor, getBrandTextColor } from '../utils/colors'
import { getReferenceCode } from '../utils/reference'
import { useAuth } from '../auth/AuthContext'

/**
 * SneakerCard
 * -----------
 * Flip card for a single sneaker, styled as an archive index entry rather
 * than a marketplace product tile. Front shows a quiet reference tag,
 * photo/swatch, and price. Back is a ledger sheet — label, dotted leader,
 * value — with a Purchase button that decrements live DB inventory, and a
 * Place Bid option where an agent judges the offer against real market
 * data and purchases automatically if it's accepted. Purchase and Place
 * Bid require being logged in (enforced here and again on the backend) —
 * a logged-out viewer sees a "Log in to purchase" prompt instead.
 *
 * Props:
 *   sneaker    (object)  — catalog entry with live quantity and in_stock fields
 *   username   (string)  — optional; if set, purchase is added to their wardrobe
 *   ownedView  (bool)    — true when showing a sneaker the viewer already
 *                         owns (the Wardrobe tab). Market/price data still
 *                         shows, but Purchase and Place Bid are hidden —
 *                         it isn't in the store's inventory to buy again.
 */
export default function SneakerCard({ sneaker, username, ownedView = false }) {
  const { user } = useAuth()
  const navigate  = useNavigate()
  const location  = useLocation()
  const loggedIn  = Boolean(user)

  const [flipped,     setFlipped]     = useState(false)
  const [quantity,    setQuantity]    = useState(sneaker.quantity ?? (sneaker.in_stock ? 1 : 0))
  const [buying,      setBuying]      = useState(false)
  const [purchased,   setPurchased]   = useState(false)
  const [imageFailed, setImageFailed] = useState(false)

  const [bidding,       setBidding]       = useState(false)
  const [bidAmount,     setBidAmount]     = useState('')
  const [bidSubmitting, setBidSubmitting] = useState(false)
  const [bidResult,     setBidResult]     = useState(null)   // {accepted, reasoning}

  const inStock    = quantity > 0 && !purchased
  const swatchBg   = getSwatchColor(sneaker.colorway, sneaker.name)
  const brandColor = getBrandTextColor(sneaker.colorway, sneaker.name)
  const marketUp   = sneaker.market_value > sneaker.retail_price
  const gain       = (sneaker.market_value - sneaker.retail_price).toFixed(0)
  const showPhoto  = Boolean(sneaker.image) && !imageFailed
  const refCode    = getReferenceCode(sneaker.name)

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

  function goToLogin(e) {
    e.stopPropagation()
    navigate('/login', { state: { from: location.pathname } })
  }

  function toggleBidding(e) {
    e.stopPropagation()
    setBidding(b => !b)
    setBidResult(null)
  }

  async function handleSubmitBid(e) {
    e.stopPropagation()
    const amount = parseFloat(bidAmount)
    if (!inStock || bidSubmitting || !amount || amount <= 0) return
    setBidSubmitting(true)
    setBidResult(null)
    try {
      const res = await fetch('/api/bid', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          sneaker_name: sneaker.name,
          bid_amount:   amount,
          username:     username || null,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        setBidResult({ accepted: data.accepted, reasoning: data.reasoning })
        if (data.purchased) {
          setQuantity(data.quantity)
          setPurchased(true)
        }
      }
    } finally {
      setBidSubmitting(false)
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
          <div
            className="card-swatch"
            style={{ background: showPhoto ? '#F1EFEA' : swatchBg }}
          >
            {showPhoto && (
              <img
                className="card-swatch-img"
                src={sneaker.image}
                alt={sneaker.name}
                loading="lazy"
                onError={() => setImageFailed(true)}
              />
            )}
            <span className="card-ref-tag">№ {refCode}</span>
            <span
              className={'card-swatch-brand' + (showPhoto ? ' on-photo' : '')}
              style={showPhoto ? undefined : { color: brandColor }}
            >
              {sneaker.brand}
            </span>
          </div>
          <div className="card-body">
            <p className="card-name">{sneaker.name}</p>
            <div className="card-price-row">
              <span className="card-price">${sneaker.retail_price}</span>
              {marketUp && (
                <span className="card-price-market">MKT ${sneaker.market_value}</span>
              )}
            </div>
            <div className="card-status-row">
              <span className={'card-status-dot' + (ownedView || inStock ? ' in' : ' out')} />
              <span className="card-status-text">
                {ownedView ? 'Owned' : purchased ? 'Purchased' : inStock ? 'In stock' : 'Out of stock'}
              </span>
              {sneaker.profile && (
                <>
                  <span className="card-status-sep">·</span>
                  <span className="card-status-text">{sneaker.profile}-top</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* ── Back ── */}
        <div className="card-back">
          <span className="card-back-tab" style={{ background: swatchBg }} />
          <div className="card-back-inner">

            <div className="card-back-header">
              <span className="card-back-ref">№ {refCode}</span>
              <span className="card-back-brand">{sneaker.brand}</span>
            </div>

            <p className="card-back-name">{sneaker.name}</p>

            {sneaker.colorway && (
              <p className="card-back-colorway">{sneaker.colorway}</p>
            )}

            <div className="ledger">
              <div className="ledger-row">
                <span className="ledger-label">Retail</span>
                <span className="ledger-fill" />
                <span className="ledger-value">${sneaker.retail_price}</span>
              </div>
              <div className="ledger-row">
                <span className="ledger-label">Market</span>
                <span className="ledger-fill" />
                <span className={'ledger-value' + (marketUp ? ' up' : '')}>
                  ${sneaker.market_value}
                </span>
              </div>
              {sneaker.last_sale && (
                <div className="ledger-row">
                  <span className="ledger-label">Last sale</span>
                  <span className="ledger-fill" />
                  <span className="ledger-value">${sneaker.last_sale}</span>
                </div>
              )}
              {sneaker.lowest_ask && (
                <div className="ledger-row">
                  <span className="ledger-label">Lowest ask</span>
                  <span className="ledger-fill" />
                  <span className="ledger-value">${sneaker.lowest_ask}</span>
                </div>
              )}
              {marketUp && (
                <div className="ledger-row">
                  <span className="ledger-label">Gain</span>
                  <span className="ledger-fill" />
                  <span className="ledger-value up">+${gain}</span>
                </div>
              )}
              {sneaker.deadstock_sold && (
                <div className="ledger-row">
                  <span className="ledger-label">Total sold</span>
                  <span className="ledger-fill" />
                  <span className="ledger-value">{sneaker.deadstock_sold.toLocaleString()}</span>
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

            {ownedView ? (
              /* Already in the viewer's wardrobe — not store inventory, so
                 no Purchase or Bid action; market data above still applies. */
              <p className="card-owned-note">Already in your wardrobe</p>
            ) : !loggedIn ? (
              <button type="button" className="card-login-prompt" onClick={goToLogin}>
                Log in to purchase or bid
              </button>
            ) : (
              <>
                {/* Purchase button */}
                <button
                  className={'card-ledger-btn' + (purchased ? ' purchased' : '') + (!inStock ? ' unavailable' : '')}
                  onClick={handlePurchase}
                  disabled={!inStock || buying}
                >
                  {purchased ? '✓ Purchased' : buying ? 'Processing…' : inStock ? 'Purchase' : 'Out of stock'}
                </button>

                {/* Bid — offer a price; an agent judges fairness against real market data */}
                <div className="card-bid-block" onClick={e => e.stopPropagation()}>
                  {inStock && !purchased && (
                    !bidding ? (
                      <button type="button" className="card-bid-toggle" onClick={toggleBidding}>
                        Place a bid instead
                      </button>
                    ) : (
                      <div className="card-bid-row">
                        <span className="card-bid-dollar">$</span>
                        <input
                          type="number"
                          min="1"
                          className="card-bid-input"
                          placeholder="Your offer"
                          value={bidAmount}
                          onChange={e => setBidAmount(e.target.value)}
                          disabled={bidSubmitting}
                        />
                        <button
                          type="button"
                          className="card-bid-submit"
                          onClick={handleSubmitBid}
                          disabled={bidSubmitting || !bidAmount}
                        >
                          Submit
                        </button>
                      </div>
                    )
                  )}

                  {bidSubmitting && (
                    <p className="card-bid-pending">
                      <span className="card-bid-pending-dot" />
                      Agent reviewing your offer…
                    </p>
                  )}

                  {bidResult && !bidSubmitting && (
                    <div className={'card-bid-verdict' + (bidResult.accepted ? ' accepted' : ' rejected')}>
                      <span className="card-bid-verdict-label">
                        Agent verdict — {bidResult.accepted ? 'Accepted' : 'Rejected'}
                      </span>
                      <p className="card-bid-verdict-text">{bidResult.reasoning}</p>
                    </div>
                  )}
                </div>
              </>
            )}

            <a
              className="card-back-link"
              href={sneaker.link}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
            >
              Source: StockX ↗
            </a>
          </div>
        </div>

      </div>
    </div>
  )
}
