import yfinance as yf
from datetime import datetime

def update_market_data(db, MarketData, Asset):
    assets = Asset.query.all()  # Fetch all assets from the database

    for asset in assets:
        symbol = asset.symbol  # Correct indentation

        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')

            if data.empty:
                print(f"⚠️ No market data found for {symbol}")
                continue  # Skip this asset if no data

            latest_price = data['Close'].iloc[-1] if 'Close' in data.columns else None
            latest_volume = data['Volume'].iloc[-1] if 'Volume' in data.columns else None

            if latest_price is not None:
                md = MarketData.query.filter_by(asset_id=asset.asset_id).first()

                if md:
                    md.closing_price = latest_price
                    md.volume = latest_volume
                    md.date = datetime.now()
                else:
                    db.session.add(MarketData(
                        asset_id=asset.asset_id,
                        closing_price=latest_price,
                        volume=latest_volume,
                        date=datetime.now()
                    ))

                print(f"✅ Updated: {asset.name} ({symbol}) → ${latest_price}")

        except Exception as e:
            print(f"❌ Error updating {asset.name} ({symbol}): {e}")

    try:
        db.session.commit()
    except Exception as e:
        print(f"❌ Database commit failed: {e}")
        db.session.rollback()

# Run only if executed directly
if __name__ == "__main__":
    from app import db, MarketData, Asset  # Import only once to avoid circular import
    update_market_data(db, MarketData, Asset)